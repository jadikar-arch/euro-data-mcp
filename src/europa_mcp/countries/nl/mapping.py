"""find_data map entries for the Netherlands: active CBS tables from the local CBS index."""

from __future__ import annotations

from ...common import UserError, clip
from ...sourcemap import Entry
from . import cbs
from .index import Index


def cbs_entries(index: Index) -> list[Entry]:
    rows = index.db.execute(
        "SELECT id, title, description, period, substr(modified,1,10) AS m, terms FROM datasets "
        "WHERE status='Regulier'"
    )
    return [
        {
            "source": "CBS", "id": r["id"], "title": r["title"] or "", "path": "",
            "keywords": f"{(r['terms'] or '')[:1500]} {clip(r['description'], 300)}",
            "period": r["period"] or "", "updated": r["m"] or "", "call": f'cbs_describe("{r["id"]}")',
        }
        for r in rows
    ]


async def build_cbs() -> list[Entry]:
    if not await cbs.wait_for_index(timeout=60):
        raise UserError("CBS index is not built yet")
    return cbs_entries(cbs.get_index())
