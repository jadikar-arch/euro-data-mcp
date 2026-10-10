"""FastMCP server exposing token-efficient tools over the CBS OData v4 API."""

from __future__ import annotations

import argparse
import asyncio
import functools
import logging
import os
import sys
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from fastmcp import FastMCP

from . import client
from .client import CBSError, NotFound, TTLCache, eq_any, get_rows, quote
from .index import CATALOG_FIELDS, Index, fold, summarize

log = logging.getLogger("cbs_mcp")

REFRESH_HOURS = float(os.environ.get("CBS_INDEX_REFRESH_HOURS", "6"))
MAX_EST_ROWS = 100_000  # reject observation queries estimated above this
MAX_FILTER_VALUES = 200
FULL_CODELIST_MAX = 5_000  # above this, resolve code titles by filtered lookups
MAX_MEASURES_SHOWN = 60

# Common names whose CBS title differs (folded query → search text).
PLACE_ALIASES = {
    "den haag": "gravenhage", "the hague": "gravenhage", "hague": "gravenhage",
    "den bosch": "hertogenbosch", "s-hertogenbosch": "hertogenbosch",
    "friesland": "fryslan", "frisia": "fryslan",
    "netherlands": "nederland", "the netherlands": "nederland",
}

INSTRUCTIONS = (
    "Dutch official statistics (CBS). Workflow: search_datasets (Dutch keywords) → "
    "describe_dataset → list_codes (find codes, e.g. a municipality) → get_observations."
)

CACHE = TTLCache(ttl=REFRESH_HOURS * 3600)
INDEX: Index | None = None
_sync_task: asyncio.Task | None = None


# ---- helpers ----------------------------------------------------------------


def safe(fn):
    """Turn known errors into short strings; never leak tracebacks to the model."""

    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        try:
            return await fn(*args, **kwargs)
        except CBSError as e:
            return f"Error: {e}"
        except Exception as e:  # noqa: BLE001
            log.exception("tool %s failed", fn.__name__)
            return f"Error: internal failure ({type(e).__name__}). Try again or simplify."

    return wrapper


def fmt_value(v: Any) -> str:
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() else str(round(v, 6))
    return str(v)


def cell(s: Any) -> str:
    return str(s).replace("|", "/").replace("\n", " ")


@dataclass
class Dataset:
    id: str
    catalog: str
    title: str
    description: str
    period: str
    status: str
    modified: str
    obs_count: int

    @property
    def base(self) -> str:
        return f"/{self.catalog}/{self.id}"


@dataclass
class Dim:
    id: str
    title: str
    kind: str
    codes_set: str | None
    groups_set: str | None


def get_index() -> Index:
    global INDEX
    if INDEX is None:
        INDEX = Index()
    return INDEX


async def resolve(dataset_id: str) -> Dataset:
    """Canonicalize a (case-insensitive) dataset id via the index, else the live catalog."""
    dataset_id = (dataset_id or "").strip()
    if not dataset_id:
        raise CBSError("dataset_id is required. Use search_datasets to find one.")
    idx = get_index()
    row = idx.get(dataset_id)
    if row is None:
        rows, _ = await get_rows(
            "/Datasets",
            {
                "$select": CATALOG_FIELDS,
                "$filter": f"tolower(Identifier) eq {quote(dataset_id.lower())}",
            },
            limit=1,
        )
        if not rows:
            raise CBSError(f"Unknown dataset '{dataset_id}'. Use search_datasets to find one.")
        idx.ingest(rows)  # self-repair: dataset is live but was missing locally
        row = idx.get(dataset_id)
        assert row is not None
    return Dataset(
        id=row["id"], catalog=row["catalog"], title=row["title"] or "",
        description=row["description"] or "", period=row["period"] or "",
        status=row["status"] or "", modified=(row["modified"] or "")[:10],
        obs_count=row["obs_count"] or 0,
    )


async def ds_rows(ds: Dataset, entity: str, params: dict[str, Any], limit: int | None = None):
    try:
        return await get_rows(f"{ds.base}/{entity}", params, limit)
    except NotFound:
        get_index().remove(ds.id)
        CACHE.invalidate(ds.id)
        raise CBSError(f"Dataset {ds.id} (or {entity}) no longer exists at CBS.") from None


