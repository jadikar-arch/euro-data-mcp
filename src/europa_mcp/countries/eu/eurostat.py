"""Eurostat and the DG EMPL / GROW / TAXUD dissemination APIs (same SDMX 2.1 + JSON-stat API)."""

from __future__ import annotations

import csv
import io
import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote as urlquote

from fastmcp import FastMCP

from ...common import (
    EC_LICENCE,
    READ_ONLY,
    NotFound,
    UserError,
    as_list,
    cell,
    clip,
    compact_table,
    fmt_value,
    fold,
    safe,
    source_line,
)
from ...web import Memo, fetch, fetch_json

AGENCIES: dict[str, tuple[str, str]] = {
    "eurostat": ("https://ec.europa.eu/eurostat/api/dissemination", "ESTAT"),
    "empl": ("https://webgate.ec.europa.eu/empl/redisstat/api/dissemination", "EMPL"),
    "grow": ("https://webgate.ec.europa.eu/grow/redisstat/api/dissemination", "GROW"),
    "taxud": ("https://webgate.ec.europa.eu/taxation_customs/redisstat/api/dissemination", "TAXUD"),
}
ALIASES = {"estat": "eurostat", "dg empl": "empl", "dg grow": "grow", "dg taxud": "taxud", "taxation_customs": "taxud"}
MAX_CELLS = 20_000  # reject data queries estimated above this
INLINE_CODES = 8  # describe shows all codes when a dimension has at most this many

S = "{http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure}"
C = "{http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common}"
LANG = "{http://www.w3.org/XML/1998/namespace}lang"

CATALOGS = Memo(ttl=12 * 3600)
STRUCTURES = Memo(ttl=6 * 3600)


def browser_url(key: str, dataset_id: str) -> str:
    """The agency's data browser page for a dataset (human-readable source link)."""
    base = AGENCIES[key][0].removesuffix("/api/dissemination")
    if key == "eurostat":  # Eurostat's browser uses lowercase codes; the DG browsers keep them as listed
        return f"{base}/databrowser/view/{dataset_id.lower()}/default/table?lang=en"
    return f"{base}/databrowser/view/{dataset_id}/default/table"


def resolve_agency(name: str | None) -> tuple[str, str, str]:
    key = fold((name or "eurostat").strip())
    key = ALIASES.get(key, key)
    if key not in AGENCIES:
        raise UserError(f"Unknown agency '{name}'. Valid: {', '.join(AGENCIES)}")
    return key, *AGENCIES[key]


# ---- catalogue ----------------------------------------------------------------


def _name(el: ET.Element) -> str:
    names = {n.get(LANG): (n.text or "").strip() for n in el.findall(C + "Name")}
    return names.get("en") or next(iter(names.values()), "")


def _annotations(el: ET.Element) -> dict[str, str]:
    out = {}
    for a in el.iter(C + "Annotation"):
        t = a.findtext(C + "AnnotationType") or ""
        out[t] = a.findtext(C + "AnnotationTitle") or a.findtext(C + "AnnotationText") or ""
    return out


def iso_date(s: str) -> str:
    """'01.10.2026' → '2026-10-01'."""
    parts = s.strip()[:10].split(".")
    return "-".join(reversed(parts)) if len(parts) == 3 else s.strip()[:10]


def parse_toc(text: str) -> list[dict[str, str]]:
    """Eurostat table of contents (TSV, one row per folder/dataset; datasets repeat)."""
    rows, seen = [], set()
    reader = csv.reader(io.StringIO(text), delimiter="\t")
    next(reader, None)
    for r in reader:
        if len(r) < 7 or r[2].strip() not in ("dataset", "table") or r[1] in seen:
            continue
        seen.add(r[1])
        start, end = r[5].strip(), r[6].strip()
        rows.append(
            {
                "id": r[1].strip(),
                "title": r[0].strip(),
                "period": f"{start}–{end}" if start else "",
                "updated": iso_date(r[3]),
            }
        )
    return rows


def parse_dataflows(xml: bytes) -> list[dict[str, str]]:
    root = ET.fromstring(xml)
    rows = []
    for df in root.iter(S + "Dataflow"):
        ann = _annotations(df)
        old, new = ann.get("OBS_PERIOD_OVERALL_OLDEST", ""), ann.get("OBS_PERIOD_OVERALL_LATEST", "")
        rows.append(
            {
                "id": df.get("id") or "",
                "title": _name(df),
                "period": f"{old}–{new}" if old else "",
                "updated": ann.get("UPDATE_DATA", "")[:10],
            }
        )
    return rows


