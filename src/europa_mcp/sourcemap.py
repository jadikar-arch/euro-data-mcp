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
    period TEXT, updated TEXT, call TEXT, builder TEXT NOT NULL, detail TEXT DEFAULT '',
    PRIMARY KEY(source, id));
CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
    source UNINDEXED, id UNINDEXED, title, path, keywords, builder UNINDEXED,
    tokenize='unicode61 remove_diacritics 2');
CREATE TABLE IF NOT EXISTS map_meta(source TEXT PRIMARY KEY, built REAL, count INTEGER);
"""
CANDIDATES = 600
# Headline span in an entry's keywords: "zqheadline <everyday words> zqend". The entry ranks first
# when those words alone answer the query ('unemployment rate' → une_rt_m), not merely when its title
# does ('Part-time employment rate' is not the answer to 'employment rate'). Made-up tokens:
# Eurostat theme paths contain "Headline indicators", so a real word would collide.
HEADLINE_MARK, HEADLINE_END = "zqheadline", "zqend"
HEADLINE_SPAN = re.compile(rf"\b{HEADLINE_MARK}\b(.*?)\b{HEADLINE_END}\b")
PREFIX_MIN = 6  # shorter terms match whole words only ('house' must not match 'household')
# Long terms that would prefix-match a different word: 'capita' is not 'capital'.
WHOLE_WORD = {"capita"}

Entry = dict[str, str]
Builder = Callable[[], Awaitable[list[Entry]]]


def words_of(s: str) -> str:
    """'pigmeat/cuts/prices' / 'rawMilk' → 'pigmeat cuts prices' / 'raw milk rawmilk'."""
    s = s.replace("/", " ").replace("-", " ").replace("_", " ")
    split = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", s)
    return f"{split} {s}".lower() if split != s else s.lower()


def keyword_hint(kw: dict[str, str], source: str, ident: str) -> str:
    return " ".join(v for k, v in kw.items() if k.startswith(source + ":") and ident.startswith(k.split(":", 1)[1]))


# ---- the map ----------------------------------------------------------------------------


RND = re.compile(r"\br\s*&\s*d\b")  # 'R&D' would tokenise into the useless letters r and d


def expand(query: str, synonyms: dict[str, list[str]]) -> list[list[str]]:
    """Query → OR-groups of terms, each the query word plus its synonyms (see merge_synonyms).
    Multi-word synonym keys ('air quality', 'per capita') are matched as one phrase first."""
    q = " " + " ".join(re.findall(r"\w+", RND.sub(" research development ", fold(query)))) + " "
    for phrase in sorted((k for k in synonyms if " " in k), key=len, reverse=True):
        q = q.replace(f" {phrase} ", f" {phrase.replace(' ', '_')} ")
    groups = []
    for tok in q.split():
        if "_" in tok:  # a phrase
            phrase = tok.replace("_", " ")
            groups.append(list(dict.fromkeys(fold(a) for a in [phrase, *synonyms[phrase]] if a)))
            continue
        if len(tok) < 2 or tok in STOPWORDS:
            continue
        alts = [tok, *synonyms.get(tok, ())]
        alts += synonyms.get(tok[:-1], ()) if tok.endswith("s") else synonyms.get(tok + "s", ())
        groups.append(list(dict.fromkeys(fold(a) for a in alts if a)))
    return groups


def stem(a: str) -> str:
    """Long single words lose a plural ending so the prefix match also finds the singular:
    'bankruptcies' → 'bankruptc' (bankruptcy), 'homicides' → 'homicide'."""
    if " " in a or len(a) < PREFIX_MIN or a in WHOLE_WORD:
        return a
    if a.endswith("ies"):  # 'cities' stays whole: 'cit*' would match far too much
        return a[:-3] if len(a) - 3 >= 5 else a
    if a.endswith("s") and not a.endswith(("ss", "us", "is")) and len(a) - 1 >= 5:
        return a[:-1]
    return a


def short_forms(a: str) -> list[str]:
    """Whole-word variants of a short term: city → city, citys, cityes, cities."""
    return [a, f"{a}s", f"{a}es", *([f"{a[:-1]}ies"] if a.endswith("y") else [])]


def prefix(a: str) -> bool:
    return len(a) >= PREFIX_MIN and a not in WHOLE_WORD


def fts_term(a: str) -> str:
    if prefix(a):
        return f'"{stem(a)}"*'
    return "(" + " OR ".join(f'"{f}"' for f in short_forms(a)) + ")"


def term_regex(groups: list[list[str]]) -> list[re.Pattern[str]]:
    """One regex per query group, matching like fts_term (word start; whole word if short)."""
    pats = []
    for alts in groups:
        parts = [
            re.escape(stem(a)) if prefix(a) else "(?:" + "|".join(map(re.escape, short_forms(a))) + r")\b" for a in alts
        ]
        pats.append(re.compile(r"\b(?:" + "|".join(parts) + ")"))
    return pats


def demoted(entry: dict[str, Any], this_year: int) -> bool:
    """Rarely what a user wants: EU-neighbourhood (ENP) copies and discontinued datasets."""
    if entry["id"].lower().startswith(("enpe_", "enps_")):
        return True
    return last_year(entry) < this_year - 3


def last_year(entry: dict[str, Any]) -> int:
    """Final year of an entry's period; 9999 when it has none (live APIs such as Agrifood)."""
    years = re.findall(r"(?:19|20)\d\d", entry.get("period") or "")
    return int(years[-1]) if years else 9999


