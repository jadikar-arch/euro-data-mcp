"""GovData (ckan.govdata.de): Germany's open data catalogue (CKAN 2.10 + DCAT-AP.de); metadata only."""

from __future__ import annotations

import re
from typing import Any

from fastmcp import FastMCP

from ...common import READ_ONLY, NotFound, UserError, cell, clip, compact_table, fold, safe, source_line
from ...preview import preview
from ...web import Memo, fetch_json
from . import SYNONYMS

API = "https://ckan.govdata.de/api/3/action"
PORTAL = "https://www.govdata.de/suche/daten"
EU_FILE_TYPE = "http://publications.europa.eu/resource/authority/file-type/"
LEVEL_URI = "http://dcat-ap.de/def/politicalGeocoding/Level/"
DESTATIS = "statistisches-bundesamt"
TABLE_ID = re.compile(r"/tables/(\d{5}-\d{4}[A-Za-z]?)_")
ORGS = Memo(ttl=24 * 3600)

# DCAT-AP data themes, as GovData's 13 groups: code → (German title, English title).
THEMES = {
    "envi": ("Umwelt", "Environment"),
    "regi": ("Regionen und Städte", "Regions and cities"),
    "gove": ("Regierung und öffentlicher Sektor", "Government and public sector"),
    "econ": ("Wirtschaft und Finanzen", "Economy and finance"),
    "tech": ("Wissenschaft und Technologie", "Science and technology"),
    "soci": ("Bevölkerung und Gesellschaft", "Population and society"),
    "agri": (
        "Landwirtschaft, Fischerei, Forstwirtschaft und Nahrungsmittel",
        "Agriculture, fisheries, forestry and food",
    ),
    "educ": ("Bildung, Kultur und Sport", "Education, culture and sport"),
    "tran": ("Verkehr", "Transport"),
    "ener": ("Energie", "Energy"),
    "heal": ("Gesundheit", "Health"),
    "just": ("Justiz, Rechtssystem und öffentliche Sicherheit", "Justice, legal system and public safety"),
    "intr": ("Internationale Themen", "International issues"),
}
LEVELS = {
    "federal": "federal",
    "bund": "federal",
    "national": "federal",
    "state": "state",
    "land": "state",
    "district": "administrativeDistrict",
    "kreis": "administrativeDistrict",
    "administrativedistrict": "administrativeDistrict",
    "municipality": "municipality",
    "gemeinde": "municipality",
    "city": "municipality",
    "international": "international",
    "european": "european",
}


async def ckan(action: str, **params: Any) -> Any:
    data = await fetch_json(f"{API}/{action}", params)
    if not (data or {}).get("success"):
        raise UserError(f"GovData {action} failed: {((data or {}).get('error') or {}).get('message', '')}")
    return data["result"]


async def organizations() -> dict[str, dict[str, Any]]:
    """Publisher slug → {'title', 'count'}; cached."""

    async def load():
        rows = await ckan("organization_list", all_fields="true", limit=1000)
        return {r["name"]: {"title": r.get("title") or r["name"], "count": r.get("package_count", 0)} for r in rows}

    return await ORGS.get("all", load)


def short_format(f: str) -> str:
    return f.removeprefix(EU_FILE_TYPE).removesuffix("_SRVC").upper()


def table_id(identifier: str) -> str:
    """Destatis GENESIS table id from a dataset identifier/URL, or ''. Judged by the URL, not the
    publisher: GovData also lists Destatis tables under other organisations (e.g. mcloud)."""
    if "destatis.de/" not in identifier:
        return ""
    m = TABLE_ID.search(f"{identifier}_")
    return m.group(1) if m else ""


def resolve_theme(theme: str) -> str:
    key = fold(theme).strip()
    for code, (de, en) in THEMES.items():
        if key in (code, fold(de), fold(en)) or fold(de).startswith(key) or fold(en).startswith(key):
            return code
    raise UserError(f"Unknown theme '{theme}'. Valid: " + ", ".join(f"{c} ({en})" for c, (_, en) in THEMES.items()))


async def resolve_publisher(publisher: str) -> str:
    orgs = await organizations()
    key = fold(publisher).strip()
    if key in orgs:
        return key
    hits = [n for n, o in orgs.items() if key in fold(n) or key in fold(o["title"])]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise UserError(f"Unknown publisher '{publisher}'. Try part of a name, e.g. 'bayern' or 'statistisches'.")
    hits.sort(key=lambda n: -orgs[n]["count"])
    raise UserError(
        f"Publisher '{publisher}' is ambiguous: " + ", ".join(f"{n} ({orgs[n]['title']})" for n in hits[:6])
    )


def solr_query(query: str) -> str:
    """'population berlin' → 'text:(population OR bevölkerung OR einwohner) AND text:(berlin) AND
    (title:(…)^5 OR *:*)'. Bare OR groups are mangled by CKAN's min-match setting, and fielded
    queries skip its title boost, so the last clause boosts title matches without filtering."""
    groups, words = [], []
    for word in re.findall(r"\w+", query.lower()):
        alts = list(dict.fromkeys([word, *SYNONYMS.get(word, ()), *SYNONYMS.get(word.removesuffix("s"), ())]))
        groups.append("text:(" + " OR ".join(alts) + ")")
        words += alts
    if not groups:
        return "*:*"
    return " AND ".join(groups) + " AND (title:(" + " OR ".join(words) + ")^5 OR *:*)"