async def dimensions(ds: Dataset) -> list[Dim]:
    key = (ds.id, "dims")
    if (hit := CACHE.get(key)) is not None:
        return hit
    rows, _ = await ds_rows(
        ds, "Dimensions", {"$select": "Identifier,Title,Kind,CodesUrl,GroupsUrl"}
    )
    dims = [
        Dim(
            id=r["Identifier"], title=r.get("Title") or r["Identifier"],
            kind=(r.get("Kind") or "Dimension").replace("Dimension", "") or "Topic",
            codes_set=(r.get("CodesUrl") or "").rsplit("/", 1)[-1] or None,
            groups_set=(r.get("GroupsUrl") or "").rsplit("/", 1)[-1] or None,
        )
        for r in rows
    ]
    CACHE.set(key, dims)
    return dims


async def measure_codes(ds: Dataset) -> list[dict[str, str]]:
    key = (ds.id, "measures")
    if (hit := CACHE.get(key)) is not None:
        return hit
    rows, _ = await ds_rows(ds, "MeasureCodes", {"$select": "Identifier,Title,Unit"})
    out = [
        {"code": r["Identifier"], "title": (r.get("Title") or "").strip(), "unit": r.get("Unit") or ""}
        for r in rows
    ]
    CACHE.set(key, out)
    return out


async def code_count(ds: Dataset, dim: Dim) -> int:
    key = (ds.id, "count", dim.id)
    if (hit := CACHE.get(key)) is not None:
        return hit
    if not dim.codes_set:
        return 0
    _, total = await ds_rows(ds, dim.codes_set, {"$count": "true", "$top": 0})
    CACHE.set(key, total or 0)
    return total or 0


async def group_roots(ds: Dataset, dim: Dim) -> dict[str, str]:
    """Group id → title of its top-level ancestor (e.g. GMPV27 → 'Gemeenten per provincie')."""
    key = (ds.id, "groups", dim.id)
    if (hit := CACHE.get(key)) is not None:
        return hit
    out: dict[str, str] = {}
    if dim.groups_set:
        rows, _ = await ds_rows(ds, dim.groups_set, {"$select": "Id,Title,ParentId"})
        by_id = {r["Id"]: r for r in rows}
        for gid in by_id:
            node, hops = by_id[gid], 0
            while node.get("ParentId") in by_id and hops < 10:
                node, hops = by_id[node["ParentId"]], hops + 1
            out[gid] = node.get("Title") or ""
    CACHE.set(key, out)
    return out


async def all_codes(ds: Dataset, dim: Dim) -> list[dict[str, str]]:
    key = (ds.id, "codes", dim.id)
    if (hit := CACHE.get(key)) is not None:
        return hit
    fields = "Identifier,Title,DimensionGroupId" + (",Status" if dim.kind == "Time" else "")
    rows, _ = await ds_rows(ds, dim.codes_set or "", {"$select": fields})
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
    if dim.kind == "Time":
        out.sort(key=lambda c: c["code"], reverse=True)
    CACHE.set(key, out)
    return out


async def code_titles(ds: Dataset, dim: Dim, codes: set[str]) -> dict[str, str]:
    if not codes:
        return {}
    if await code_count(ds, dim) <= FULL_CODELIST_MAX:
        return {c["code"]: c["title"] for c in await all_codes(ds, dim) if c["code"] in codes}
    out: dict[str, str] = {}
    todo = sorted(codes)
    for i in range(0, len(todo), 100):
        rows, _ = await ds_rows(
            ds, dim.codes_set or "",
            {"$select": "Identifier,Title", "$filter": eq_any("Identifier", todo[i : i + 100])},
        )
        out.update({r["Identifier"]: (r.get("Title") or "").strip() for r in rows})
    return out


def pick_dim(dims: list[Dim], name: str) -> Dim:
    for d in dims:
        if d.id.lower() == name.lower() or fold(d.title) == fold(name):
            return d
    valid = ", ".join(d.id for d in dims)
    raise CBSError(f"Unknown dimension '{name}'. Valid: {valid}, Measures")


async def wait_for_index(timeout: float = 90.0) -> bool:
    idx = get_index()
    if idx.count():
        return True
    ensure_sync_task()
    try:
        await asyncio.wait_for(idx.ready.wait(), timeout)
    except TimeoutError:
        return False
    return idx.count() > 0


# ---- tools ------------------------------------------------------------------

@asynccontextmanager
async def lifespan(_server: FastMCP) -> AsyncIterator[None]:
    ensure_sync_task()
    try:
        yield
    finally:
        await client.aclose()