# Questions where recency matters most: prices and "latest/current" figures. For these, live
# sources (Agrifood weekly prices) beat annual tables that ended years ago.
FRESH_INTENT = re.compile(
    r"\b(?:prices?|prix|preise?|precios?|prezz[io]|prijz?e?n?|latest|current|newest|recent|now|today|this week)\b"
)


def negated(title: str, words: list[str]) -> bool:
    """The title has a query word only in negated form: 'non-household' for 'households'."""
    t = fold(title)
    return any(not w.startswith("non") and re.search(rf"\bnon[- ]?{re.escape(stem(w))}", t) for w in words)


def merge_synonyms(
    to_local: Iterable[dict[str, Iterable[str]]], extra: Iterable[dict[str, Iterable[str]]]
) -> dict[str, list[str]]:
    """English → local-language lists apply both ways (a Dutch query also finds English titles);
    `extra` (hints.json synonyms) apply as written."""
    syn: dict[str, list[str]] = {}
    for table in to_local:
        for en, local in table.items():
            syn.setdefault(fold(en), []).extend(local)
            for word in local:  # keys folded like query tokens ('bevölkerung' → 'bevolkerung')
                syn.setdefault(fold(word), []).append(en)
    for table in extra:
        for k, v in table.items():
            syn.setdefault(fold(k), []).extend(v)
    return syn


