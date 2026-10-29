"""GovData (ckan.govdata.de): Germany's open data catalogue (CKAN 2.10 + DCAT-AP.de); metadata only."""

from __future__ import annotations

import csv
import io
import ipaddress
import json
import re
from typing import Any
from urllib.parse import urlsplit

from fastmcp import FastMCP

from ...common import NotFound, READ_ONLY, UserError, cell, clip, compact_table, fold, safe
from ...web import Memo, fetch_json, fetch_prefix
from . import SYNONYMS

API = "https://ckan.govdata.de/api/3/action"
PORTAL = "https://www.govdata.de/suche/daten"
EU_FILE_TYPE = "http://publications.europa.eu/resource/authority/file-type/"
LEVEL_URI = "http://dcat-ap.de/def/politicalGeocoding/Level/"
DESTATIS = "statistisches-bundesamt"
TABLE_ID = re.compile(r"/tables/(\d{5}-\d{4}[A-Za-z]?)_")
PREVIEW_BYTES = 1_000_000
ORGS = Memo(ttl=24 * 3600)

# DCAT-AP data themes, as GovData's 13 groups: code → (German title, English title).
THEMES = {
    "envi": ("Umwelt", "Environment"),
    "regi": ("Regionen und Städte", "Regions and cities"),
    "gove": ("Regierung und öffentlicher Sektor", "Government and public sector"),
    "econ": ("Wirtschaft und Finanzen", "Economy and finance"),
    "tech": ("Wissenschaft und Technologie", "Science and technology"),
    "soci": ("Bevölkerung und Gesellschaft", "Population and society"),
    "agri": ("Landwirtschaft, Fischerei, Forstwirtschaft und Nahrungsmittel", "Agriculture, fisheries, forestry and food"),
    "educ": ("Bildung, Kultur und Sport", "Education, culture and sport"),
    "tran": ("Verkehr", "Transport"),
    "ener": ("Energie", "Energy"),
    "heal": ("Gesundheit", "Health"),
    "just": ("Justiz, Rechtssystem und öffentliche Sicherheit", "Justice, legal system and public safety"),
    "intr": ("Internationale Themen", "International issues"),
}
LEVELS = {
    "federal": "federal", "bund": "federal", "national": "federal", "state": "state", "land": "state",
    "district": "administrativeDistrict", "kreis": "administrativeDistrict",
    "administrativedistrict": "administrativeDistrict", "municipality": "municipality",
    "gemeinde": "municipality", "city": "municipality", "international": "international", "european": "european",
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
    """Destatis GENESIS table id from a dataset identifier/URL, or ''."""
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
    raise UserError(f"Publisher '{publisher}' is ambiguous: " + ", ".join(f"{n} ({orgs[n]['title']})" for n in hits[:6]))


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
    query: str, theme: str | None = None, publisher: str | None = None, format: str | None = None,
    level: str | None = None, page: int = 0, limit: int = 10,
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
        "package_search", q=solr_query(query), fq=" AND ".join(fq), rows=limit, start=max(0, page) * limit,
        fl="name,title,organization,res_format,extras_identifier,metadata_modified",
    )
    rows = res.get("results") or []
    if not rows:
        return f"No GovData datasets match '{query}'. Try German keywords or fewer filters."
    cols = ["id", "title", "publisher", "formats", "modified", "values"]
    table = []
    for r in rows:
        fmts = ",".join(dict.fromkeys(short_format(f) for f in r.get("res_format") or []))
        tid = table_id(r.get("identifier") or "") if r.get("organization") == DESTATIS else ""
        table.append([
            r["name"], clip(r.get("title"), 100), r.get("organization") or "", clip(fmts, 40),
            str(r.get("metadata_modified") or "")[:10], f'govdata_table("{tid}")' if tid else "",
        ])
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
    tid = table_id(ex.get("identifier", "")) if org.get("name") == DESTATIS else ""
    out = [f"{d['name']}: {d.get('title', '')}"]
    facts = {
        "publisher": ex.get("publisher_name") or org.get("title"),
        "themes": ", ".join(THEMES.get(g["name"], (g.get("display_name", g["name"]), ""))[1] or g["name"]
                            for g in d.get("groups") or []),
        "level": ex.get("politicalGeocodingLevelURI", "").removeprefix(LEVEL_URI),
        "licence": d.get("license_title") or next(
            (r.get("license") for r in d.get("resources") or [] if r.get("license")), ""),
        "issued": ex.get("issued", "")[:10], "modified": (ex.get("modified") or d.get("metadata_modified", ""))[:10],
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
            out.append("|".join(cell(v) for v in (
                i, short_format(r.get("format") or ""), clip(r.get("name") or r.get("description"), 60), r.get("url", ""),
            )))
        if len(files) > max_files:
            out.append(f"# {max_files} of {len(files)} files")
    return "\n".join(out)


def check_url(url: str) -> None:
    """Publisher-supplied URLs: only public http(s) hosts (the server may run hosted)."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https") or not host or host == "localhost":
        raise UserError(f"Can't preview '{url}'.")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return
    if not ip.is_global:
        raise UserError(f"Can't preview '{url}'.")


def decode(body: bytes) -> str:
    try:
        return body.decode("utf-8-sig")
    except UnicodeDecodeError:
        return body.decode("latin-1")


def csv_rows(text: str, truncated: bool) -> list[list[str]]:
    if truncated:
        text = text.rsplit("\n", 1)[0]  # drop the partial last line
    sample = text[:20000]
    try:
        delim = csv.Sniffer().sniff(sample, delimiters=";,\t|").delimiter
    except csv.Error:
        delim = ";" if sample.count(";") > sample.count(",") else ","
    return [r for r in csv.reader(io.StringIO(text), delimiter=delim) if any(c.strip() for c in r)]


def json_rows(data: Any) -> list[list[str]]:
    if isinstance(data, dict):
        if isinstance(data.get("features"), list):  # GeoJSON
            data = [f.get("properties") or {} for f in data["features"] if isinstance(f, dict)]
        else:
            data = next((v for v in data.values() if isinstance(v, list)), [data])
    items = [x for x in data if isinstance(x, dict)] if isinstance(data, list) else []
    if not items:
        raise UserError("JSON has no list of records to preview.")
    keys = list(dict.fromkeys(k for x in items[:50] for k in x))
    flat = lambda v: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else ("" if v is None else str(v))  # noqa: E731
    return [keys] + [[flat(x.get(k)) for k in keys] for x in items]


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
        return f"This is Destatis table {tid}; use govdata_table(\"{tid}\") for its values."
    kind = fmt if fmt in ("CSV", "TXT", "TSV", "JSON", "GEOJSON") else urlsplit(url).path.rsplit(".", 1)[-1].upper()
    if kind not in ("CSV", "TXT", "TSV", "JSON", "GEOJSON"):
        raise UserError(f"File {file} is {fmt or 'unknown format'}; only CSV/JSON can be previewed. Download: {url}")
    check_url(url)
    body, truncated, ctype = await fetch_prefix(url, PREVIEW_BYTES)
    if "html" in ctype and not body.lstrip().startswith((b"{", b"[")):
        raise UserError(f"File {file} is a web page, not data. Open: {url}")
    text = decode(body)
    if kind in ("JSON", "GEOJSON"):
        if truncated:
            raise UserError(f"JSON file is larger than {PREVIEW_BYTES // 1_000_000} MB; download it: {url}")
        try:
            rows = json_rows(json.loads(text))
        except ValueError:
            raise UserError("File is not valid JSON.") from None
    else:
        rows = csv_rows(text, truncated)
    if len(rows) < 2:
        raise UserError(f"File {file} has no rows to preview. Download: {url}")
    limit = max(1, min(limit, 50))
    header, data = rows[0], rows[1:]
    width = min(len(header), 15)
    out = [f"{d['name']} file {file}: {fmt}, {len(header)} columns" + (f" (first {width} shown)" if width < len(header) else "")]
    out.append("|".join(cell(clip(h, 40)) for h in header[:width]))
    out += ["|".join(cell(clip(c, 40)) for c in row[:width]) for row in data[:limit]]
    more = "first part of a large file" if truncated else f"{len(data)} rows"
    out.append(f"# showing {min(limit, len(data))} of {more}; download: {url}")
    return "\n".join(out)


def register(mcp: FastMCP) -> None:
    for fn in (govdata_search, govdata_dataset, govdata_preview):
        mcp.tool(annotations=READ_ONLY, output_schema=None)(fn)
