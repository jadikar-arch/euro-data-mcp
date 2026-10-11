"""<SOURCE> (<API base URL>): <one line on what it serves>."""

from __future__ import annotations

from fastmcp import FastMCP

from ...common import READ_ONLY, UserError, cell, compact_table, fold, safe
from ...web import Memo, fetch_json

BASE = "<https://api.example/…>"
CATALOG = Memo(ttl=12 * 3600)


async def catalog() -> list[dict[str, str]]:
    """All tables as {'id', 'title', 'period', 'updated'}; cached."""

    async def load():
        data = await fetch_json(f"{BASE}/<catalogue endpoint>")
        return [{"id": r["<id>"], "title": r["<title>"], "period": "", "updated": ""} for r in data]

    return await CATALOG.get("all", load)


@safe
async def source_search(query: str, limit: int = 10) -> str:
    """Find <SOURCE> tables by topic (<language> keywords work best)."""
    words = fold(query).split()
    hits = [r for r in await catalog() if all(w in fold(r["title"]) for w in words)]
    if not hits:
        return f"No tables match '{query}'."
    lines = ["id|title|period|updated"] + [
        "|".join(cell(r[k]) for k in ("id", "title", "period", "updated")) for r in hits[:limit]
    ]
    if len(hits) > limit:
        lines.append(f"# {limit} of {len(hits)} matches; refine the query")
    return "\n".join(lines)


@safe
async def source_data(table_id: str, filters: dict[str, list[str]] | None = None, limit: int = 500) -> str:
    """Fetch values. filters = {dimension: [codes]}; constant columns are shown once."""
    if not filters:
        raise UserError("Add filters; see <source>_describe for dimensions and codes.")
    data = await fetch_json(f"{BASE}/<data endpoint>/{table_id}", {"<param>": "<value>"})
    cols, rows = ["<dim>", "value"], [[str(r["<dim>"]), str(r["value"])] for r in data][:limit]
    return "\n".join(compact_table(cols, rows)) or "No values for these filters."


def register(mcp: FastMCP) -> None:
    for fn in (source_search, source_data):  # rename to <source>_search, <source>_data, …
        mcp.tool(annotations=READ_ONLY, output_schema=None)(fn)
