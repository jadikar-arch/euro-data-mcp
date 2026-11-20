"""find_data map entries for the Netherlands: one row per regular CBS table (~1,300).

Keywords come from the table's description plus its dimension and measure titles (two small
requests per table, run concurrently once per map build); the discontinued tables (~3,600) are left
out, `cbs_search(include_discontinued=true)` still finds them.
"""

from __future__ import annotations

import asyncio
import logging

from ...common import clip
from ...sourcemap import HEADLINE_END, HEADLINE_MARK, Entry
from . import HINTS, cbs

log = logging.getLogger("europa_mcp")

CONCURRENCY = 8


async def titles_of(ds: dict, sem: asyncio.Semaphore) -> str:
    """Dimension and measure titles of one table, '' when CBS does not answer."""
    async with sem:
        try:
            dims, meas = await asyncio.gather(
                cbs.ds_rows(ds, "Dimensions", {"$select": "Title"}),
                cbs.ds_rows(ds, "MeasureCodes", {"$select": "Title"}),
            )
        except Exception as e:  # noqa: BLE001  (one broken table must not fail the whole map)
            log.warning("CBS details for %s skipped: %s", ds["id"], e)
            return ""
    titles = [(r.get("Title") or "").strip() for r in [*dims[0], *meas[0]]]
    return "; ".join(dict.fromkeys(t for t in titles if t))[:2000]


async def build_cbs() -> list[Entry]:
    rows = [r for r in await cbs.catalog() if r["status"] == "Regulier"]
    sem = asyncio.Semaphore(CONCURRENCY)
    terms = await asyncio.gather(*(titles_of(r, sem) for r in rows))
    headline = HINTS["headline"].get("CBS", {})
    return [
        {
            "source": "CBS",
            "id": r["id"],
            "title": r["title"],
            "path": "",
            "keywords": " ".join(
                [
                    f"{HEADLINE_MARK} {headline[r['id']]} {HEADLINE_END}" if r["id"] in headline else "",
                    t,
                    clip(r["body"], 300),
                ]
            ).strip(),
            "period": r["period"],
            "updated": r["modified"],
            "call": f'cbs_describe("{r["id"]}")',
        }
        for r, t in zip(rows, terms, strict=True)
    ]
