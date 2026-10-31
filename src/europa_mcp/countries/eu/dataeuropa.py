"""data.europa.eu: the EU open data portal (search, dataset details, SPARQL, quality, use cases)."""

from __future__ import annotations

import csv
import io
import json
import re
from typing import Any

from fastmcp import FastMCP

from ...common import READ_ONLY, NotFound, UserError, cell, clip, fold, safe, source_line
from ...preview import preview
from ...web import Memo, fetch, fetch_json

PORTAL = "https://data.europa.eu"
SEARCH = f"{PORTAL}/api/hub/search"
MQA = f"{PORTAL}/api/mqa/cache"
USE_CASES = Memo(ttl=24 * 3600)
SEARCH_FIELDS = "id,title,country,catalog,distributions.format,modified,issued,catalog_record"
SORTS = {"relevance": "relevance+desc", "newest": "modified+desc"}
CATEGORIES = {  # EU data themes (facet 'categories')
    "AGRI": "Agriculture, fisheries, forestry and food",
    "ECON": "Economy and finance",
    "EDUC": "Education, culture and sport",
    "ENER": "Energy",
    "ENVI": "Environment",
    "GOVE": "Government and public sector",
    "HEAL": "Health",
    "INTR": "International issues",
    "JUST": "Justice, legal system and public safety",
    "REGI": "Regions and cities",
    "SOCI": "Population and society",
    "TECH": "Science and technology",
    "TRAN": "Transport",
}
QUALITY = ("excellent", "good", "sufficient")  # metadata scoring, best first ('bad' is the rest)
FACETS = {  # dataeu_facets `by` → API facet id
    "catalogue": "catalog",
    "format": "format",
    "category": "categories",
    "country": "country",
    "publisher": "publisher",
    "licence": "license",
    "quality": "scoring",
}
WRITE_SPARQL = re.compile(r"\b(INSERT|DELETE|LOAD|CLEAR|DROP|CREATE|COPY|MOVE|ADD)\b", re.I)
PREFIXES = {
    "http://www.w3.org/ns/dcat#": "dcat:",
    "http://purl.org/dc/terms/": "dct:",
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#": "rdf:",
    "http://xmlns.com/foaf/0.1/": "foaf:",
    "http://www.w3.org/2004/02/skos/core#": "skos:",
    "http://data.europa.eu/88u/dataset/": "dataset/",
    "http://publications.europa.eu/resource/authority/": "eu-auth/",
}


def text(v: Any, lang: str = "en") -> str:
    """Pick one language from a multilingual value (dict, list or plain string)."""
    if isinstance(v, dict):
        if "label" in v and not isinstance(v["label"], dict):
            return str(v["label"])
        return str(v.get(lang) or v.get("en") or next(iter(v.values()), ""))
    if isinstance(v, list):
        return ", ".join(text(x, lang) for x in v if x)
    return str(v or "")


def plain(v: Any, n: int) -> str:
    """Description text without HTML tags, clipped."""
    return clip(re.sub(r"<[^>]+>", " ", str(v or "")), n)


def formats(ds: dict[str, Any]) -> str:
    fm = []
    for d in ds.get("distributions") or []:
        f = (d.get("format") or {}).get("id") if isinstance(d.get("format"), dict) else None
        if f and f not in fm:
            fm.append(f)
    return ",".join(fm[:6])


def modified(ds: dict[str, Any]) -> str:
    rec = ds.get("catalog_record") or {}
    return str(ds.get("modified") or ds.get("issued") or rec.get("modified") or rec.get("issued") or "")[:10]


def dmy_to_iso(s: str) -> str:
    """'31/05/2016' → '2016-05-31'."""
    parts = (s or "").strip()[:10].split("/")
    return "-".join(reversed(parts)) if len(parts) == 3 else (s or "")[:10]


def category_code(c: str) -> str:
    """'heal' / 'Health' / 'transport' → EU theme code."""
    key = c.strip().upper()
    if key in CATEGORIES:
        return key
    hits = [k for k, name in CATEGORIES.items() if fold(c.strip()) in fold(name)]
    if len(hits) != 1:
        raise UserError(f"Unknown category '{c}'. Use one of: {', '.join(CATEGORIES)}.")
    return hits[0]


def search_facets(
    country: str | None = None,
    format: str | None = None,
    catalogue: str | None = None,
    category: str | None = None,
    hvd: bool = False,
    min_quality: str | None = None,
) -> dict[str, list[str]]:
    facets: dict[str, list[str]] = {}
    if country:
        facets["country"] = [country.strip().lower()]
    if format:
        facets["format"] = [format.strip().upper()]
    if catalogue:
        facets["catalog"] = [catalogue.strip()]
    if category:
        facets["categories"] = [category_code(category)]
    if hvd:
        facets["is_hvd"] = ["true"]
    if min_quality:
        q = min_quality.strip().lower().removesuffix("scoring")
        if q not in QUALITY:
            raise UserError(f"min_quality must be one of: {', '.join(QUALITY)}.")
        facets["scoring"] = [f"{x}Scoring" for x in QUALITY[: QUALITY.index(q) + 1]]
    return facets


