"""find_data map entries for EU-level sources (Eurostat + DGs, agri-food, Parliament, data.europa.eu)."""

from __future__ import annotations

import asyncio
import csv
import logging
import re

from ...common import clip
from ...sourcemap import Entry, keyword_hint, words_of
from ...web import fetch, fetch_json
from . import HINTS, agrifood, europarl, eurostat

log = logging.getLogger("europa_mcp")

LOOKUP_CONCURRENCY = 8
LOOKUP_TIMEOUT = 20.0
SKIP_LOOKUPS = ("cn8", "taric")  # customs code lists: slow (up to 90 s) and only numbers


def toc_entries(text: str) -> list[Entry]:
    """Eurostat TOC: indentation (4 spaces per level) gives each dataset its theme path."""
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
        out[code] = {
            "source": "Eurostat", "id": code, "title": title, "path": path,
            "keywords": f"{code} {'table' if kind == 'table' else ''}".strip(),
            "period": f"{start}–{end}" if start else "", "updated": eurostat.iso_date(r[3]),
            "call": f'eurostat_describe("{code}")',
        }
    return list(out.values())


async def build_eurostat() -> list[Entry]:
    base = eurostat.AGENCIES["eurostat"][0]
    resp = await fetch(f"{base}/catalogue/toc/txt", {"lang": "en"})
    return toc_entries(resp.text)


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
            out.append({
                "source": label, "id": r["id"], "title": r["title"], "path": blurbs.get(label, ""),
                "keywords": words_of(r["id"]), "period": r["period"], "updated": r["updated"],
                "call": f'eurostat_describe("{r["id"]}", agency="{key}")',
            })
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
        out.append({
            "source": "Agrifood", "id": ep, "title": op.get("summary") or ep,
            "path": f"EU agri-food > {tag}" if tag else "EU agri-food",
            "keywords": f"{words_of(ep)} {keyword_hint(kw, 'Agrifood', ep)} {harvested}".strip(),
            "period": "", "updated": "",
            "call": f'agri_data("{ep}", params={{{", ".join(params[:4])}{", …" if len(params) > 4 else ""}}})',
        })
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
        out.append({
            "source": "European Parliament", "id": ep,
            "title": (op.get("summary") or ep).replace("Returns the list of all ", "").replace("Returns ", ""),
            "path": f"European Parliament > {tag}",
            "keywords": f"{words_of(ep)} {keyword_hint(kw, 'European Parliament', ep)} "
                        f"{clip(desc, 300)} {tags.get(tag, '')}",
            "period": "", "updated": "", "call": f'ep_query("{ep}")',
        })
    return out


async def build_curated() -> list[Entry]:
    out = []
    for e in HINTS["entries"]:
        out.append({"path": HINTS["sources"].get(e["source"], ""), "period": "", "updated": "", **e})
    return out
