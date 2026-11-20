"""CBS (Statistics Netherlands) OData v4 (https://datasets.cbs.nl/odata/v1): search, describe, codes, data, releases.

The API has no ranked search (`$search` is ignored), so the whole catalogue (~4,900 tables, Dutch)
is downloaded once, cached, and searched in memory; the find_data map is built from the same rows.
"""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from fastmcp import FastMCP

from ...common import (
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
from ...web import Memo, fetch_json

BASE = "https://datasets.cbs.nl/odata/v1"
PAGE = "https://opendata.cbs.nl/#/CBS/nl/dataset/{}/table"
LICENCE = "CC BY 4.0, © Centraal Bureau voor de Statistiek (CBS)"
CATALOG_FIELDS = "Identifier,Title,Description,Status,Modified,ObservationCount"
CATALOG = Memo(ttl=12 * 3600)
META = Memo(ttl=6 * 3600)
MAX_EST_ROWS = 100_000  # reject observation queries estimated above this
MAX_FILTER_VALUES = 200
FULL_CODELIST_MAX = 5_000  # above this, resolve code titles by filtered lookups
MAX_MEASURES_SHOWN = 60

# Common names whose CBS title differs (folded query → search text).
PLACE_ALIASES = {
    "den haag": "gravenhage",
    "the hague": "gravenhage",
    "hague": "gravenhage",
    "den bosch": "hertogenbosch",
    "s-hertogenbosch": "hertogenbosch",
    "friesland": "fryslan",
    "frisia": "fryslan",
    "netherlands": "nederland",
    "the netherlands": "nederland",
}

PERIOD_RE = re.compile(r"Gegevens beschikbaar\s*(?:vanaf|van|over|tot|per)?\s*:?\s*([^\n\r]+)", re.IGNORECASE)


# ---- OData helpers ----------------------------------------------------------------------


def quote(value: str) -> str:
    """OData string literal: single quotes doubled."""
    return "'" + str(value).replace("'", "''") + "'"


def eq_any(field: str, values: list[str]) -> str:
    """`(F eq 'a' or F eq 'b')`."""
    return "(" + " or ".join(f"{field} eq {quote(v)}" for v in values) + ")"


async def get_rows(
    path: str, params: dict[str, Any] | None = None, limit: int | None = None
) -> tuple[list[dict[str, Any]], int | None]:
    """`value` rows of an entity set, following @odata.nextLink up to `limit` rows.
    Returns (rows, total) where total is @odata.count when `$count=true` was requested."""
    params = dict(params or {})
    if limit is not None:
        params["$top"] = limit
    data = await fetch_json(BASE + path, params) or {}
    rows: list[dict[str, Any]] = list(data.get("value", []))
    total = data.get("@odata.count")
    while (nxt := data.get("@odata.nextLink")) and (limit is None or len(rows) < limit):
        data = await fetch_json(nxt) or {}
        rows.extend(data.get("value", []))
    return (rows[:limit] if limit is not None else rows), total


# ---- catalogue --------------------------------------------------------------------------


def parse_description(text: str | None) -> tuple[str, str]:
    """Split a CBS description into (body without the availability boilerplate, period)."""
    text = text or ""
    m = PERIOD_RE.search(text)
    period = re.split(r"\.\s", m.group(1).strip())[0].rstrip(".")[:40] if m else ""  # first sentence only
    body = re.sub(r"\s+", " ", text[: m.start()] if m else text).strip()
    return body[:1500], period


async def catalog() -> list[dict[str, Any]]:
    """Every table as {id, title, body, period, status, modified, obs}; cached."""

    async def load():
        rows, _ = await get_rows("/Datasets", {"$select": CATALOG_FIELDS})
        if not rows:
            raise UserError("CBS catalogue returned no tables; try again later.")
        out = []
        for r in rows:
            body, period = parse_description(r.get("Description"))
            out.append(
                {
                    "id": r["Identifier"],
                    "title": (r.get("Title") or "").strip(),
                    "body": body,
                    "period": period,
                    "status": r.get("Status") or "",
                    "modified": (r.get("Modified") or "")[:10],
                    "obs": r.get("ObservationCount") or 0,
                }
            )
        return out

    return await CATALOG.get("all", load)


async def resolve(dataset_id: str) -> dict[str, Any]:
    """The catalogue row of a (case-insensitive) table id."""
    key = (dataset_id or "").strip().lower()
    if not key:
        raise UserError("dataset_id is required. Use cbs_search or find_data to find one.")
    row = next((r for r in await catalog() if r["id"].lower() == key), None)
    if row is None:
        raise UserError(f"Unknown CBS table '{dataset_id}'. Use cbs_search or find_data to find one.")
    return row


async def ds_rows(ds: dict[str, Any], entity: str, params: dict[str, Any], limit: int | None = None):
    try:
        return await get_rows(f"/CBS/{ds['id']}/{entity}", params, limit)
    except NotFound:
        CATALOG.clear()
        META.clear()
        raise UserError(f"Table {ds['id']} (or {entity}) no longer exists at CBS.") from None


# ---- table metadata ---------------------------------------------------------------------


async def dimensions(ds: dict[str, Any]) -> list[dict[str, Any]]:
    async def load():
        rows, _ = await ds_rows(ds, "Dimensions", {"$select": "Identifier,Title,Kind,CodesUrl,GroupsUrl"})
        return [
            {
                "id": r["Identifier"],
                "title": r.get("Title") or r["Identifier"],
                "kind": (r.get("Kind") or "Dimension").replace("Dimension", "") or "Topic",
                "codes": (r.get("CodesUrl") or "").rsplit("/", 1)[-1],
                "groups": (r.get("GroupsUrl") or "").rsplit("/", 1)[-1],
            }
            for r in rows
        ]

    return await META.get((ds["id"], "dims"), load)


async def measure_codes(ds: dict[str, Any]) -> list[dict[str, str]]:
    """Measures as {code, title, unit}. Leaf titles repeat across groups ('Seizoengecorrigeerd' under
    'Beroepsbevolking' and under 'Werkloze beroepsbevolking'), so a repeated title is prefixed with
    its group: 'Werkloze beroepsbevolking: Seizoengecorrigeerd'."""

    async def load():
        rows, _ = await ds_rows(ds, "MeasureCodes", {"$select": "Identifier,Title,Unit,MeasureGroupId"})
        try:
            groups, _ = await get_rows(f"/CBS/{ds['id']}/MeasureGroups", {"$select": "Id,Title,ParentId"})
        except NotFound:
            groups = []
        by_id = {g["Id"]: g for g in groups}

        def group(gid: str | None) -> str:
            names, hops = [], 0
            while gid in by_id and hops < 10:
                names.append((by_id[gid].get("Title") or "").strip())
                gid, hops = by_id[gid].get("ParentId"), hops + 1
            return " > ".join(n for n in reversed(names) if n)

        out = [
            {
                "code": r["Identifier"],
                "title": (r.get("Title") or "").strip(),
                "unit": r.get("Unit") or "",
                "group": group(r.get("MeasureGroupId")),
            }
            for r in rows
        ]
        seen = [m["title"] for m in out]
        for m in out:
            if m["group"] and seen.count(m["title"]) > 1:
                m["title"] = f"{m['group']}: {m['title']}"
        return out

    return await META.get((ds["id"], "measures"), load)


async def code_count(ds: dict[str, Any], dim: dict[str, Any]) -> int:
    async def load():
        if not dim["codes"]:
            return 0
        _, total = await ds_rows(ds, dim["codes"], {"$count": "true", "$top": 0})
        return total or 0

    return await META.get((ds["id"], "count", dim["id"]), load)


async def group_roots(ds: dict[str, Any], dim: dict[str, Any]) -> dict[str, str]:
    """Group id → title of its top-level ancestor (e.g. GMPV27 → 'Gemeenten per provincie')."""

    async def load():
        out: dict[str, str] = {}
        if dim["groups"]:
            rows, _ = await ds_rows(ds, dim["groups"], {"$select": "Id,Title,ParentId"})
            by_id = {r["Id"]: r for r in rows}
            for gid in by_id:
                node, hops = by_id[gid], 0
                while node.get("ParentId") in by_id and hops < 10:
                    node, hops = by_id[node["ParentId"]], hops + 1
                out[gid] = node.get("Title") or ""
        return out

    return await META.get((ds["id"], "groups", dim["id"]), load)


async def all_codes(ds: dict[str, Any], dim: dict[str, Any]) -> list[dict[str, str]]:
    async def load():
        fields = "Identifier,Title,DimensionGroupId" + (",Status" if dim["kind"] == "Time" else "")
        rows, _ = await ds_rows(ds, dim["codes"], {"$select": fields})
        roots = await group_roots(ds, dim)
        out = [
            {
                "code": r["Identifier"],
                "title": (r.get("Title") or "").strip(),
                "group": roots.get(r.get("DimensionGroupId") or "", ""),
                "status": r.get("Status") or "",
            }
            for r in rows
        ]
        if dim["kind"] == "Time":
            out.sort(key=lambda c: c["code"], reverse=True)
        return out

    return await META.get((ds["id"], "codes", dim["id"]), load)


async def code_titles(ds: dict[str, Any], dim: dict[str, Any], codes: set[str]) -> dict[str, str]:
    if not codes:
        return {}
    if await code_count(ds, dim) <= FULL_CODELIST_MAX:
        return {c["code"]: c["title"] for c in await all_codes(ds, dim) if c["code"] in codes}
    out: dict[str, str] = {}
    todo = sorted(codes)
    for i in range(0, len(todo), 100):
        rows, _ = await ds_rows(
            ds, dim["codes"], {"$select": "Identifier,Title", "$filter": eq_any("Identifier", todo[i : i + 100])}
        )
        out.update({r["Identifier"]: (r.get("Title") or "").strip() for r in rows})
    return out


def pick_dim(dims: list[dict[str, Any]], name: str) -> dict[str, Any]:
    for d in dims:
        if d["id"].lower() == name.lower() or fold(d["title"]) == fold(name):
            return d
    raise UserError(f"Unknown dimension '{name}'. Valid: {', '.join(d['id'] for d in dims)}, Measures")


# ---- search -----------------------------------------------------------------------------


def query_groups(query: str) -> list[list[str]]:
    """Free-text query → OR-groups of folded terms (the word plus its Dutch synonyms)."""
    from ...common import STOPWORDS
    from . import SYNONYMS

    groups = []
    for tok in re.findall(r"\w+", fold(query)):
        if len(tok) < 2 or tok in STOPWORDS:
            continue
        syn = SYNONYMS.get(tok) or (SYNONYMS.get(tok[:-1], ()) if tok.endswith("s") else ())
        if not syn and tok + "s" in SYNONYMS:
            syn = SYNONYMS[tok + "s"]
        groups.append(list(dict.fromkeys([tok, *(fold(s) for s in syn)])))
    return groups


def rank(rows: list[dict[str, Any]], groups: list[list[str]]) -> list[dict[str, Any]]:
    """Tables matching at least one term group, best first: more groups in the title, then anywhere,
    then regular before discontinued tables, then newest."""

    def hits(text: str) -> int:
        return sum(any(a in text for a in alts) for alts in groups)

    scored = []
    for r in sorted(rows, key=lambda r: r["modified"], reverse=True):  # newest first; the sort below is stable
        title = fold(r["title"])
        anywhere = hits(f"{title} {fold(r['body'])}")
        if anywhere:
            scored.append((-hits(title), -anywhere, r["status"] != "Regulier", r))
    scored.sort(key=lambda t: t[:3])
    return [t[-1] for t in scored]


@safe
async def cbs_search(query: str, include_discontinued: bool = False, limit: int = 10) -> str:
    """Find CBS tables by topic. Start here for any Dutch statistics question.
    query: Dutch topic keywords (e.g. 'bevolking regio'); leave out places and years, they are codes."""
    limit = max(1, min(limit, 50))
    groups = query_groups(query)
    if not groups:
        raise UserError("Give topic keywords, e.g. 'bevolking regio'.")
    rows = [r for r in await catalog() if include_discontinued or r["status"] == "Regulier"]
    hits = rank(rows, groups)
    if not hits:
        hint = "" if include_discontinued else " or include_discontinued=true"
        return f"No tables match '{query}'. Try other Dutch keywords{hint}."
    lines = ["id|title|period|status|modified"]
    lines += ["|".join(cell(r[k]) for k in ("id", "title", "period", "status", "modified")) for r in hits[:limit]]
    if len(hits) > limit:
        lines.append(f"# {limit} of {len(hits)} matches; refine the query for others")
    return "\n".join(lines)


# ---- describe / codes / data / releases ---------------------------------------------------


@safe
async def cbs_describe(dataset_id: str) -> str:
    """Show a table's measures and dimensions (with code counts) before querying it.
    Use the measure codes and dimension ids with cbs_codes / cbs_data."""
    ds = await resolve(dataset_id)
    dims, meas = await asyncio.gather(dimensions(ds), measure_codes(ds))
    counts = await asyncio.gather(*(code_count(ds, d) for d in dims))
    out = [
        f"{ds['id']}: {ds['title']}",
        f"status: {ds['status']}; period: {ds['period'] or '?'}; modified: {ds['modified']}; observations: {ds['obs']}",
        f"summary: {clip(ds['body'], 300)}",
        "dimensions (id|title|kind|codes):",
    ]
    for d, n in zip(dims, counts, strict=True):
        line = f"{d['id']}|{cell(d['title'])}|{d['kind']}|{n}"
        if d["kind"] == "Time" and n:
            newest, _ = await ds_rows(
                ds, d["codes"], {"$select": "Identifier,Title", "$orderby": "Identifier desc"}, limit=1
            )
            if newest:
                line += f" (latest {newest[0]['Identifier']} = {newest[0]['Title']})"
        out.append(line)
    out.append(f"measures (code|title|unit), {len(meas)} total:")
    out += [f"{m['code']}|{cell(m['title'])}|{m['unit']}" for m in meas[:MAX_MEASURES_SHOWN]]
    if len(meas) > MAX_MEASURES_SHOWN:
        out.append(f"# {len(meas) - MAX_MEASURES_SHOWN} more: cbs_codes(id, 'Measures', query)")
    return "\n".join(out)


@safe
async def cbs_codes(dataset_id: str, dimension: str, query: str | None = None, limit: int = 50) -> str:
    """Look up codes of a dimension (or 'Measures') by title, e.g. 'Amsterdam' → GM0363.
    Time dimensions are listed newest first; query 'JJ' = years, 'KW' = quarters, 'MM' = months."""
    limit = max(1, min(limit, 500))
    ds = await resolve(dataset_id)
    if dimension.lower() in ("measures", "measure", "measurecodes", "onderwerpen"):
        items = [{**m, "extra": m["unit"]} for m in await measure_codes(ds)]
        header = "code|title|unit"
    else:
        dim = pick_dim(await dimensions(ds), dimension)
        if not dim["codes"]:
            raise UserError(f"Dimension '{dim['id']}' has no code list.")
        time = dim["kind"] == "Time"
        items = [
            {**c, "extra": ("" if c["status"] in ("", "Definitief") else c["status"]) if time else c["group"]}
            for c in await all_codes(ds, dim)
        ]
        header = "code|title|" + ("status" if time else "group")
    if query:
        query = PLACE_ALIASES.get(fold(query).strip(), query)
        words = fold(query).split()
        items = [i for i in items if all(w in fold(i["title"]) or w in fold(i["code"]) for w in words)]
        q = fold(query)
        items.sort(key=lambda i: (fold(i["title"]) != q, not fold(i["title"]).startswith(q)))  # exact, prefix, rest
    if not items:
        return f"No codes match '{query}' in {dimension}."
    lines = [header] + [
        "|".join(cell(x) for x in (i["code"], i["title"], i["extra"])).rstrip("|") for i in items[:limit]
    ]
    if len(items) > limit:
        lines.append(f"# {limit} of {len(items)}; add/narrow query")
    return "\n".join(lines)


@safe
async def cbs_data(
    dataset_id: str,
    measures: list[str] | None = None,
    filters: dict[str, list[str]] | None = None,
    latest: bool = False,
    limit: int = 500,
) -> str:
    """Fetch values. filters = {dimension_id: [codes]}, e.g. {'RegioS': ['GM0363']}.
    latest=true keeps only the newest period with data (unless the time dimension is filtered).
    Large tables need filters; constant columns are shown once under 'fixed'."""
    limit = max(1, min(limit, 5000))
    ds = await resolve(dataset_id)
    dims = await dimensions(ds)
    all_meas = await measure_codes(ds)

    flt: dict[str, list[str]] = {}
    for name, vals in (filters or {}).items():
        dim = pick_dim(dims, name)
        vals = list(dict.fromkeys(as_list(vals)))
        if len(vals) > MAX_FILTER_VALUES:
            raise UserError(f"Too many codes for {dim['id']} ({len(vals)}); max {MAX_FILTER_VALUES}.")
        if vals:
            flt[dim["id"]] = vals

    meas_by_lc = {m["code"].lower(): m for m in all_meas}
    sel_meas: list[str] = []
    for m in as_list(measures):
        hit = meas_by_lc.get(m.lower())
        if hit is None:
            sample = ", ".join(x["code"] for x in all_meas[:8])
            raise UserError(f"Unknown measure '{m}'. Examples: {sample}. Use cbs_codes(id, 'Measures', query).")
        sel_meas.append(hit["code"])

    time_dim = next((d for d in dims if d["kind"] == "Time"), None)
    want_latest = latest and time_dim is not None and time_dim["id"] not in flt

    # Estimate the result size from code counts and reject over-broad queries before downloading.
    est = float(ds["obs"] or 0)
    if sel_meas and all_meas:
        est *= len(sel_meas) / len(all_meas)
    counts = dict(zip([d["id"] for d in dims], await asyncio.gather(*(code_count(ds, d) for d in dims)), strict=True))
    for dim_id, vals in flt.items():
        est *= min(1.0, len(vals) / max(1, counts.get(dim_id, 1)))
    if want_latest and time_dim:
        est /= max(1, counts.get(time_dim["id"], 1))
    if est > MAX_EST_ROWS:
        open_dims = [d["id"] for d in dims if d["id"] not in flt and not (want_latest and d is time_dim)]
        raise UserError(
            f"query too broad (~{int(est):,} rows). Add filters on: "
            f"{', '.join(open_dims + ([] if sel_meas else ['measures']))}. "
            "Find codes with cbs_codes; use latest=true for the newest period."
        )

    clauses = [eq_any(dim_id, vals) for dim_id, vals in flt.items()]
    if sel_meas:
        clauses.append(eq_any("Measure", sel_meas))

    if want_latest and time_dim:
        probe, _ = await ds_rows(
            ds,
            "Observations",
            {
                "$filter": " and ".join([*clauses, "ValueAttribute eq 'None'"]),
                "$orderby": f"{time_dim['id']} desc",
                "$select": time_dim["id"],
            },
            limit=1,
        )
        if not probe:
            return "No data for these filters."
        flt[time_dim["id"]] = [probe[0][time_dim["id"]]]
        clauses.append(eq_any(time_dim["id"], flt[time_dim["id"]]))

    params: dict[str, Any] = {
        "$select": ",".join(["Measure", "Value", "StringValue", "ValueAttribute"] + [d["id"] for d in dims]),
        "$count": "true",
    }
    if clauses:
        params["$filter"] = " and ".join(clauses)
    if time_dim:
        params["$orderby"] = f"{time_dim['id']} desc"  # truncation keeps the newest periods
    rows, total = await ds_rows(ds, "Observations", params, limit=limit)

    used = {d["id"]: {r[d["id"]] for r in rows if r.get(d["id"])} for d in dims}
    titles = dict(zip(used, await asyncio.gather(*(code_titles(ds, d, used[d["id"]]) for d in dims)), strict=True))
    meas_info = {m["code"]: m for m in all_meas}

    cols = [d["title"] for d in dims] + ["measure", "unit", "value"]
    table: list[list[str]] = []
    empty: dict[str, int] = {}
    for r in rows:
        v = r.get("Value")
        if v is None:
            v = r.get("StringValue")
        if v is None or v == "":
            attr = r.get("ValueAttribute") or "empty"
            empty[attr] = empty.get(attr, 0) + 1
            continue
        m = meas_info.get(r["Measure"], {"title": r["Measure"], "unit": ""})
        table.append(
            [titles[d["id"]].get(r.get(d["id"]), r.get(d["id"]) or "") for d in dims]
            + [m["title"], m["unit"], fmt_value(v)]
        )

    out = [f"{ds['id']}: {ds['title']}"]
    if not table:
        out.append("No values for these filters." + (f" Empty cells: {empty}" if empty else ""))
        return "\n".join(out)
    out += compact_table(cols, table)  # columns constant across rows are printed once
    total = total if total is not None else len(rows)
    if total > len(rows):
        out.append(f"# truncated: {len(rows)} of {total} rows; narrow filters or raise limit")
    if empty:
        out.append(f"# omitted empty cells: {empty}")
    out.append(source_line(PAGE.format(ds["id"]), LICENCE))
    return "\n".join(out)


@safe
async def cbs_releases(days: int = 14, limit: int = 30) -> str:
    """List CBS tables scheduled to get new data in the next `days` days."""
    days, limit = max(1, min(days, 90)), max(1, min(limit, 200))
    now = datetime.now(UTC).replace(microsecond=0)
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    rows, total = await get_rows(
        "/ReleaseCalendar",
        {
            "$filter": f"ReleaseDate ge {now.strftime(fmt)} and ReleaseDate le {(now + timedelta(days=days)).strftime(fmt)}",
            "$orderby": "ReleaseDate",
            "$count": "true",
        },
        limit=limit,
    )
    if not rows:
        return f"No releases scheduled in the next {days} days."
    titles = {r["id"].lower(): r["title"] for r in await catalog()}
    lines = ["date|id|title"] + [
        f"{r['ReleaseDate'][:16].replace('T', ' ')}|{r['DatasetIdentifier']}|"
        f"{cell(titles.get(r['DatasetIdentifier'].lower(), ''))}"
        for r in rows
    ]
    if total and total > len(rows):
        lines.append(f"# {len(rows)} of {total}; raise limit or lower days")
    return "\n".join(lines)


def register(mcp: FastMCP) -> None:
    for fn in (cbs_search, cbs_describe, cbs_codes, cbs_data, cbs_releases):
        mcp.tool(annotations=READ_ONLY, output_schema=None)(fn)