async def catalog(key: str) -> list[dict[str, str]]:
    base, ag = AGENCIES[key]

    async def load():
        if key == "eurostat":
            resp = await fetch(f"{base}/catalogue/toc/txt", {"lang": "en"})
            return parse_toc(resp.text)
        resp = await fetch(f"{base}/sdmx/2.1/dataflow/{ag}/all/latest")
        return parse_dataflows(resp.content)

    return await CATALOGS.get(key, load)


def rank(rows: list[dict[str, str]], query: str) -> list[dict[str, str]]:
    """All-words match on id+title first (shortest titles first), else most words matched."""
    words = fold(query).split()
    if not words:
        return rows
    q = fold(query).strip()
    scored = []
    for r in rows:
        hay = fold(r["id"] + " " + r["title"])
        n = sum(w in hay for w in words)
        if n:
            scored.append((fold(r["id"]) != q, -n, len(r["title"]), r))
    best = max((-s[1] for s in scored), default=0)
    if best == len(words):
        scored = [s for s in scored if -s[1] == best]
    scored.sort(key=lambda s: s[:3])
    return [s[3] for s in scored]


# ---- structure ----------------------------------------------------------------


MAP_SOURCES = {"eurostat": "Eurostat", "empl": "DG EMPL", "grow": "DG GROW", "taxud": "DG TAXUD"}


async def map_search(key: str, query: str) -> list[dict[str, str]]:
    """The same ranking as find_data (headline datasets, breakdowns, synonyms), for one agency."""
    from ... import server  # the map is owned by the server, which imports this package

    smap = server.get_map()
    await smap.ensure()
    return [
        {k: r[k] or "" for k in ("id", "title", "period", "updated")} for r in smap.search(query, [MAP_SOURCES[key]])
    ]


@dataclass
class Dim:
    id: str
    title: str
    codes: dict[str, str] = field(default_factory=dict)  # code → label, in API order


@dataclass
class Structure:
    agency: str
    id: str
    title: str
    dims: list[Dim]
    time_id: str | None
    obs_count: int | None
    oldest: str
    latest: str
    updated: str

    def dim(self, name: str) -> Dim:
        for d in self.dims:
            if d.id.lower() == name.strip().lower() or fold(d.title) == fold(name):
                return d
        valid = ", ".join(d.id for d in self.dims)
        raise UserError(f"Unknown dimension '{name}'. Valid: {valid}")


def parse_structure(xml: bytes, agency_key: str) -> Structure:
    root = ET.fromstring(xml)
    flow = next(root.iter(S + "Dataflow"), None)
    if flow is None:
        raise UserError("No dataflow in structure response.")
    ann = _annotations(flow)
    concepts = {c.get("id"): _name(c) for c in root.iter(S + "Concept")}
    lists = {cl.get("id"): {c.get("id"): _name(c) for c in cl.findall(S + "Code")} for cl in root.iter(S + "Codelist")}
    dims = []
    for d in sorted(root.iter(S + "Dimension"), key=lambda d: int(d.get("position") or 0)):
        ref = d.find(f"{S}LocalRepresentation/{S}Enumeration/Ref")
        cid = d.find(f"{S}ConceptIdentity/Ref")
        dims.append(
            Dim(
                id=d.get("id") or "",
                title=concepts.get(cid.get("id") if cid is not None else None) or d.get("id") or "",
                codes=lists.get(ref.get("id") if ref is not None else None, {}),
            )
        )
    time = next(root.iter(S + "TimeDimension"), None)
    obs = ann.get("OBS_COUNT", "")
    return Structure(
        agency=agency_key,
        id=flow.get("id") or "",
        title=_name(flow),
        dims=dims,
        time_id=time.get("id") if time is not None else None,
        obs_count=int(obs) if obs.isdigit() else None,
        oldest=ann.get("OBS_PERIOD_OVERALL_OLDEST", ""),
        latest=ann.get("OBS_PERIOD_OVERALL_LATEST", ""),
        updated=(ann.get("UPDATE_DATA") or "")[:10],
    )