@safe
async def dataeu_search(
    query: str,
    country: str | None = None,
    format: str | None = None,
    catalogue: str | None = None,
    category: str | None = None,
    hvd: bool = False,
    min_quality: str | None = None,
    sort: str = "relevance",
    language: str = "en",
    page: int = 0,
    limit: int = 10,
) -> str:
    """Search 1.9M open datasets from EU institutions and national portals (data.europa.eu).
    country: ISO2; format: 'CSV'; catalogue: portal id; category: EU theme (HEAL, ECON, TRAN…); hvd: High-Value
    only; min_quality: excellent|good|sufficient; sort: relevance|newest; language: ISO2 for titles/descriptions."""
    facets = search_facets(country, format, catalogue, category, hvd, min_quality)
    if sort.strip().lower() not in SORTS:
        raise UserError(f"sort must be one of: {', '.join(SORTS)}.")
    lang = language.strip().lower()[:2] or "en"
    limit = max(1, min(limit, 50))
    params = {
        "q": query,
        "filter": "dataset",
        "limit": limit,
        "page": max(0, page),
        "aggregation": "false",
        "includes": f"{SEARCH_FIELDS},description.en" + (f",description.{lang}" if lang != "en" else ""),
        "sort": SORTS[sort.strip().lower()].replace("+", " "),
    }
    if facets:
        params["facets"] = json.dumps(facets)
    data = await fetch_json(f"{SEARCH}/search", params)
    res = (data or {}).get("result") or {}
    rows = res.get("results") or []
    if not rows:
        return f"No datasets match '{query}'" + (f" with {facets}" if facets else "") + "."
    lines = ["id|title|country|catalogue|formats|modified|about"]
    for r in rows:
        lines.append(
            "|".join(
                cell(x)
                for x in (
                    r.get("id", ""),
                    clip(text(r.get("title"), lang), 110),
                    (r.get("country") or {}).get("id", ""),
                    (r.get("catalog") or {}).get("id", ""),
                    formats(r),
                    modified(r),
                    plain(text(r.get("description"), lang), 140),
                )
            )
        )
    total = res.get("count") or 0
    if total > (page + 1) * limit:
        lines.append(f"# {len(rows)} of {total:,}; page={page + 1} for more or add filters")
    return "\n".join(lines)


@safe
async def dataeu_facets(
    query: str = "",
    by: str = "catalogue,format,category",
    country: str | None = None,
    format: str | None = None,
    catalogue: str | None = None,
    category: str | None = None,
    hvd: bool = False,
    min_quality: str | None = None,
    top: int = 10,
) -> str:
    """Where are the matching data.europa.eu datasets? Counts per catalogue, format, category,
    country, publisher, licence or quality (by: comma-separated). Use it to pick dataeu_search filters."""
    wanted = [b.strip().lower() for b in by.split(",") if b.strip()]
    if bad := [b for b in wanted if b not in FACETS]:
        raise UserError(f"Unknown by '{', '.join(bad)}'. Use: {', '.join(FACETS)}.")
    facets = search_facets(country, format, catalogue, category, hvd, min_quality)
    params: dict[str, Any] = {"filter": "dataset", "limit": 0}
    if query:
        params["q"] = query
    if facets:
        params["facets"] = json.dumps(facets)
    data = await fetch_json(f"{SEARCH}/search", params)
    res = (data or {}).get("result") or {}
    found = {f.get("id"): f.get("items") or [] for f in res.get("facets") or []}
    top = max(1, min(top, 50))
    lines = [
        f"{res.get('count') or 0:,} datasets match"
        + (f" '{query}'" if query else "")
        + (f" with {facets}" if facets else "")
    ]
    for b in wanted or list(FACETS)[:3]:
        items = [i for i in found.get(FACETS[b], []) if i.get("count")]
        lines.append(f"{b}|datasets|name")
        lines += [
            "|".join(cell(x) for x in (i.get("id"), f"{i['count']:,}", clip(text(i.get("title")), 80)))
            for i in items[:top]
        ]
        if len(items) > top:
            lines.append(f"# {top} of {len(items)} {b} values")
    return "\n".join(lines)


