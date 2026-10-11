"""One searchable map of everything the server can reach: CBS tables, Eurostat/DG datasets,
agri-food endpoints, European Parliament endpoints and data.europa.eu tools.

The APIs publish little "what is this about" metadata, so each entry is enriched from what is
available (Eurostat theme tree, OpenAPI tags/summaries, agri-food code lists) plus the
hand-written `source_hints.json`. `find_data` ranks entries and says which tool to call next.
"""

from __future__ import annotations

import asyncio
import csv
import json
import logging
import re
import sqlite3
import time
from collections.abc import Awaitable, Callable
from importlib.resources import files
from pathlib import Path
from typing import Any

from . import agrifood, europarl, eurostat
from .common import clip
from .index import STOPWORDS, SYNONYMS, Index, default_path, fold
from .web import fetch, fetch_json

log = logging.getLogger("cbs_mcp")

SCHEMA = """
CREATE TABLE IF NOT EXISTS entries(
    source TEXT NOT NULL, id TEXT NOT NULL, title TEXT, path TEXT, keywords TEXT,
    period TEXT, updated TEXT, call TEXT, builder TEXT NOT NULL, PRIMARY KEY(source, id));
CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
    source UNINDEXED, id UNINDEXED, title, path, keywords, builder UNINDEXED,
    tokenize='unicode61 remove_diacritics 2');
CREATE TABLE IF NOT EXISTS map_meta(source TEXT PRIMARY KEY, built REAL, count INTEGER);
"""
CANDIDATES = 600
LOOKUP_CONCURRENCY = 8
PREFIX_MIN = 6  # shorter terms match whole words only ('house' must not match 'household')

Entry = dict[str, str]


def hints() -> dict[str, Any]:
    return json.loads(files("cbs_mcp").joinpath("source_hints.json").read_text("utf-8"))


def words_of(s: str) -> str:
    """'pigmeat/cuts/prices' / 'rawMilk' → 'pigmeat cuts prices' / 'raw milk rawmilk'."""
    s = s.replace("/", " ").replace("-", " ").replace("_", " ")
    split = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", s)
    return f"{split} {s}".lower() if split != s else s.lower()


def keyword_hint(kw: dict[str, str], source: str, ident: str) -> str:
    return " ".join(v for k, v in kw.items()
                    if k.startswith(source + ":") and ident.startswith(k.split(":", 1)[1]))


# ---- builders (one per source) ---------------------------------------------------------


def toc_entries(text: str) -> list[Entry]:
    """Eurostat TOC: indentation (4 spaces per level) gives each dataset its theme path."""
    out: dict[str, Entry] = {}
    stack: list[str] = []
    reader = csv.reader(text.splitlines(), delimiter="\t")
    next(reader, None)
    for r in reader:
        if len(r) < 7:
            continue
        raw, code, kind = r[0], r[1].strip(), r[2].strip()
        level = (len(raw) - len(raw.lstrip(" "))) // 4
        title = raw.strip()
        if kind == "folder":
            stack = stack[:level] + [title]
            continue
        path = " > ".join(t for t in stack[:level] if t not in ("Database by themes", "Tables by themes"))
        if code in out:  # same dataset filed under several themes: keep the extra paths as keywords
            if path and path not in out[code]["path"]:
                out[code]["keywords"] += " " + path
            continue
        start, end = r[5].strip(), r[6].strip()
        out[code] = {
            "source": "Eurostat", "id": code, "title": title, "path": path,
            "keywords": f"{code} {'table' if kind == 'table' else ''}".strip(),
            "period": f"{start}–{end}" if start else "", "updated": eurostat.iso_date(r[3]),
            "call": f'eurostat_describe("{code}")',
        }
    return list(out.values())


async def build_eurostat(_: Index | None) -> list[Entry]:
    base = eurostat.AGENCIES["eurostat"][0]
    resp = await fetch(f"{base}/catalogue/toc/txt", {"lang": "en"})
    return toc_entries(resp.text)


async def build_dg(_: Index | None) -> list[Entry]:
    labels = {"empl": "DG EMPL", "grow": "DG GROW", "taxud": "DG TAXUD"}
    blurbs = hints()["sources"]
    out = []
    for key, label in labels.items():
        rows = await eurostat.catalog(key)
        ids = {r["id"] for r in rows}
        for r in rows:
            parent, _, suffix = r["id"].partition("$")
            if suffix and len(suffix) == 2 and parent in ids:
                continue  # per-country copy of a parent dataset
            out.append({
                "source": label, "id": r["id"], "title": r["title"], "path": blurbs.get(label, ""),
                "keywords": words_of(r["id"]), "period": r["period"], "updated": r["updated"],
                "call": f'eurostat_describe("{r["id"]}", agency="{key}")',
            })
    return out