mcp = FastMCP("cbs", instructions=INSTRUCTIONS, lifespan=lifespan)
READ_ONLY = {"readOnlyHint": True, "openWorldHint": True}


@mcp.tool(annotations=READ_ONLY, output_schema=None)
@safe
async def search_datasets(
    query: str, catalog: str = "CBS", include_discontinued: bool = False, limit: int = 10
) -> str:
    """Find CBS tables by topic. Start here for any statistics question.
    query: Dutch topic keywords (e.g. 'bevolking regio', 'koopwoningen prijzen'); leave out
    places and years, they are codes picked later with list_codes."""
    limit = max(1, min(limit, 50))
    if not await wait_for_index():
        raise CBSError("Search index is still being built; retry in a minute.")
    rows, total = get_index().search(query, catalog, include_discontinued, limit)
    if not rows:
        hint = "" if include_discontinued else " or include_discontinued=true"
        return f"No datasets match '{query}'. Try other Dutch keywords{hint}."
    lines = ["id|title|period|status|modified"]
    lines += [
        "|".join(cell(r[k] or "") for k in ("id", "title", "period", "status", "modified"))
        for r in rows
    ]
    if total > len(rows):
        lines.append(f"# {len(rows)} of {total} matches; refine the query for others")
    return "\n".join(lines)


@mcp.tool(annotations=READ_ONLY, output_schema=None)
@safe
async def describe_dataset(dataset_id: str) -> str:
    """Show a table's measures and dimensions (with code counts) before querying it.
    Use the measure codes and dimension ids with list_codes / get_observations."""
    ds = await resolve(dataset_id)
    dims, meas = await asyncio.gather(dimensions(ds), measure_codes(ds))
    counts = await asyncio.gather(*(code_count(ds, d) for d in dims))
    out = [
        f"{ds.id}: {ds.title}",
        f"status: {ds.status}; period: {ds.period or '?'}; modified: {ds.modified}; "
        f"observations: {ds.obs_count}",
        f"summary: {summarize(ds.description)}",
        "dimensions (id|title|kind|codes):",
    ]
    for d, n in zip(dims, counts):
        line = f"{d.id}|{cell(d.title)}|{d.kind}|{n}"
        if d.kind == "Time" and n:
            newest, _ = await ds_rows(
                ds, d.codes_set or "",
                {"$select": "Identifier,Title", "$orderby": "Identifier desc"}, limit=1,
            )
            if newest:
                line += f" (latest {newest[0]['Identifier']} = {newest[0]['Title']})"
        out.append(line)
    out.append(f"measures (code|title|unit), {len(meas)} total:")
    out += [f"{m['code']}|{cell(m['title'])}|{m['unit']}" for m in meas[:MAX_MEASURES_SHOWN]]
    if len(meas) > MAX_MEASURES_SHOWN:
        out.append(f"# {len(meas) - MAX_MEASURES_SHOWN} more: list_codes(id, 'Measures', query)")
    return "\n".join(out)


@mcp.tool(annotations=READ_ONLY, output_schema=None)
@safe
async def list_codes(
    dataset_id: str, dimension: str, query: str | None = None, limit: int = 50
) -> str:
    """Look up codes of a dimension (or 'Measures') by title, e.g. 'Amsterdam' → GM0363.
    Time dimensions are listed newest first; query 'JJ' = years, 'KW' = quarters, 'MM' = months."""
    limit = max(1, min(limit, 500))
    ds = await resolve(dataset_id)
    if dimension.lower() in ("measures", "measure", "measurecodes", "onderwerpen"):
        items = [{**m, "extra": m["unit"]} for m in await measure_codes(ds)]
        header = "code|title|unit"
    else:
        dim = pick_dim(await dimensions(ds), dimension)
        if not dim.codes_set:
            raise CBSError(f"Dimension '{dim.id}' has no code list.")
        items = [
            {**c, "extra": c["group"] if dim.kind != "Time" else
             ("" if c["status"] in ("", "Definitief") else c["status"])}
            for c in await all_codes(ds, dim)
        ]
        header = "code|title|" + ("status" if dim.kind == "Time" else "group")
    if query:
        query = PLACE_ALIASES.get(fold(query).strip(), query)
        words = fold(query).split()
        hits = [
            i for i in items if all(w in fold(i["title"]) or w in fold(i["code"]) for w in words)
        ]
        q = fold(query)
        # exact title first, then prefix, then the rest (stable).
        hits.sort(key=lambda i: (fold(i["title"]) != q, not fold(i["title"]).startswith(q)))
        items = hits
    if not items:
        return f"No codes match '{query}' in {dimension}."
    lines = [header] + [
        "|".join(cell(x) for x in (i["code"], i["title"], i["extra"])).rstrip("|")
        for i in items[:limit]
    ]
    if len(items) > limit:
        lines.append(f"# {limit} of {len(items)}; add/narrow query")
    return "\n".join(lines)