async def structure(dataset_id: str, agency_name: str | None) -> Structure:
    key, base, ag = resolve_agency(agency_name)
    ds = (dataset_id or "").strip().upper()
    if not ds:
        raise UserError("dataset_id is required. Use eurostat_search to find one.")

    async def load():
        try:
            resp = await fetch(
                f"{base}/sdmx/2.1/dataflow/{ag}/{urlquote(ds, safe='')}/latest",
                {"references": "descendants", "detail": "referencepartial"},
            )
        except NotFound:
            raise UserError(f"Unknown dataset '{dataset_id}' at {key}. Use eurostat_search(query, agency).") from None
        return parse_structure(resp.content, key)

    return await STRUCTURES.get((key, ds), load)


# ---- data -----------------------------------------------------------------------


def jsonstat_rows(js: dict[str, Any]) -> tuple[list[str], list[list[str]], list[str]]:
    """Decode sparse JSON-stat 2.0 into (dim labels, rows of code labels, values+flags)."""
    ids, sizes = js.get("id") or [], js.get("size") or []
    dims = js.get("dimension") or {}
    labels_by_pos: list[list[str]] = []
    for d in ids:
        cat = dims[d]["category"]
        index = cat.get("index") or {}
        order = sorted(index, key=index.get) if isinstance(index, dict) else list(index)
        labels = cat.get("label") or {}
        labels_by_pos.append([labels.get(c, c) for c in order])
    strides = [math.prod(sizes[i + 1 :]) for i in range(len(sizes))]
    values, status = js.get("value") or {}, js.get("status") or {}
    if isinstance(values, list):
        values = {str(i): v for i, v in enumerate(values) if v is not None}
    rows = []
    for k in sorted(values, key=int):
        i = int(k)
        coords = [labels_by_pos[p][(i // strides[p]) % sizes[p]] for p in range(len(ids))]
        flag = status.get(k, "") if isinstance(status, dict) else ""
        rows.append(coords + [fmt_value(values[k]), flag])
    return [dims[d].get("label") or d for d in ids], rows, ids


# ---- tools ------------------------------------------------------------------------


@safe
async def eurostat_search(query: str, agency: str = "eurostat", limit: int = 10) -> str:
    """Find Eurostat datasets by topic (same ranking as find_data), e.g. 'house prices', 'unemployment by region'.
    agency: eurostat (default, ~8k datasets) | empl (labour market policy) | grow (postal) | taxud (tax)."""
    key, *_ = resolve_agency(agency)
    limit = max(1, min(limit, 50))
    hits = await map_search(key, query) if query.strip() else []
    if not hits:  # empty query (list all), map not built yet, or nothing in the map matched
        hits = rank(await catalog(key), query)
    if not hits:
        return f"No {key} datasets match '{query}'. Try broader English keywords."
    lines = ["id|title|period|updated"]
    lines += ["|".join(cell(r[k]) for k in ("id", "title", "period", "updated")) for r in hits[:limit]]
    if len(hits) > limit:
        lines.append(f"# {limit} of {len(hits)} matches; refine the query for others")
    return "\n".join(lines)


@safe
async def eurostat_describe(dataset_id: str, agency: str = "eurostat") -> str:
    """Show a dataset's dimensions and codes before fetching data with eurostat_data.
    Small code lists are shown in full; look up others with eurostat_codes."""
    st = await structure(dataset_id, agency)
    out = [f"{st.id}: {st.title} ({st.agency})"]
    meta = []
    if st.oldest:
        meta.append(f"period: {st.oldest}–{st.latest}")
    if st.updated:
        meta.append(f"updated: {st.updated}")
    if st.obs_count:
        meta.append(f"observations: {st.obs_count}")
    if meta:
        out.append("; ".join(meta))
    out.append("dimensions (id|title|codes|values):")
    for d in st.dims:
        items = list(d.codes.items())
        shown = ", ".join(f"{c}={clip(t, 60)}" for c, t in items[:INLINE_CODES])
        if len(items) > INLINE_CODES:
            shown = ", ".join(c for c, _ in items[:INLINE_CODES]) + ", … (eurostat_codes)"
        out.append(f"{d.id}|{cell(d.title)}|{len(items)}|{cell(shown)}")
    if st.time_id:
        out.append("time: filter with since/until/last_n (e.g. last_n=5; periods like 2024, 2024-Q1, 2024-03)")
    return "\n".join(out)


@safe
async def eurostat_codes(
    dataset_id: str, dimension: str, query: str | None = None, agency: str = "eurostat", limit: int = 50
) -> str:
    """Look up codes of a dataset dimension by label, e.g. geo 'Netherlands' → NL."""
    st = await structure(dataset_id, agency)
    d = st.dim(dimension)
    items = list(d.codes.items())
    if query:
        words = fold(query).split()
        q = fold(query).strip()
        items = [(c, t) for c, t in items if all(w in fold(t) or w in fold(c) for w in words)]
        items.sort(key=lambda i: (fold(i[0]) != q and fold(i[1]) != q, not fold(i[1]).startswith(q)))
    if not items:
        return f"No codes match '{query}' in {d.id}."
    limit = max(1, min(limit, 500))
    lines = ["code|label"] + [f"{cell(c)}|{cell(t)}" for c, t in items[:limit]]
    if len(items) > limit:
        lines.append(f"# {limit} of {len(items)}; add/narrow query")
    return "\n".join(lines)


@safe
async def eurostat_data(
    dataset_id: str,
    filters: dict[str, list[str]] | None = None,
    agency: str = "eurostat",
    last_n: int | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int = 500,
) -> str:
    """Fetch values. filters = {dimension: [codes]}, e.g. {'geo': ['NL','DE'], 'unit': ['I15_Q']}.
    Time: last_n=5 (latest periods) or since/until ('2020', '2024-Q1'). Constant columns shown once."""
    key, base, _ = resolve_agency(agency)
    st = await structure(dataset_id, key)
    limit = max(1, min(limit, 5000))

    params: list[tuple[str, str]] = [("lang", "en")]
    chosen: dict[str, list[str]] = {}
    for name, vals in (filters or {}).items():
        d = st.dim(name)
        by_lc = {c.lower(): c for c in d.codes}
        codes = []
        for v in as_list(vals):
            code = by_lc.get(v.lower())
            if code is None:
                sample = ", ".join(list(d.codes)[:8])
                raise UserError(f"Unknown code '{v}' for {d.id}. Examples: {sample}. Use eurostat_codes.")
            codes.append(code)
        if codes:
            chosen[d.id] = codes
            params += [(d.id, c) for c in codes]
    if last_n:
        params.append(("lastTimePeriod", str(max(1, min(int(last_n), 500)))))
    if since:
        params.append(("sinceTimePeriod", since.strip()))
    if until:
        params.append(("untilTimePeriod", until.strip()))

    # Estimate the response size and reject over-broad queries before downloading MBs.
    sel = math.prod(len(chosen.get(d.id) or d.codes or [1]) for d in st.dims)
    full = math.prod(len(d.codes) or 1 for d in st.dims)
    periods = int(last_n) if last_n else 40
    est = (st.obs_count * sel / full) if st.obs_count and not last_n else sel * periods
    if est > MAX_CELLS:
        open_dims = [f"{d.id}({len(d.codes)})" for d in st.dims if d.id not in chosen and len(d.codes) > 1]
        return (
            f"Error: query too broad (~{int(est):,} values). Filter: {', '.join(open_dims)}"
            " and/or set last_n. Find codes with eurostat_codes."
        )

    js = await fetch_json(f"{base}/statistics/1.0/data/{urlquote(st.id, safe='')}", params)
    cols, rows, ids = jsonstat_rows(js or {})
    out = [
        f"{st.id}: {clip(js.get('label') or st.title, 120)}"
        + (f" (updated {js['updated'][:10]})" if js and js.get("updated") else "")
    ]
    if not rows:
        out.append("No values for these filters.")
        return "\n".join(out)
    # Newest periods first so truncation keeps recent data.
    if "time" in ids:
        t = ids.index("time")
        rows.sort(key=lambda r: r[t], reverse=True)
    total = len(rows)
    rows = rows[:limit]
    has_flags = any(r[-1] for r in rows)
    if has_flags:  # value stays the last column
        table, cols = [r[:-2] + [r[-1], r[-2]] for r in rows], cols + ["flag", "value"]
    else:
        table, cols = [r[:-1] for r in rows], cols + ["value"]
    out += compact_table(cols, table)
    if total > limit:
        out.append(f"# truncated: {limit} of {total} values; narrow filters or raise limit")
    if has_flags:
        out.append("# flags: p=provisional, e=estimated, b=break, u=low reliability, c=confidential")
    owner = "Eurostat" if key == "eurostat" else f"European Commission, DG {key.upper()}"
    out.append(source_line(browser_url(key, st.id), EC_LICENCE.replace("European Union", f"European Union ({owner})")))
    return "\n".join(out)


def register(mcp: FastMCP) -> None:
    for fn in (eurostat_search, eurostat_describe, eurostat_codes, eurostat_data):
        mcp.tool(annotations=READ_ONLY, output_schema=None)(fn)