@safe
async def dataeu_dataset(dataset_id: str, language: str = "en", max_files: int = 15) -> str:
    """Details of one data.europa.eu dataset: description, publisher, licence and download URLs."""
    try:
        data = await fetch_json(f"{SEARCH}/datasets/{dataset_id.strip()}")
    except NotFound:
        raise UserError(f"Unknown dataset '{dataset_id}'. Use dataeu_search.") from None
    d = (data or {}).get("result") or {}
    out = [f"{d.get('id')}: {text(d.get('title'), language)}"]
    pub = d.get("publisher") or {}
    facts = {
        "catalogue": (d.get("catalog") or {}).get("id"),
        "country": (d.get("country") or {}).get("label"),
        "publisher": pub.get("name") or pub.get("resource"),
        "issued": str(d.get("issued") or "")[:10],
        "modified": modified(d),
        "frequency": (d.get("accrual_periodicity") or {}).get("label"),
        "keywords": ", ".join(k.get("label", "") for k in (d.get("keywords") or [])[:10] if isinstance(k, dict)),
        "landing page": text(d.get("landing_page")),
        "quality score": (d.get("quality_meas") or {}).get("scoring"),
        "portal": f"{PORTAL}/data/datasets/{d.get('id')}",
    }
    out += [f"{k}: {cell(v)}" for k, v in facts.items() if v]
    out.append(f"description: {clip(text(d.get('description'), language), 600)}")
    dists = d.get("distributions") or []
    if dists:
        out.append("files (n|format|title|licence|url); first rows: dataeu_preview(id, file=n):")
        for i, x in enumerate(dists[:max_files], 1):
            out.append(
                "|".join(
                    cell(v)
                    for v in (
                        i,
                        dist_format(x),
                        clip(text(x.get("title"), language), 60),
                        dist_licence(x),
                        dist_url(x),
                    )
                )
            )
        if len(dists) > max_files:
            out.append(f"# {max_files} of {len(dists)} files")
    return "\n".join(out)


def dist_url(x: dict[str, Any]) -> str:
    url = x.get("download_url") or x.get("access_url") or [""]
    return str(url[0] if isinstance(url, list) and url else url or "")


def dist_format(x: dict[str, Any]) -> str:
    return str((x.get("format") or {}).get("id", "")) if isinstance(x.get("format"), dict) else ""


def dist_licence(x: dict[str, Any]) -> str:
    lic = x.get("license") or {}
    return str(lic.get("label") or lic.get("id") or "") if isinstance(lic, dict) else str(lic)


@safe
async def dataeu_preview(dataset_id: str, file: int = 1, limit: int = 20) -> str:
    """First rows of a CSV or JSON file of a data.europa.eu dataset (file = n from dataeu_dataset).
    Use it to check the columns and values before downloading."""
    try:
        data = await fetch_json(f"{SEARCH}/datasets/{dataset_id.strip()}")
    except NotFound:
        raise UserError(f"Unknown dataset '{dataset_id}'. Use dataeu_search.") from None
    d = (data or {}).get("result") or {}
    dists = d.get("distributions") or []
    if not dists:
        raise UserError(f"Dataset '{dataset_id}' lists no files. Portal: {PORTAL}/data/datasets/{dataset_id}")
    if not 1 <= file <= len(dists):
        raise UserError(f"file must be 1..{len(dists)}; see dataeu_dataset('{dataset_id}').")
    x = dists[file - 1]
    url = dist_url(x)
    if not url:
        raise UserError(f"File {file} has no URL.")
    out = await preview(f"{d.get('id')} file {file}", url, dist_format(x), limit)
    out.append(source_line(url, dist_licence(x) or "not stated; check the publisher"))
    return "\n".join(out)


def _short_uri(v: str) -> str:
    for full, pre in PREFIXES.items():
        if v.startswith(full):
            return pre + v[len(full) :]
    return v


@safe
async def dataeu_sparql(query: str, limit: int = 100) -> str:
    """Run a read-only SPARQL SELECT/ASK on data.europa.eu (DCAT metadata of all datasets).
    For text search use dataeu_search: CONTAINS over all titles times out."""
    if WRITE_SPARQL.search(re.sub(r'"[^"]*"|<[^>]*>', "", query)):
        raise UserError("Only read-only SELECT/ASK queries are allowed.")
    if not re.search(r"\b(SELECT|ASK)\b", query, re.I):
        raise UserError("Only SELECT or ASK queries are supported.")
    limit = max(1, min(limit, 1000))
    q = query.strip()
    if re.search(r"\bSELECT\b", q, re.I) and not re.search(r"\bLIMIT\s+\d+", q, re.I):
        q += f"\nLIMIT {limit + 1}"
    data = await fetch_json(
        f"{PORTAL}/sparql",
        {"query": q},
        headers={"Accept": "application/sparql-results+json"},
        timeout=90,
    )
    if data is None or not isinstance(data, dict):
        raise UserError("SPARQL endpoint returned no JSON (query too heavy?). Add filters or LIMIT.")
    if "boolean" in data:
        return str(data["boolean"]).lower()
    cols = data.get("head", {}).get("vars", [])
    rows = data.get("results", {}).get("bindings", [])
    if not rows:
        return "No results."
    lines = ["|".join(cols)]
    for b in rows[:limit]:
        lines.append("|".join(cell(clip(_short_uri(b[c]["value"]), 200)) if c in b else "" for c in cols))
    if len(rows) > limit:
        lines.append(f"# truncated at {limit} rows; add LIMIT/OFFSET or filters")
    return "\n".join(lines)