async def build_agrifood(_: Index | None) -> list[Entry]:
    spec = await fetch_json(f"{agrifood.BASE}/v3/api-docs")
    kw = hints()["keywords"]
    data_eps, lookups = {}, []
    for path, ops in spec.get("paths", {}).items():
        op = ops.get("get")
        if op is None or not path.startswith("/api/"):
            continue
        ep = path.removeprefix("/api/")
        params = [p["name"] for p in op.get("parameters", []) if p.get("in") == "query"]
        if params:
            data_eps[ep] = (op, params)
        else:
            lookups.append(ep)

    # Harvest code-list values (product names, categories…) as keywords for the sector.
    sem = asyncio.Semaphore(LOOKUP_CONCURRENCY)
    values: dict[str, set[str]] = {}

    async def harvest(ep: str) -> None:
        async with sem:
            try:
                data = await fetch_json(f"{agrifood.BASE}/api/{ep}")
            except Exception as e:  # noqa: BLE001 - a missing code list just means fewer keywords
                log.debug("agrifood lookup %s failed: %s", ep, e)
                return
        items = data if isinstance(data, list) else []
        found = values.setdefault(ep.split("/")[0], set())
        for x in items[:300]:
            texts = x.values() if isinstance(x, dict) else [x]
            found.update(str(t) for t in texts if isinstance(t, str) and 2 < len(t) < 60)

    await asyncio.gather(*(harvest(ep) for ep in lookups))
    out = []
    for ep, (op, params) in sorted(data_eps.items()):
        sector = ep.split("/")[0]
        tag = ", ".join(op.get("tags") or [])
        harvested = " ".join(sorted(values.get(sector, set())))[:1500]
        out.append({
            "source": "Agrifood", "id": ep, "title": op.get("summary") or ep,
            "path": f"EU agri-food > {tag}" if tag else "EU agri-food",
            "keywords": f"{words_of(ep)} {keyword_hint(kw, 'Agrifood', ep)} {harvested}".strip(),
            "period": "", "updated": "",
            "call": f'agri_data("{ep}", {{{", ".join(repr(p) + ": …" for p in params[:3])}}})',
        })
    return out


async def build_europarl(_: Index | None) -> list[Entry]:
    spec = await fetch_json(f"{europarl.BASE}/")
    kw = hints()["keywords"]
    tags = {t["name"]: t.get("description", "") for t in spec.get("tags", [])}
    out = []
    for path, ops in spec.get("paths", {}).items():
        op = ops.get("get")
        ep = path.strip("/")
        if op is None or "{" in ep or ep.endswith("/feed"):  # lists only; details go via ep_query
            continue
        desc = re.sub(r"!\[[^\]]*\]\([^)]*\)|\[([^\]]*)\]\([^)]*\)|<[^>]+>", r"\1", op.get("description") or "")
        tag = ", ".join(op.get("tags") or [])
        out.append({
            "source": "European Parliament", "id": ep,
            "title": (op.get("summary") or ep).replace("Returns the list of all ", "").replace("Returns ", ""),
            "path": f"European Parliament > {tag}",
            "keywords": f"{words_of(ep)} {keyword_hint(kw, 'European Parliament', ep)} "
                        f"{clip(desc, 300)} {tags.get(tag, '')}",
            "period": "", "updated": "", "call": f'ep_query("{ep}")',
        })
    return out


async def build_curated(_: Index | None) -> list[Entry]:
    out = []
    for e in hints()["entries"]:
        out.append({"path": hints()["sources"].get(e["source"], ""), "period": "", "updated": "", **e})
    return out


def cbs_entries(index: Index) -> list[Entry]:
    rows = index.db.execute(
        "SELECT id, title, description, period, substr(modified,1,10) AS m, terms FROM datasets "
        "WHERE status='Regulier'"
    )
    return [
        {
            "source": "CBS", "id": r["id"], "title": r["title"] or "",
            "path": "CBS Netherlands", "keywords": f"{(r['terms'] or '')[:1500]} {clip(r['description'], 300)}",
            "period": r["period"] or "", "updated": r["m"] or "", "call": f'describe_dataset("{r["id"]}")',
        }
        for r in rows
    ]


async def build_cbs(index: Index | None) -> list[Entry]:
    if index is None or not index.count():
        raise RuntimeError("CBS index is empty")
    return cbs_entries(index)


BUILDERS: dict[str, Callable[[Index | None], Awaitable[list[Entry]]]] = {
    "CBS": build_cbs,
    "Eurostat": build_eurostat,
    "DG": build_dg,
    "Agrifood": build_agrifood,
    "European Parliament": build_europarl,
    "curated": build_curated,
}


# ---- the map ----------------------------------------------------------------------------


def expand(query: str, synonyms: dict[str, list[str]]) -> list[list[str]]:
    """Query → OR-groups of terms: EN→NL (index.SYNONYMS), NL→EN (reversed) and EU hints."""
    groups = []
    for tok in re.findall(r"\w+", fold(query)):
        if len(tok) < 2 or tok in STOPWORDS:
            continue
        alts = [tok, *synonyms.get(tok, ())]
        alts += synonyms.get(tok[:-1], ()) if tok.endswith("s") else synonyms.get(tok + "s", ())
        groups.append(list(dict.fromkeys(fold(a) for a in alts if a)))
    return groups