@mcp.tool(annotations=READ_ONLY, output_schema=None)
@safe
async def get_observations(
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
        vals = [vals] if isinstance(vals, str) else [str(v) for v in vals]
        vals = list(dict.fromkeys(v.strip() for v in vals if str(v).strip()))
        if len(vals) > MAX_FILTER_VALUES:
            raise CBSError(f"Too many codes for {dim.id} ({len(vals)}); max {MAX_FILTER_VALUES}.")
        if vals:
            flt[dim.id] = vals

    meas_by_lc = {m["code"].lower(): m for m in all_meas}
    sel_meas: list[str] = []
    for m in measures or []:
        hit = meas_by_lc.get(m.strip().lower())
        if hit is None:
            sample = ", ".join(x["code"] for x in all_meas[:8])
            raise CBSError(
                f"Unknown measure '{m}'. Examples: {sample}. Use list_codes(id, 'Measures', query)."
            )
        sel_meas.append(hit["code"])

    time_dim = next((d for d in dims if d.kind == "Time"), None)
    want_latest = latest and time_dim is not None and time_dim.id not in flt

    # Estimate result size from code counts and reject over-broad queries.
    est = float(ds.obs_count or 0)
    if sel_meas and all_meas:
        est *= len(sel_meas) / len(all_meas)
    counts = dict(zip([d.id for d in dims], await asyncio.gather(*(code_count(ds, d) for d in dims))))
    for dim_id, vals in flt.items():
        est *= min(1.0, len(vals) / max(1, counts.get(dim_id, 1)))
    if want_latest and time_dim:
        est /= max(1, counts.get(time_dim.id, 1))
    if est > MAX_EST_ROWS:
        open_dims = [d.id for d in dims if d.id not in flt and not (want_latest and d is time_dim)]
        return (
            f"Error: query too broad (~{int(est):,} rows). Add filters on: "
            f"{', '.join(open_dims + ([] if sel_meas else ['measures']))}. "
            "Find codes with list_codes; use latest=true for the newest period."
        )

    clauses = [eq_any(dim_id, vals) for dim_id, vals in flt.items()]
    if sel_meas:
        clauses.append(eq_any("Measure", sel_meas))

    if want_latest and time_dim:
        probe, _ = await ds_rows(
            ds, "Observations",
            {
                "$filter": " and ".join([*clauses, "ValueAttribute eq 'None'"]),
                "$orderby": f"{time_dim.id} desc",
                "$select": time_dim.id,
            },
            limit=1,
        )
        if not probe:
            return "No data for these filters."
        flt[time_dim.id] = [probe[0][time_dim.id]]
        clauses.append(eq_any(time_dim.id, flt[time_dim.id]))

    params: dict[str, Any] = {
        "$select": ",".join(["Measure", "Value", "StringValue", "ValueAttribute"] + [d.id for d in dims]),
        "$count": "true",
    }
    if clauses:
        params["$filter"] = " and ".join(clauses)
    if time_dim:
        params["$orderby"] = f"{time_dim.id} desc"  # truncation keeps the newest periods
    rows, total = await ds_rows(ds, "Observations", params, limit=limit)

    # Map codes → titles.
    used = {d.id: {r[d.id] for r in rows if r.get(d.id)} for d in dims}
    titles = dict(zip(used, await asyncio.gather(*(code_titles(ds, d, used[d.id]) for d in dims))))
    meas_info = {m["code"]: m for m in all_meas}

    cols = [d.title for d in dims] + ["measure", "unit", "value"]
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
            [titles[d.id].get(r.get(d.id), r.get(d.id) or "") for d in dims]
            + [m["title"], m["unit"], fmt_value(v)]
        )

    out = [f"{ds.id}: {ds.title}"]
    if not table:
        out.append("No values for these filters." + (f" Empty cells: {empty}" if empty else ""))
        return "\n".join(out)
    # Columns constant across all rows are printed once.
    keep = [i for i in range(len(cols)) if i == len(cols) - 1 or len({t[i] for t in table}) > 1]
    fixed = [f"{cols[i]}={table[0][i]}" for i in range(len(cols)) if i not in keep and table[0][i]]
    if fixed:
        out.append("fixed: " + "; ".join(cell(f) for f in fixed))
    out.append("|".join(cell(cols[i]) for i in keep))
    out += ["|".join(cell(t[i]) for i in keep) for t in table]
    total = total if total is not None else len(rows)
    if total > len(rows):
        out.append(f"# truncated: {len(rows)} of {total} rows; narrow filters or raise limit")
    if empty:
        out.append(f"# omitted empty cells: {empty}")
    return "\n".join(out)


