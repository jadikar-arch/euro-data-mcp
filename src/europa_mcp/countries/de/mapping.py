"""find_data map entries for Germany.

- Destatis: one row per GENESIS table (~3,150), keywords from its GovData tags.
- GovData: 168k datasets are too many for one row each, so the map describes *what kinds of data
  exist*: one row per theme and per theme × publisher (≥ MIN_DATASETS), with the top tags and file
  formats of that slice as keywords and a ready govdata_search call.
"""

from __future__ import annotations

import asyncio
import json

from ...sourcemap import Entry
from .govdata import DESTATIS, THEMES, ckan, organizations, short_format, table_id

PAGE = 1000
MIN_DATASETS = 20
MONTHS = set("januar februar märz april mai juni juli august september oktober november dezember".split())
NOISE = {"opendata", "open-data", "inspireidentifiziert", "national", "jahr", *THEMES}  # theme codes appear as tags too


async def build_destatis() -> list[Entry]:
    out: list[Entry] = []
    start, total = 0, 1
    while start < total:
        res = await ckan(
            "package_search",
            fq=f"organization:{DESTATIS}",
            rows=PAGE,
            start=start,
            sort="name asc",
            fl="name,title,tags,groups,extras_identifier,extras_modified,metadata_modified",
        )
        total = res["count"]
        start += PAGE
        for r in res["results"]:
            tid = table_id(r.get("identifier") or "")
            if not tid:
                continue
            themes = [THEMES[g][1] for g in r.get("groups") or [] if g in THEMES]
            tags = [t for t in r.get("tags") or [] if t not in MONTHS | NOISE]
            out.append(
                {
                    "source": "Destatis",
                    "id": tid,
                    "title": r.get("title") or "",
                    "path": "Destatis > " + " / ".join(themes) if themes else "Destatis",
                    "keywords": " ".join(tags)[:1200],
                    "period": "",
                    "updated": str(r.get("modified") or r.get("metadata_modified") or "")[:10],
                    "call": f'govdata_table("{tid}")',
                }
            )
    return out


def top(facet: dict, n: int) -> list[str]:
    items = sorted((i for i in facet.get("items") or [] if i["name"] not in NOISE), key=lambda i: -i["count"])
    return [i["name"] for i in items[:n]]


async def build_catalogue() -> list[Entry]:
    orgs = await organizations()
    sem = asyncio.Semaphore(8)

    async def facets(fq: str, fields: list[str], n: int = 80) -> dict:
        async with sem:
            res = await ckan("package_search", fq=fq, rows=0, **{"facet.field": json.dumps(fields), "facet.limit": n})
        return {"count": res["count"], **res["search_facets"]}

    themes = dict(
        zip(
            THEMES,
            await asyncio.gather(*(facets(f"groups:{g}", ["organization", "tags", "res_format"], 100) for g in THEMES)),
            strict=True,
        )
    )
    combos = [
        (g, o["name"]) for g, f in themes.items() for o in f["organization"]["items"] if o["count"] >= MIN_DATASETS
    ]
    slices = await asyncio.gather(
        *(facets(f"groups:{g} AND organization:{o}", ["tags", "res_format"]) for g, o in combos)
    )

    out: list[Entry] = []
    for g, f in themes.items():
        de, en = THEMES[g]
        publishers = [orgs.get(o, {}).get("title", o) for o in top(f["organization"], 8)]
        out.append(
            {
                "source": "GovData",
                "id": g,
                "title": f"{en} ({de}): {f['count']:,} datasets",
                "path": f"GovData > {en}",
                "keywords": " ".join([*top(f["tags"], 100), *publishers, *formats(f)]),
                "period": "",
                "updated": "",
                "call": f'govdata_search("<German keywords>", theme="{g}")',
            }
        )
    for (g, o), f in zip(combos, slices, strict=True):
        de, en = THEMES[g]
        title = orgs.get(o, {}).get("title", o)
        out.append(
            {
                "source": "GovData",
                "id": f"{g}/{o}",
                "title": f"{en} data from {title}: {f['count']:,} datasets",
                "path": f"GovData > {en} > {title}",
                "keywords": " ".join([de, *top(f["tags"], 80), *formats(f)]),
                "period": "",
                "updated": "",
                "call": f'govdata_search("<German keywords>", theme="{g}", publisher="{o}")',
            }
        )
    return out


def formats(f: dict) -> list[str]:
    return list(dict.fromkeys(short_format(x) for x in top(f.get("res_format") or {}, 10)))