def fts_term(a: str) -> str:
    if len(a) >= PREFIX_MIN:
        return f'"{a}"*'
    return f'("{a}" OR "{a}s" OR "{a}es")'


def term_regex(groups: list[list[str]]) -> list[re.Pattern[str]]:
    """One regex per query group, matching like fts_term (word start; whole word if short)."""
    pats = []
    for alts in groups:
        parts = [re.escape(a) + (r"" if len(a) >= PREFIX_MIN else r"(?:s|es)?\b") for a in alts]
        pats.append(re.compile(r"\b(?:" + "|".join(parts) + ")"))
    return pats


class SourceMap:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else default_path().with_name("sourcemap.db")
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self._lock = asyncio.Lock()
        self.synonyms = self._synonyms()

    @staticmethod
    def _synonyms() -> dict[str, list[str]]:
        syn: dict[str, list[str]] = {k: list(v) for k, v in SYNONYMS.items()}
        for en, nls in SYNONYMS.items():  # Dutch query terms also find English titles
            for nl in nls:
                syn.setdefault(nl, []).append(en)
        for k, v in hints()["synonyms"].items():
            syn.setdefault(k, []).extend(v)
        return syn

    def count(self, source: str | None = None) -> int:
        if source:
            return self.db.execute("SELECT count(*) FROM entries WHERE source=?", (source,)).fetchone()[0]
        return self.db.execute("SELECT count(*) FROM entries").fetchone()[0]

    def age(self) -> float:
        row = self.db.execute("SELECT min(built) FROM map_meta").fetchone()
        return time.time() - (row[0] or 0)

    def replace(self, builder: str, entries: list[Entry]) -> None:
        """Swap all rows of one builder atomically (a failed build keeps the old rows)."""
        with self.db:
            self.db.execute("DELETE FROM entries WHERE builder=?", (builder,))
            self.db.execute("DELETE FROM entries_fts WHERE builder=?", (builder,))
            for e in entries:
                row = (e["source"], e["id"], e.get("title", ""), e.get("path", ""), e.get("keywords", ""))
                self.db.execute(
                    "INSERT OR REPLACE INTO entries VALUES(?,?,?,?,?,?,?,?,?)",
                    (*row, e.get("period", ""), e.get("updated", ""), e.get("call", ""), builder),
                )
                self.db.execute("INSERT INTO entries_fts VALUES(?,?,?,?,?,?)", (*row, builder))
            self.db.execute("INSERT OR REPLACE INTO map_meta VALUES(?,?,?)", (builder, time.time(), len(entries)))

    async def build(self, index: Index | None = None, only: list[str] | None = None) -> dict[str, int | str]:
        async with self._lock:
            stats: dict[str, int | str] = {}

            async def run(name: str) -> None:
                try:
                    entries = await BUILDERS[name](index)
                except Exception as e:  # noqa: BLE001 - keep the previous rows for this source
                    log.warning("source map: %s failed: %s", name, e)
                    stats[name] = f"failed ({type(e).__name__})"
                    return
                self.replace(name, entries)
                stats[name] = len(entries)

            await asyncio.gather(*(run(n) for n in (only or BUILDERS)))
            log.info("source map built: %s", stats)
            return stats

    def search(self, query: str, sources: list[str] | None = None) -> list[dict[str, Any]]:
        """Ranked entries: FTS candidates (OR of all terms), reranked by term coverage."""
        groups = expand(query, self.synonyms)
        if not groups:
            return []
        expr = " OR ".join(fts_term(a) for alts in groups for a in alts)
        params: list[Any] = [expr]
        where = "entries_fts MATCH ?"
        if sources:
            where += f" AND e.source IN ({','.join('?' * len(sources))})"
            params += sources
        sql = f"""
            SELECT e.*, bm25(entries_fts, 0, 0, 8.0, 3.0, 1.0, 0) AS score
            FROM entries_fts JOIN entries e ON e.source = entries_fts.source AND e.id = entries_fts.id
            WHERE {where} ORDER BY score LIMIT {CANDIDATES}"""

        pats = term_regex(groups)

        def hits(text: str) -> int:
            text = fold(text)
            return sum(bool(p.search(text)) for p in pats)

        ranked = []
        for r in self.db.execute(sql, params):
            r = dict(r)
            in_title = hits(r["title"])
            in_any = hits(f"{r['title']} {r['path']} {r['keywords']}")
            ranked.append((-in_any, -in_title, r["score"], r))
        ranked.sort(key=lambda t: t[:3])
        return [{**r, "coverage": -a / len(groups)} for a, _, _, r in ranked]

    def export(self, out: Path) -> int:
        rows = self.db.execute(
            "SELECT source, id, title, path, period, updated, call, keywords FROM entries ORDER BY source, id")
        with out.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["source", "id", "title", "topic_path", "period", "updated", "next_call", "keywords"])
            n = 0
            for r in rows:
                w.writerow([*tuple(r)[:7], clip(r["keywords"], 500)])
                n += 1
        return n