@safe
async def govdata_search(
    query: str,
    theme: str | None = None,
    publisher: str | None = None,
    format: str | None = None,
    level: str | None = None,
    page: int = 0,
    limit: int = 10,
) -> str:
    """Search Germany's open data catalogue (168k datasets; German titles, English terms are translated).
    theme: e.g. 'envi'/'Environment'; publisher: e.g. 'bayern'; format: e.g. 'CSV';
    level: federal/state/district/municipality. Details: govdata_dataset."""
    fq = []
    if theme:
        fq.append(f"groups:{resolve_theme(theme)}")
    if publisher:
        fq.append(f"organization:{await resolve_publisher(publisher)}")
    if format:
        f = re.sub(r"\W", "", format).upper()
        fq.append(f'res_format:("{f}" OR "{EU_FILE_TYPE}{f}" OR "{EU_FILE_TYPE}{f}_SRVC")')
    if level:
        lv = LEVELS.get(fold(level).strip())
        if not lv:
            raise UserError(f"Unknown level '{level}'. Valid: federal, state, district, municipality")
        fq.append(f'extras_politicalGeocodingLevelURI:"{LEVEL_URI}{lv}"')
    limit = max(1, min(limit, 30))
    res = await ckan(
        "package_search",
        q=solr_query(query),
        fq=" AND ".join(fq),
        rows=limit,
        start=max(0, page) * limit,
        fl="name,title,organization,res_format,extras_identifier,metadata_modified",
    )
    rows = res.get("results") or []
    if not rows:
        return f"No GovData datasets match '{query}'. Try German keywords or fewer filters."
    cols = ["id", "title", "publisher", "formats", "modified", "values"]
    table = []
    for r in rows:
        fmts = ",".join(dict.fromkeys(short_format(f) for f in r.get("res_format") or []))
        tid = table_id(r.get("identifier") or "")
        table.append(
            [
                r["name"],
                clip(r.get("title"), 100),
                r.get("organization") or "",
                clip(fmts, 40),
                str(r.get("metadata_modified") or "")[:10],
                f'govdata_table("{tid}")' if tid else "",
            ]
        )
    out = compact_table(cols, table, keep_last=False)
    total = res.get("count") or 0
    if total > (page + 1) * limit:
        out.append(f"# {len(rows)} of {total:,}; page={page + 1} for more, or add theme/publisher/format filters")
    return "\n".join(out)


def extras(d: dict[str, Any]) -> dict[str, str]:
    return {e["key"]: str(e.get("value") or "") for e in d.get("extras") or []}


@safe
async def govdata_dataset(dataset_id: str, max_files: int = 15) -> str:
    """Details of one GovData dataset: description, publisher, licence, coverage level and its files."""
    try:
        d = await ckan("package_show", id=dataset_id.strip())
    except NotFound:
        raise UserError(f"Unknown dataset '{dataset_id}'. Use govdata_search.") from None
    ex = extras(d)
    org = d.get("organization") or {}
    tid = table_id(ex.get("identifier", ""))
    out = [f"{d['name']}: {d.get('title', '')}"]
    facts = {
        "publisher": ex.get("publisher_name") or org.get("title"),
        "themes": ", ".join(
            THEMES.get(g["name"], (g.get("display_name", g["name"]), ""))[1] or g["name"] for g in d.get("groups") or []
        ),
        "level": ex.get("politicalGeocodingLevelURI", "").removeprefix(LEVEL_URI),
        "licence": d.get("license_title")
        or next((r.get("license") for r in d.get("resources") or [] if r.get("license")), ""),
        "issued": ex.get("issued", "")[:10],
        "modified": (ex.get("modified") or d.get("metadata_modified", ""))[:10],
        "frequency": ex.get("frequency", "").rsplit("/", 1)[-1],
        "tags": ", ".join(t["name"] for t in (d.get("tags") or [])[:12]),
        "portal": f"{PORTAL}/{d['name']}",
        "values": f'govdata_table("{tid}")' if tid else "",
    }
    out += [f"{k}: {cell(v)}" for k, v in facts.items() if v]
    out.append(f"description: {clip(d.get('notes'), 600)}")
    files = d.get("resources") or []
    if files:
        out.append("files (n|format|name|url); first rows: govdata_preview(id, file=n):")
        for i, r in enumerate(files[:max_files], 1):
            out.append(
                "|".join(
                    cell(v)
                    for v in (
                        i,
                        short_format(r.get("format") or ""),
                        clip(r.get("name") or r.get("description"), 60),
                        r.get("url", ""),
                    )
                )
            )
        if len(files) > max_files:
            out.append(f"# {max_files} of {len(files)} files")
    return "\n".join(out)


@safe
async def govdata_preview(dataset_id: str, file: int = 1, limit: int = 20) -> str:
    """First rows of a CSV or JSON file of a GovData dataset (file = n from govdata_dataset).
    Use it to see columns before downloading; Destatis tables: use govdata_table."""
    try:
        d = await ckan("package_show", id=dataset_id.strip())
    except NotFound:
        raise UserError(f"Unknown dataset '{dataset_id}'. Use govdata_search.") from None
    files = d.get("resources") or []
    if not 1 <= file <= len(files):
        raise UserError(f"file must be 1..{len(files)}; see govdata_dataset('{d['name']}').")
    r = files[file - 1]
    url, fmt = r.get("url") or "", short_format(r.get("format") or "")
    if tid := table_id(url):
        return f'This is Destatis table {tid}; use govdata_table("{tid}") for its values.'
    out = await preview(f"{d['name']} file {file}", url, fmt, limit)
    licence = r.get("license") or d.get("license_title") or "see dataset"
    out.append(source_line(url, licence))
    return "\n".join(out)


def register(mcp: FastMCP) -> None:
    for fn in (govdata_search, govdata_dataset, govdata_preview):
        mcp.tool(annotations=READ_ONLY, output_schema=None)(fn)
