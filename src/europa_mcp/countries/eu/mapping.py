"""find_data map entries for EU-level sources (Eurostat + DGs, agri-food, Parliament, data.europa.eu)."""

from __future__ import annotations

import asyncio
import csv
import gzip
import logging
import re
from urllib.parse import urlparse

from ...common import clip
from ...sourcemap import HEADLINE_END, HEADLINE_MARK, Entry, keyword_hint, words_of
from ...web import fetch, fetch_json
from . import HINTS, agrifood, dataeuropa, europarl, eurostat

log = logging.getLogger("europa_mcp")

LOOKUP_CONCURRENCY = 8
LOOKUP_TIMEOUT = 20.0
SKIP_LOOKUPS = ("cn8", "taric")  # customs code lists: slow (up to 90 s) and only numbers


# Breakdown dimensions → the words people use when they ask for that breakdown ("… by age").
# Generic words ("country", "status", "level") are left out: they would make far too many
# datasets match every query containing them.
DIM_WORDS = {
    "sex": "sex gender men women",
    "age": "age",
    "nace_r2": "industry economic activity nace",
    "nace_r1": "industry economic activity nace",
    "isced11": "education attainment isced",
    "isced97": "education attainment isced",
    "citizen": "citizenship nationality foreigners",
    "c_birth": "birth born",
    "partner": "partner partners",
    "isco08": "occupation isco",
    "isco88": "occupation isco",
    "deg_urb": "urban rural urbanisation",
    "hhcomp": "household composition",
    "hhtyp": "household composition",
    "quant_inc": "income quantile quintile decile",
    "icd10": "cause disease icd",
    "siec": "fuel",
    "sizeclas": "enterprise size",
    "size_emp": "enterprise size",
    "c_dest": "destination",
}
NUTS_WORDS = {1: "regional regions nuts1", 2: "regional regions nuts2", 3: "regional regions nuts3 districts"}
# The same breakdowns as a short label for people choosing between datasets.
DIM_LABELS = {
    "sex": "sex",
    "age": "age",
    "nace_r2": "industry",
    "nace_r1": "industry",
    "isced11": "education",
    "isced97": "education",
    "citizen": "citizenship",
    "c_birth": "country of birth",
    "partner": "partner",
    "isco08": "occupation",
    "isco88": "occupation",
    "deg_urb": "urbanisation",
    "hhcomp": "household type",
    "hhtyp": "household type",
    "quant_inc": "income group",
    "icd10": "cause",
    "siec": "fuel",
    "sizeclas": "enterprise size",
    "size_emp": "enterprise size",
    "c_dest": "destination",
}
AGGREGATE_GEO = ("EU", "EA", "EFTA", "EEA")


def parse_metabase(text: str) -> dict[str, tuple[str, str]]:
    """Eurostat metabase (dataset<TAB>dimension<TAB>code, one line per code) → dataset id →
    (search words, display label) for its breakdowns: the dimensions above plus the deepest NUTS
    level in `geo`, e.g. ('age sex … regional regions nuts2', 'age, sex, NUTS 2 regions')."""
    dims: dict[str, set[str]] = {}
    nuts: dict[str, int] = {}
    cities: set[str] = set()
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        ds, dim, code = parts
        if dim in ("cities", "metroreg"):  # Urban Audit cities / metropolitan regions
            cities.add(ds)
        elif dim == "geo":
            if code.startswith(AGGREGATE_GEO) or not code.isalnum() or not code[:2].isalpha():
                continue
            if len(code) == 6 and code.endswith("C"):  # Urban Audit city codes, e.g. NL002C
                cities.add(ds)
            elif 3 <= len(code) <= 5:
                nuts[ds] = max(nuts.get(ds, 0), len(code) - 2)
        elif dim in DIM_WORDS:
            dims.setdefault(ds, set()).add(dim)
    out: dict[str, tuple[str, str]] = {}
    for ds in set(dims) | set(nuts) | cities:
        found = sorted(dims.get(ds, ()))
        words = [DIM_WORDS[d] for d in found]
        labels = [DIM_LABELS[d] for d in found]
        if ds in nuts:
            words.append(NUTS_WORDS[nuts[ds]])
            labels.append(f"NUTS {nuts[ds]} regions")
        if ds in cities:
            words.append("cities city urban")
            labels.append("cities")
        out[ds] = (" ".join(dict.fromkeys(" ".join(words).split())), ", ".join(dict.fromkeys(labels)))
    return out


