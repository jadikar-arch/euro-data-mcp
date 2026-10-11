"""Local SQLite FTS5 index of the CBS dataset catalog.

The CBS API has no ranked or fuzzy search (`$search` is ignored), so we mirror the
catalog locally and keep it current by diffing each dataset's `Version`.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import sqlite3
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from ...common import STOPWORDS, NotFound, UserError, cache_dir, fold
from .client import eq_any, get_rows

log = logging.getLogger("europa_mcp")

CATALOG_FIELDS = "Identifier,Catalog,Version,Title,Description,Status,Modified,ObservationCount"
BULK_THRESHOLD = 200  # above this many changes, refetch the whole catalog in one request
BATCH = 40  # ids per `$filter` request
DETAIL_CONCURRENCY = 8
CANDIDATES = 400  # FTS candidates reranked in Python

SCHEMA = """
CREATE TABLE IF NOT EXISTS datasets(
    id TEXT PRIMARY KEY, id_lc TEXT NOT NULL, catalog TEXT NOT NULL, version TEXT,
    title TEXT, description TEXT, period TEXT, status TEXT, modified TEXT,
    obs_count INTEGER, terms TEXT DEFAULT '', details_version TEXT);
CREATE INDEX IF NOT EXISTS ix_datasets_lc ON datasets(id_lc);
CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(
    id UNINDEXED, title, description, terms, tokenize='unicode61 remove_diacritics 2');
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
"""

# English → Dutch for common statistics terms (the catalog is Dutch-only).
SYNONYMS: dict[str, tuple[str, ...]] = {
    "population": ("bevolking", "inwoners"), "inhabitants": ("inwoners", "bevolking"),
    "people": ("personen", "bevolking"), "births": ("geboorte", "geborenen"),
    "deaths": ("overledenen", "sterfte"), "mortality": ("sterfte",), "migration": ("migratie",),
    "immigration": ("immigratie",), "emigration": ("emigratie",), "age": ("leeftijd",),
    "gender": ("geslacht",), "sex": ("geslacht",), "households": ("huishoudens",),
    "household": ("huishoudens",), "income": ("inkomen",), "wages": ("lonen",),
    "salary": ("lonen",), "employment": ("werkgelegenheid", "werkzame"),
    "unemployment": ("werkloosheid", "werkloze"), "jobs": ("banen",), "labour": ("arbeid",),
    "labor": ("arbeid",), "housing": ("woningen", "woon"), "houses": ("woningen", "koopwoningen"),
    "homes": ("woningen",), "dwellings": ("woningen",), "rent": ("huur",),
    "prices": ("prijzen", "prijs", "verkoopprijzen"), "inflation": ("inflatie", "cpi"),
    "consumer": ("consumenten",), "energy": ("energie",), "gas": ("aardgas", "gas"),
    "electricity": ("elektriciteit",), "emissions": ("emissies",), "environment": ("milieu",),
    "education": ("onderwijs",), "students": ("studenten", "leerlingen"),
    "health": ("gezondheid",), "healthcare": ("zorg",), "crime": ("criminaliteit", "misdrijven"),
    "traffic": ("verkeer",), "transport": ("vervoer", "verkeer"), "cars": ("personenauto",),
    "tourism": ("toerisme",), "hotels": ("logies",), "trade": ("handel",),
    "exports": ("uitvoer", "export"), "imports": ("invoer", "import"), "economy": ("economie",),
    "gdp": ("bbp", "bruto"), "government": ("overheid",), "debt": ("schuld",),
    "companies": ("bedrijven",), "businesses": ("bedrijven",), "bankruptcies": ("faillissementen",),
    "agriculture": ("landbouw",), "municipality": ("gemeente",), "municipalities": ("gemeenten",),
    "region": ("regio",), "regional": ("regio",), "province": ("provincie",),
    "neighbourhood": ("wijken", "buurten"), "neighborhood": ("wijken", "buurten"),
    "monthly": ("maand",), "quarterly": ("kwartaal",), "yearly": ("jaar",), "annual": ("jaar",),
    "social": ("sociale",), "benefits": ("uitkeringen",), "pensions": ("pensioen",),
    "religion": ("religie",), "elections": ("verkiezingen",), "construction": ("bouw",),
}


_PERIOD = re.compile(
    r"Gegevens beschikbaar\s*(?:vanaf|van|over|tot|per)?\s*:?\s*([^\n\r]+)", re.IGNORECASE
)


def parse_description(text: str | None) -> tuple[str, str]:
    """Split a CBS description into (body without boilerplate, period)."""
    text = text or ""
    m = _PERIOD.search(text)
    period = m.group(1).strip().rstrip(".")[:60] if m else ""
    body = text[: m.start()] if m else text
    body = re.sub(r"\s+", " ", body).strip()
    return body[:1500], period


def summarize(body: str, n: int = 300) -> str:
    if len(body) <= n:
        return body
    return body[:n].rsplit(" ", 1)[0] + "…"


def default_path() -> Path:
    env = os.environ.get("CBS_INDEX_PATH")
    return Path(env) if env else cache_dir() / "nl-cbs.db"



def query_groups(query: str) -> list[list[str]]:
    """Tokenize a free-text query into OR-groups of FTS terms (synonyms expanded)."""
    groups = []
    for tok in re.findall(r"\w+", fold(query)):
        if len(tok) < 2 or tok in STOPWORDS:
            continue
        syn = SYNONYMS.get(tok) or (SYNONYMS.get(tok[:-1], ()) if tok.endswith("s") else ())
        if not syn and tok + "s" in SYNONYMS:
            syn = SYNONYMS[tok + "s"]
        alts = [tok, *syn]
        groups.append(list(dict.fromkeys(alts)))
    return groups


def fts_expr(groups: list[list[str]], op: str) -> str:
    parts = []
    for alts in groups:
        terms = " OR ".join(f'"{a}"*' for a in alts)
        parts.append(f"({terms})" if len(alts) > 1 else terms)
    return f" {op} ".join(parts)


class Index:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else default_path()
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)
        self.ready = asyncio.Event()
        if self.count():
            self.ready.set()
        self._lock = asyncio.Lock()

    # ---- reads -----------------------------------------------------------

    def count(self) -> int:
        return self.db.execute("SELECT count(*) FROM datasets").fetchone()[0]

    def last_sync(self) -> float:
        row = self.db.execute("SELECT value FROM meta WHERE key='last_sync'").fetchone()
        return float(row[0]) if row else 0.0

    def get(self, dataset_id: str) -> dict[str, Any] | None:
        row = self.db.execute(
            "SELECT * FROM datasets WHERE id_lc=?", (dataset_id.lower(),)
        ).fetchone()
        return dict(row) if row else None

    def titles(self, ids: Iterable[str]) -> dict[str, str]:
        ids = list(ids)
        if not ids:
            return {}
        marks = ",".join("?" * len(ids))
        rows = self.db.execute(f"SELECT id, title FROM datasets WHERE id IN ({marks})", ids)
        return {r["id"]: r["title"] for r in rows}

    def search(
        self, query: str, catalog: str = "CBS", include_discontinued: bool = False, limit: int = 10
    ) -> tuple[list[dict[str, Any]], int]:
        """Ranked search. Returns (rows, total matches).

        FTS (OR of all terms, bm25) picks candidates; they are then reranked by how many
        query terms occur in the title, then anywhere, then bm25 × status × recency.
        Rare words that only appear in descriptions (e.g. a city name) can't dominate.
        """
        groups = query_groups(query)
        if not groups:
            return [], 0
        where = "fts MATCH ? AND d.catalog = ?"
        if not include_discontinued:
            where += " AND d.status = 'Regulier'"
        expr = fts_expr(groups, "OR")
        # bm25 is negative (lower = better): status and recency factors scale it.
        sql = f"""
            SELECT d.id, d.title, d.period, d.status, substr(d.modified, 1, 10) AS modified,
                   d.description, d.terms,
                   bm25(fts, 0.0, 10.0, 1.0, 1.5)
                   * CASE d.status WHEN 'Regulier' THEN 1.0 ELSE 0.35 END
                   * (1.0 + 0.03 * max(0, min(12, CAST(substr(d.modified, 1, 4) AS INT) - 2014)))
                   AS score
            FROM fts JOIN datasets d ON d.id = fts.id
            WHERE {where} ORDER BY score LIMIT {CANDIDATES}"""
        total = self.db.execute(
            f"SELECT count(*) FROM fts JOIN datasets d ON d.id = fts.id WHERE {where}",
            (expr, catalog),
        ).fetchone()[0]
        folded = [[fold(a) for a in alts] for alts in groups]

        def hits(text: str) -> int:
            text = fold(text)
            return sum(any(a in text for a in alts) for alts in folded)

        ranked = []
        for r in self.db.execute(sql, (expr, catalog)):
            title_hits = hits(r["title"] or "")
            any_hits = hits(f"{r['title']} {r['description']} {r['terms']}")
            ranked.append((-title_hits, -any_hits, r["score"], dict(r)))
        ranked.sort(key=lambda t: t[:3])
        out = []
        for *_, r in ranked[:limit]:
            r.pop("description"), r.pop("terms"), r.pop("score")
            out.append(r)
        return out, total

    # ---- writes ----------------------------------------------------------

    def _upsert(self, row: dict[str, Any]) -> None:
        body, period = parse_description(row.get("Description"))
        ident = row["Identifier"]
        self.db.execute(
            """INSERT INTO datasets(id, id_lc, catalog, version, title, description, period,
                   status, modified, obs_count)
               VALUES(?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET catalog=excluded.catalog,
                   version=excluded.version, title=excluded.title,
                   description=excluded.description, period=excluded.period,
                   status=excluded.status, modified=excluded.modified,
                   obs_count=excluded.obs_count""",
            (
                ident, ident.lower(), row.get("Catalog") or "CBS", row.get("Version"),
                (row.get("Title") or "").strip(), body, period, row.get("Status"),
                row.get("Modified"), row.get("ObservationCount"),
            ),
        )
        self._reindex(ident)

    def _reindex(self, ident: str) -> None:
        self.db.execute("DELETE FROM fts WHERE id=?", (ident,))
        self.db.execute(
            "INSERT INTO fts(id, title, description, terms) "
            "SELECT id, title, description, terms FROM datasets WHERE id=?",
            (ident,),
        )

    def ingest(self, rows: Iterable[dict[str, Any]]) -> None:
        """Add/refresh catalog rows (e.g. a dataset found live but missing locally)."""
        with self.db:
            for row in rows:
                self._upsert(row)
        if self.count():
            self.ready.set()

    def remove(self, dataset_id: str) -> None:
        with self.db:
            row = self.db.execute(
                "SELECT id FROM datasets WHERE id_lc=?", (dataset_id.lower(),)
            ).fetchone()
            if row:
                self.db.execute("DELETE FROM datasets WHERE id=?", (row[0],))
                self.db.execute("DELETE FROM fts WHERE id=?", (row[0],))

    # ---- sync ------------------------------------------------------------

    async def sync(
        self,
        full: bool = False,
        details: bool = True,
        on_change: Callable[[list[str]], None] | None = None,
    ) -> dict[str, int]:
        """Diff remote `Version`s against the index and fetch only what changed."""
        async with self._lock:
            remote, _ = await get_rows("/Datasets", {"$select": "Identifier,Catalog,Version"})
            if not remote:
                raise UserError("CBS catalog returned no datasets; keeping the current index")
            remote_ver = {r["Identifier"]: r.get("Version") for r in remote}
            local_ver = {
                r["id"]: r["version"] for r in self.db.execute("SELECT id, version FROM datasets")
            }
            changed = [i for i, v in remote_ver.items() if full or local_ver.get(i) != v]
            removed = [i for i in local_ver if i not in remote_ver]
            if len(removed) > max(10, 0.2 * len(local_ver)):
                log.warning("refusing to drop %d of %d datasets; skipping deletes",
                            len(removed), len(local_ver))
                removed = []

            rows = await self._fetch_catalog(changed)
            with self.db:
                for row in rows:
                    self._upsert(row)
                for ident in removed:
                    self.db.execute("DELETE FROM datasets WHERE id=?", (ident,))
                    self.db.execute("DELETE FROM fts WHERE id=?", (ident,))
                self.db.execute(
                    "INSERT OR REPLACE INTO meta VALUES('last_sync', ?)", (str(time.time()),)
                )
            if self.count():
                self.ready.set()
            if on_change and (changed or removed):
                on_change(changed + removed)
            log.info("index sync: %d changed, %d removed, %d total",
                     len(changed), len(removed), self.count())
            stats = {"changed": len(changed), "removed": len(removed), "total": self.count()}
            if details:
                stats["details"] = await self._sync_details()
            return stats

    async def _fetch_catalog(self, ids: list[str]) -> list[dict[str, Any]]:
        if not ids:
            return []
        if len(ids) > BULK_THRESHOLD:
            wanted = set(ids)
            rows, _ = await get_rows("/Datasets", {"$select": CATALOG_FIELDS})
            return [r for r in rows if r["Identifier"] in wanted]
        out: list[dict[str, Any]] = []
        for i in range(0, len(ids), BATCH):
            batch, _ = await get_rows(
                "/Datasets",
                {"$select": CATALOG_FIELDS, "$filter": eq_any("Identifier", ids[i : i + BATCH])},
            )
            out.extend(batch)
        return out

    async def _sync_details(self) -> int:
        """Index measure and dimension titles of active datasets whose version changed."""
        todo = [
            dict(r)
            for r in self.db.execute(
                "SELECT id, catalog, version FROM datasets WHERE status='Regulier' "
                "AND (details_version IS NULL OR details_version != version)"
            )
        ]
        if not todo:
            return 0
        log.info("indexing measures/dimensions for %d datasets", len(todo))
        sem = asyncio.Semaphore(DETAIL_CONCURRENCY)
        done = 0

        async def one(r: dict[str, Any]) -> None:
            nonlocal done
            base = f"/{r['catalog']}/{r['id']}"
            async with sem:
                try:
                    dims, _ = await get_rows(f"{base}/Dimensions", {"$select": "Title"})
                    meas, _ = await get_rows(f"{base}/MeasureCodes", {"$select": "Title"})
                except NotFound:
                    return
                except UserError as e:
                    log.warning("details for %s failed: %s", r["id"], e)
                    return
            titles = [d.get("Title") or "" for d in dims] + [m.get("Title") or "" for m in meas]
            terms = "; ".join(t.strip() for t in titles if t)[:4000]
            with self.db:
                self.db.execute(
                    "UPDATE datasets SET terms=?, details_version=? WHERE id=?",
                    (terms, r["version"], r["id"]),
                )
                self._reindex(r["id"])
            done += 1
            if done % 200 == 0:
                log.info("details: %d/%d", done, len(todo))

        await asyncio.gather(*(one(r) for r in todo))
        return done