@safe
async def dataeu_quality(scope: str = "global", id: str | None = None) -> str:
    """Metadata quality (MQA) of data.europa.eu: scope 'global', 'country' (id: ISO3, e.g. NLD)
    or 'catalogue' (id from dataeu_search). Shows score/7.5, counts and weakest metrics."""
    scope = scope.strip().lower().removesuffix("s")
    if scope == "global":
        url = f"{MQA}/global"
    elif scope in ("country", "catalogue", "catalog"):
        if not id:
            raise UserError(f"id is required for scope '{scope}'.")
        ident = id.strip().upper() if scope == "country" else id.strip()
        if scope == "country" and len(ident) != 3:
            raise UserError("country id must be ISO 3166 alpha-3, e.g. NLD, DEU, FRA.")
        url = f"{MQA}/{'countries' if scope == 'country' else 'catalogues'}/{ident}"
    else:
        raise UserError("scope must be 'global', 'country' or 'catalogue'.")
    try:
        data = await fetch_json(url)
    except NotFound:
        raise UserError(f"No quality metrics for {scope} '{id}'.") from None
    results = ((data or {}).get("result") or {}).get("results") or []
    if not results:
        return f"No quality metrics for {scope} '{id}'."
    r = results[0]
    score, counts = r.get("score") or {}, (r.get("counts") or {}).get("value") or {}
    out = [
        f"{scope} {id or ''}".strip() + f": score {round(score.get('value', 0), 2)}/{score.get('max', 7.5)}"
        f" ({score.get('date', '')})",
        "counts: " + ", ".join(f"{k}={v}" for k, v in counts.items()),
        "metric|level|importance|coverage%",
    ]
    cov = (r.get("coverage") or {}).get("value") or {}
    for level in ("dataset", "distribution"):
        metrics = sorted(cov.get(level) or [], key=lambda m: m.get("coverage") or 0)
        out += [
            f"{m.get('metric')}|{level}|{m.get('importance', '')}|{round(m.get('coverage') or 0, 1)}" for m in metrics
        ]
    if scope.startswith("catalog"):
        out.append(f"# PDF report: {PORTAL}/api/mqa/reporter/report/en?catalogueId={id.strip()}")
    return "\n".join(out)


async def use_cases() -> list[dict[str, str]]:
    async def load():
        resp = await fetch(f"{PORTAL}/en/export-use-cases")
        return list(csv.DictReader(io.StringIO(resp.text)))

    return await USE_CASES.get("csv", load)


@safe
async def dataeu_use_cases(
    query: str | None = None, country: str | None = None, sector: str | None = None, limit: int = 10
) -> str:
    """Real-world apps/projects built on EU open data (data.europa.eu use cases), by keyword,
    country (name, e.g. 'Netherlands') or sector."""
    rows = await use_cases()

    def match(r: dict[str, str]) -> bool:
        if country and fold(country) not in fold(r.get("Country", "")):
            return False
        if sector and fold(sector) not in fold(r.get("Sector", "")):
            return False
        hay = fold(" ".join(r.get(k, "") for k in ("Title", "Description", "Sector")))
        return all(w in hay for w in fold(query or "").split())

    hits = [r for r in rows if match(r)]
    if not hits:
        return "No use cases match."
    hits.sort(key=lambda r: dmy_to_iso(r.get("Date of Publication", "")), reverse=True)
    limit = max(1, min(limit, 50))
    lines = ["title|country|sector|published|summary"] + [
        "|".join(
            cell(x)
            for x in (
                r.get("Title", ""),
                r.get("Country", ""),
                clip(r.get("Sector", ""), 60),
                dmy_to_iso(r.get("Date of Publication", "")),
                clip(r.get("Description", ""), 160),
            )
        )
        for r in hits[:limit]
    ]
    if len(hits) > limit:
        lines.append(f"# {limit} of {len(hits)}; narrow with query/country/sector")
    return "\n".join(lines)


def register(mcp: FastMCP) -> None:
    for fn in (
        dataeu_search,
        dataeu_facets,
        dataeu_dataset,
        dataeu_preview,
        dataeu_sparql,
        dataeu_quality,
        dataeu_use_cases,
    ):
        mcp.tool(annotations=READ_ONLY, output_schema=None)(fn)