def toc_entries(
    text: str,
    headline: dict[str, str] | None = None,
    breakdowns: dict[str, tuple[str, str]] | None = None,
) -> list[Entry]:
    """Eurostat TOC: indentation (4 spaces per level) gives each dataset its theme path.
    `headline` (id → everyday words) marks the most-asked datasets, which find_data ranks first;
    `breakdowns` (id → (words, label), from parse_metabase) says how each dataset can be broken down."""
    headline, breakdowns = headline or {}, breakdowns or {}
    out: dict[str, Entry] = {}
    stack: list[str] = []
    reader = csv.reader(text.splitlines(), delimiter="\t")
    next(reader, None)
    for r in reader:
        if len(r) < 7:
            continue
        raw, code, kind = r[0], r[1].strip(), r[2].strip()
        level = (len(raw) - len(raw.lstrip(" "))) // 4
        title = raw.strip()
        if kind == "folder":
            stack = stack[:level] + [title]
            continue
        path = " > ".join(t for t in stack[:level] if t not in ("Database by themes", "Tables by themes"))
        if code in out:  # same dataset filed under several themes: keep the extra paths as keywords
            if path and path not in out[code]["path"]:
                out[code]["keywords"] += " " + path
            continue
        start, end = r[5].strip(), r[6].strip()
        by_words, by_label = breakdowns.get(code, ("", ""))
        out[code] = {
            "source": "Eurostat",
            "id": code,
            "title": title,
            "path": path,
            "keywords": " ".join(
                x
                for x in (
                    code,
                    "table" if kind == "table" else "",
                    by_words,
                    f"{HEADLINE_MARK} {headline[code]} {by_words} {HEADLINE_END}" if code in headline else "",
                )
                if x
            ),
            "detail": by_label,
            "period": f"{start}–{end}" if start else "",
            "updated": eurostat.iso_date(r[3]),
            "call": f'eurostat_describe("{code}")',
        }
    return list(out.values())


async def build_eurostat() -> list[Entry]:
    base = eurostat.AGENCIES["eurostat"][0]
    toc, meta = await asyncio.gather(
        fetch(f"{base}/catalogue/toc/txt", {"lang": "en"}),
        fetch(f"{base}/catalogue/metabase.txt.gz", timeout=120),
        return_exceptions=True,
    )
    if isinstance(toc, BaseException):
        raise toc
    breakdowns: dict[str, tuple[str, str]] = {}
    if isinstance(meta, BaseException):  # optional enrichment: titles alone still work
        log.warning("eurostat metabase unavailable (%s); map built without breakdowns", meta)
    else:
        body = meta.content
        breakdowns = parse_metabase((gzip.decompress(body) if body[:2] == b"\x1f\x8b" else body).decode("utf-8"))
    return toc_entries(toc.text, HINTS["headline"].get("Eurostat"), breakdowns)


async def build_dg() -> list[Entry]:
    labels = {"empl": "DG EMPL", "grow": "DG GROW", "taxud": "DG TAXUD"}
    blurbs = HINTS["sources"]
    out = []
    for key, label in labels.items():
        rows = await eurostat.catalog(key)
        ids = {r["id"] for r in rows}
        for r in rows:
            parent, _, suffix = r["id"].partition("$")
            if suffix and len(suffix) == 2 and parent in ids:
                continue  # per-country copy of a parent dataset
            out.append(
                {
                    "source": label,
                    "id": r["id"],
                    "title": r["title"],
                    "path": blurbs.get(label, ""),
                    "keywords": words_of(r["id"]),
                    "period": r["period"],
                    "updated": r["updated"],
                    "call": f'eurostat_describe("{r["id"]}", agency="{key}")',
                }
            )
    return out


