"""One searchable map of everything the server can reach, used by find_data.

The APIs publish little "what is this about" metadata, so each country package contributes
map builders that enrich entries from whatever is available (theme trees, OpenAPI tags, code
lists) plus its hand-written `hints.json`. `find_data` ranks entries and says what to call next.
"""

from __future__ import annotations

import asyncio
import csv
import logging
import re
import sqlite3
import time
from collections.abc import Awaitable, Callable, Iterable
from pathlib import Path
from typing import Any

from .common import STOPWORDS, cache_dir, clip, fold

log = logging.getLogger("europa_mcp")

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
PREFIX_MIN = 6  # shorter terms match whole words only ('house' must not match 'household')

Entry = dict[str, str]
Builder = Callable[[], Awaitable[list[Entry]]]


def words_of(s: str) -> str:
    """'pigmeat/cuts/prices' / 'rawMilk' → 'pigmeat cuts prices' / 'raw milk rawmilk'."""
    s = s.replace("/", " ").replace("-", " ").replace("_", " ")
    split = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", s)
    return f"{split} {s}".lower() if split != s else s.lower()


def keyword_hint(kw: dict[str, str], source: str, ident: str) -> str:
    return " ".join(v for k, v in kw.items()
                    if k.startswith(source + ":") and ident.startswith(k.split(":", 1)[1]))



# ---- the map ----------------------------------------------------------------------------


def expand(query: str, synonyms: dict[str, list[str]]) -> list[list[str]]:
    """Query → OR-groups of terms, each the query word plus its synonyms (see merge_synonyms)."""
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


def merge_synonyms(
    to_local: Iterable[dict[str, Iterable[str]]], extra: Iterable[dict[str, Iterable[str]]]
) -> dict[str, list[str]]:
    """English → local-language lists apply both ways (a Dutch query also finds English titles);
    `extra` (hints.json synonyms) apply as written."""
    syn: dict[str, list[str]] = {}
    for table in to_local:
        for en, local in table.items():
            syn.setdefault(en, []).extend(local)
            for word in local:
                syn.setdefault(word, []).append(en)
    for table in extra:
        for k, v in table.items():
            syn.setdefault(k, []).extend(v)
    return syn


class SourceMap:
    def __init__(
        self, path: Path | str | None = None, synonyms: dict[str, list[str]] | None = None,
        builders: dict[str, Builder] | None = None,
    ):
        self.path = Path(path) if path else cache_dir() / "sourcemap.db"
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self._lock = asyncio.Lock()
        self.synonyms = synonyms or {}
        self.builders = builders or {}

    def count(self, source: str | None = None) -> int:
        if source:
            return self.db.execute("SELECT count(*) FROM entries WHERE source=?", (source,)).fetchone()[0]
        return self.db.execute("SELECT count(*) FROM entries").fetchone()[0]

    def missing(self) -> list[str]:
        """Builders that have never run (or failed) against this database."""
        done = {r[0] for r in self.db.execute("SELECT source FROM map_meta")}
        return [b for b in self.builders if b not in done]

    async def ensure(self) -> None:
        """Make sure every builder has run once (waits for a build already in progress)."""
        if not self.missing():
            return
        async with self._lock:
            pass
        if missing := self.missing():
            await self.build(only=missing)

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

    async def build(self, only: list[str] | None = None) -> dict[str, int | str]:
        """Run builders concurrently; a failing builder keeps its previous rows."""
        async with self._lock:
            stats: dict[str, int | str] = {}

            async def run(name: str) -> None:
                try:
                    entries = await self.builders[name]()
                except Exception as e:  # noqa: BLE001 - keep the previous rows for this source
                    log.warning("source map: %s failed: %s", name, e)
                    stats[name] = f"failed ({type(e).__name__})"
                    with self.db:  # count -1: tried; retried on the next refresh, not on every call
                        self.db.execute("INSERT OR IGNORE INTO map_meta VALUES(?,?,?)", (name, time.time(), -1))
                    return
                self.replace(name, entries)
                stats[name] = len(entries)

            await asyncio.gather(*(run(n) for n in (only or self.builders)))
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
        own = term_regex([alts[:1] for alts in groups])  # the user's own words, no synonyms

        def hits(text: str, patterns: list[re.Pattern[str]] = pats) -> int:
            text = fold(text)
            return sum(bool(p.search(text)) for p in patterns)

        ranked = []
        for r in self.db.execute(sql, params):
            r = dict(r)
            text = f"{r['title']} {r['path']} {r['keywords']}"
            key = (-hits(text), -hits(text, own), -hits(r["title"]), -hits(r["title"], own), r["score"])
            ranked.append((key, r))
        ranked.sort(key=lambda t: t[0])
        return [{**r, "coverage": -k[0] / len(groups)} for k, r in ranked]

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