@mcp.tool(annotations=READ_ONLY, output_schema=None)
@safe
async def upcoming_releases(days: int = 14, limit: int = 30) -> str:
    """List CBS tables scheduled to get new data in the next `days` days."""
    days, limit = max(1, min(days, 90)), max(1, min(limit, 200))
    now = datetime.now(timezone.utc).replace(microsecond=0)
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    rows, total = await get_rows(
        "/ReleaseCalendar",
        {
            "$filter": f"ReleaseDate ge {now.strftime(fmt)} and "
            f"ReleaseDate le {(now + timedelta(days=days)).strftime(fmt)}",
            "$orderby": "ReleaseDate",
            "$count": "true",
        },
        limit=limit,
    )
    if not rows:
        return f"No releases scheduled in the next {days} days."
    titles = get_index().titles(r["DatasetIdentifier"] for r in rows)
    lines = ["date|id|title"] + [
        f"{r['ReleaseDate'][:16].replace('T', ' ')}|{r['DatasetIdentifier']}|"
        f"{cell(titles.get(r['DatasetIdentifier'], ''))}"
        for r in rows
    ]
    if total and total > len(rows):
        lines.append(f"# {len(rows)} of {total}; raise limit or lower days")
    return "\n".join(lines)


# ---- index lifecycle --------------------------------------------------------


def _on_change(ids: list[str]) -> None:
    for i in ids:
        CACHE.invalidate(i)


async def _sync_loop() -> None:
    idx = get_index()
    interval = REFRESH_HOURS * 3600
    while True:
        age = time.time() - idx.last_sync()
        if idx.count() == 0 or age >= interval:
            try:
                await idx.sync(on_change=_on_change)
                wait = interval
            except Exception as e:  # noqa: BLE001
                log.warning("index sync failed: %s; retrying in 10 min", e)
                wait = 600
        else:
            idx.ready.set()
            wait = interval - age
        await asyncio.sleep(max(60.0, wait))


def ensure_sync_task() -> None:
    """Start the background index sync once per process (safe to call repeatedly)."""
    global _sync_task
    if _sync_task is None or _sync_task.done():
        _sync_task = asyncio.get_running_loop().create_task(_sync_loop())




# ---- CLI --------------------------------------------------------------------


def main() -> None:
    logging.basicConfig(
        stream=sys.stderr, level=os.environ.get("CBS_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    p = argparse.ArgumentParser(prog="cbs-mcp", description="CBS open data MCP server")
    p.add_argument("command", nargs="?", default="serve", choices=["serve", "sync"])
    p.add_argument("--transport", default="stdio", choices=["stdio", "http"])
    p.add_argument("--host", default=os.environ.get("CBS_HOST", "127.0.0.1"))
    p.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    p.add_argument("--full", action="store_true", help="sync: rebuild the whole index")
    p.add_argument("--no-details", action="store_true", help="sync: skip measure/dimension titles")
    args = p.parse_args()

    if args.command == "sync":
        async def run_sync() -> None:
            try:
                stats = await get_index().sync(full=args.full, details=not args.no_details)
                log.info("sync done: %s (index: %s)", stats, get_index().path)
            finally:
                await client.aclose()

        asyncio.run(run_sync())
        return

    if args.transport == "http":
        from fastmcp.server.middleware.rate_limiting import RateLimitingMiddleware

        rps = float(os.environ.get("CBS_RATE_LIMIT_RPS", "5"))
        mcp.add_middleware(RateLimitingMiddleware(max_requests_per_second=rps, burst_capacity=20))
        mcp.run(
            transport="http", host=args.host, port=args.port, show_banner=False,
            uvicorn_config={"log_config": None},  # use our stderr logging, not stdout
        )
    else:
        mcp.run(transport="stdio", show_banner=False)


if __name__ == "__main__":
    main()