class SourceMap:
    def __init__(
        self,
        path: Path | str | None = None,
        synonyms: dict[str, list[str]] | None = None,
        builders: dict[str, Builder] | None = None,
    ):
        self.path = Path(path) if path else cache_dir() / "sourcemap.db"
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        if "detail" not in {r[1] for r in self.db.execute("PRAGMA table_info(entries)")}:  # pre-0.4 cache
            with self.db:  # add the column and forget the builds, so the next ensure() refills it
                self.db.execute("ALTER TABLE entries ADD COLUMN detail TEXT DEFAULT ''")
                self.db.execute("DELETE FROM map_meta")
        self._lock = asyncio.Lock()
        self.synonyms = synonyms or {}
        self.builders = builders or {}
        self.prune()

    def count(self, source: str | None = None) -> int:
        if source:
            return self.db.execute("SELECT count(*) FROM entries WHERE source=?", (source,)).fetchone()[0]
        return self.db.execute("SELECT count(*) FROM entries").fetchone()[0]

    def prune(self) -> int:
        """Drop rows of builders this server no longer has (e.g. a removed country), so find_data
        never points to tools that don't exist. Returns the number of rows removed."""
        if not self.builders:
            return 0
        known = list(self.builders)
        marks = ",".join("?" * len(known))
        with self.db:
            n = self.db.execute(f"DELETE FROM entries WHERE builder NOT IN ({marks})", known).rowcount
            self.db.execute(f"DELETE FROM entries_fts WHERE builder NOT IN ({marks})", known)
            self.db.execute(f"DELETE FROM map_meta WHERE source NOT IN ({marks})", known)
        if n:
            log.info("source map: removed %d rows of retired sources", n)
        return n

    def missing(self) -> list[str]:
        """Builders that have never run (or failed) against this database."""
        done = {r[0] for r in self.db.execute("SELECT source FROM map_meta")}
        return [b for b in self.builders if b not in done]

    def failed(self, older_than: float = 0.0) -> list[str]:
        """Builders whose last run failed (marked count -1) at least `older_than` seconds ago."""
        cutoff = time.time() - older_than
        rows = self.db.execute("SELECT source FROM map_meta WHERE count = -1 AND built <= ?", (cutoff,))
        return [r[0] for r in rows if r[0] in self.builders]

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
                kw = e.get("keywords", "")
                if RND.search(fold(e.get("title", ""))):
                    kw += " research development"
                row = (e["source"], e["id"], e.get("title", ""), e.get("path", ""), kw)
                self.db.execute(
                    "INSERT OR REPLACE INTO entries(source, id, title, path, keywords, period, updated, call,"
                    " builder, detail) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (*row, e.get("period", ""), e.get("updated", ""), e.get("call", ""), builder, e.get("detail", "")),
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
        # Headline datasets always reach the reranking, even when a broad word ('employment')
        # matches thousands of titles that crowd them out of the bm25 candidates.
        headline_params = [f"keywords:{HEADLINE_MARK} AND ({expr})", *params[1:]]

        pats = term_regex(groups)
        own = term_regex([alts[:1] for alts in groups])  # the user's own words, no synonyms
        own_words = [alts[0] for alts in groups]
        fresh = bool(FRESH_INTENT.search(fold(query)))

        def hits(text: str, patterns: list[re.Pattern[str]] = pats) -> int:
            text = fold(text)
            return sum(bool(p.search(text)) for p in patterns)

        ranked, seen, this_year = [], set(), time.gmtime().tm_year
        rows = [*self.db.execute(sql, params), *self.db.execute(sql, headline_params)]
        for r in rows:
            r = dict(r)
            if (r["source"], r["id"]) in seen:
                continue
            seen.add((r["source"], r["id"]))
            text = f"{r['title']} {r['path']} {r['keywords']}"
            covered = hits(text)
            words = r["keywords"].split()
            span = HEADLINE_SPAN.search(r["keywords"])
            headline = covered == len(groups) and span is not None and hits(span.group(1)) == len(groups)
            main_table = "table" in words[:3]  # Eurostat's own curated key-indicator tables
            key = (
                -covered,
                negated(r["title"], own_words),
                -headline,
                demoted(r, this_year),
                fresh and last_year(r) < this_year - 1,  # price/latest questions: ended over a year ago
                -hits(text, own),
                -hits(r["title"]),
                -main_table,
                -hits(r["title"], own),
                r["score"],
            )
            ranked.append((key, r))
        ranked.sort(key=lambda t: t[0])
        return [{**r, "coverage": -k[0] / len(groups)} for k, r in ranked]

    def export(self, out: Path) -> int:
        rows = self.db.execute(
            "SELECT source, id, title, path, period, updated, call, detail, keywords FROM entries ORDER BY source, id"
        )
        with out.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(
                ["source", "id", "title", "topic_path", "period", "updated", "next_call", "breakdowns", "keywords"]
            )
            n = 0
            for r in rows:
                w.writerow([*tuple(r)[:8], clip(r["keywords"], 500)])
                n += 1
        return n