async def build_agrifood() -> list[Entry]:
    spec = await fetch_json(f"{agrifood.BASE}/v3/api-docs")
    kw = HINTS["keywords"]
    data_eps, lookups = {}, []
    for path, ops in spec.get("paths", {}).items():
        op = ops.get("get")
        if op is None or not path.startswith("/api/"):
            continue
        ep = path.removeprefix("/api/")
        params = [p["name"] for p in op.get("parameters", []) if p.get("in") == "query"]
        if params:
            data_eps[ep] = (op, params)
        elif not any(k in ep.lower() for k in SKIP_LOOKUPS):
            lookups.append(ep)

    # Harvest code-list values (product names, categories…) as keywords for the sector.
    sem = asyncio.Semaphore(LOOKUP_CONCURRENCY)
    values: dict[str, set[str]] = {}

    async def harvest(ep: str) -> None:
        async with sem:
            try:
                data = await fetch_json(f"{agrifood.BASE}/api/{ep}", timeout=LOOKUP_TIMEOUT)
            except Exception as e:  # noqa: BLE001 - a missing code list just means fewer keywords
                log.debug("agrifood lookup %s failed: %s", ep, e)
                return
        items = data if isinstance(data, list) else []
        found = values.setdefault(ep.split("/")[0], set())
        for x in items[:300]:
            texts = x.values() if isinstance(x, dict) else [x]
            found.update(str(t) for t in texts if isinstance(t, str) and 2 < len(t) < 60)

    await asyncio.gather(*(harvest(ep) for ep in lookups))
    out = []
    for ep, (op, params) in sorted(data_eps.items()):
        sector = ep.split("/")[0]
        tag = ", ".join(op.get("tags") or [])
        harvested = " ".join(sorted(values.get(sector, set())))[:1500]
        out.append(
            {
                "source": "Agrifood",
                "id": ep,
                "title": op.get("summary") or ep,
                "path": f"EU agri-food > {tag}" if tag else "EU agri-food",
                "keywords": f"{words_of(ep)} {keyword_hint(kw, 'Agrifood', ep)} {harvested}".strip(),
                "period": "current",
                "updated": "",
                "call": f'agri_data("{ep}", params={{{", ".join(params[:4])}{", …" if len(params) > 4 else ""}}})',
            }
        )
    return out


async def build_europarl() -> list[Entry]:
    spec = await fetch_json(f"{europarl.BASE}/")
    kw = HINTS["keywords"]
    tags = {t["name"]: t.get("description", "") for t in spec.get("tags", [])}
    out = []
    for path, ops in spec.get("paths", {}).items():
        op = ops.get("get")
        ep = path.strip("/")
        if op is None or "{" in ep or ep.endswith("/feed"):  # lists only; details go via ep_query
            continue
        desc = re.sub(r"!\[[^\]]*\]\([^)]*\)|\[([^\]]*)\]\([^)]*\)|<[^>]+>", r"\1", op.get("description") or "")
        tag = ", ".join(op.get("tags") or [])
        out.append(
            {
                "source": "European Parliament",
                "id": ep,
                "title": (op.get("summary") or ep).replace("Returns the list of all ", "").replace("Returns ", ""),
                "path": f"European Parliament > {tag}",
                "keywords": f"{words_of(ep)} {keyword_hint(kw, 'European Parliament', ep)} "
                f"{clip(desc, 300)} {tags.get(tag, '')}",
                "period": "",
                "updated": "",
                "call": f'ep_query("{ep}")',
            }
        )
    return out


async def build_dataeu() -> list[Entry]:
    """data.europa.eu catalogues (national/regional portals, EU bodies), so find_data can say which
    portal to search; the 1.9M datasets themselves stay behind dataeu_search."""
    data = await fetch_json(
        f"{dataeuropa.SEARCH}/search", {"filter": "catalogue", "limit": 1000, "aggregation": "false"}
    )
    out = []
    for c in (data.get("result") or {}).get("results") or []:
        n = c.get("count") or 0
        if not n:
            continue
        country = (c.get("country") or {}).get("label", "")
        desc = c.get("description") or {}
        langs = ["en", *(lang.get("id", "") for lang in c.get("language") or [])]
        about = " ".join(dict.fromkeys(dataeuropa.plain(desc[lang], 300) for lang in langs if desc.get(lang)))
        site = urlparse(str(c.get("homepage") or "")).netloc.removeprefix("www.")
        out.append(
            {
                "source": "data.europa.eu",
                "id": c["id"],
                "title": f"{clip(dataeuropa.text(c.get('title')), 80)}: {n:,} datasets",
                "path": f"data.europa.eu > {country}" if country else "data.europa.eu",
                "keywords": " ".join(
                    x
                    for x in (
                        about,
                        (c.get("publisher") or {}).get("name", ""),
                        site,
                        c.get("source_type", ""),
                        country,
                    )
                    if x
                ),
                "period": "",
                "updated": str(c.get("modified") or "")[:10],
                "call": f'dataeu_search("...", catalogue="{c["id"]}")',
            }
        )
    return out


async def build_curated() -> list[Entry]:
    out = []
    for e in HINTS["entries"]:
        out.append({"path": HINTS["sources"].get(e["source"], ""), "period": "", "updated": "", **e})
    return out
