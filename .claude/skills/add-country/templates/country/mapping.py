"""find_data map entries for <Country name>."""

from __future__ import annotations

from ...sourcemap import Entry
from . import source


async def build_source() -> list[Entry]:
    """One entry per table; enrich keywords with whatever metadata the API offers."""
    return [
        {
            "source": "<SOURCE>",  # must match a key in hints.json "sources"
            "id": r["id"],
            "title": r["title"],
            "path": "",  # topic path if the API has a theme tree, e.g. "Economy > Prices"
            "keywords": "",  # dimension/measure names, code-list values, English translations
            "period": r["period"],
            "updated": r["updated"],
            "call": f'<source>_describe("{r["id"]}")',
        }
        for r in await source.catalog()
    ]
