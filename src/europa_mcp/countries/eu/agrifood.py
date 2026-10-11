"""EU agri-food market data (DG AGRI): prices, production and indicators per sector."""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from ...common import NotFound, READ_ONLY, UserError, as_list, cell, compact_table, fmt_value, fold, safe
from ...web import Memo, fetch_json

BASE = "https://api.tech.ec.europa.eu/agrifood"
SPEC = Memo(ttl=24 * 3600)


async def endpoints() -> dict[str, dict[str, Any]]:
    """endpoint ('cereal/prices') → {'params': {name: (required, description)}}, from OpenAPI."""

    async def load():
        spec = await fetch_json(f"{BASE}/v3/api-docs")
        out = {}
        for path, ops in sorted(spec.get("paths", {}).items()):
            op = ops.get("get")
            if op is None or not path.startswith("/api/"):
                continue
            params = {
                p["name"]: (bool(p.get("required")), " ".join((p.get("description") or "").split()))
                for p in op.get("parameters", [])
                if p.get("in") == "query"
            }
            out[path.removeprefix("/api/")] = {"params": params}
        return out

    return await SPEC.get("spec", load)


def _hint(desc: str) -> str:
    """The format part of a parameter description, e.g. 'dd/mm/yyyy' or 'yyyy/yyyy'."""
    for token in ("dd/mm/yyyy", "yyyy/yyyy", "yyyy/yy", "yyyy/mm", "yyyy", "'annual' or 'monthly'",
                  "'monthly' or 'short'"):
        if token in desc:
            return token
    return ""


def _resolve(name: str, eps: dict[str, Any]) -> str:
    key = name.strip().strip("/").removeprefix("api/")
    if key in eps:
        return key
    by_lc = {k.lower(): k for k in eps}
    if key.lower() in by_lc:
        return by_lc[key.lower()]
    near = [k for k in eps if fold(key.split("/")[0]) in fold(k)][:8]
    raise UserError(
        f"Unknown endpoint '{name}'." + (f" Did you mean: {', '.join(near)}?" if near else "")
        + " See agri_endpoints."
    )


@safe
async def agri_endpoints(query: str | None = None) -> str:
    """List EU agri-food endpoints (prices, production, trade, CMEF indicators) and their params.
    query filters by sector, e.g. 'cereal', 'milk', 'pig', 'fertiliser'."""
    eps = await endpoints()
    words = fold(query or "").split()
    keep = {k: v for k, v in eps.items() if all(w in fold(k) for w in words)} if words else eps
    if not keep:
        sectors = sorted({k.split("/")[0] for k in eps})
        return f"No endpoints match '{query}'. Sectors: {', '.join(sectors)}"
    data = [(k, v) for k, v in keep.items() if v["params"]]
    lookups = [k for k, v in keep.items() if not v["params"]]
    lines = ["endpoint|params (* required; list params take comma-separated values)"]
    for k, v in data:
        ps = []
        for name, (req, desc) in v["params"].items():
            h = _hint(desc)
            ps.append(name + ("*" if req else "") + (f"[{h}]" if h else ""))
        lines.append(f"{k}|{', '.join(ps)}")
    if lookups:
        lines.append("code lookups (no params): " + ", ".join(lookups))
    return "\n".join(lines)


@safe
async def agri_data(endpoint: str, params: dict[str, Any] | None = None, limit: int = 200) -> str:
    """Fetch rows from an agri-food endpoint, e.g. endpoint='pigmeat/prices',
    params={'memberStateCodes': 'NL,DE', 'beginDate': '01/09/2026'}. Lookups take no params."""
    eps = await endpoints()
    key = _resolve(endpoint, eps)
    allowed = eps[key]["params"]
    by_lc = {p.lower(): p for p in allowed}
    query: dict[str, str] = {}
    for name, val in (params or {}).items():
        real = by_lc.get(name.lower())
        if real is None:
            raise UserError(
                f"Unknown param '{name}' for {key}. Valid: {', '.join(allowed) or 'none'}"
            )
        vals = as_list(val)
        if vals:
            query[real] = ",".join(vals)
    missing = [p for p, (req, _) in allowed.items() if req and p not in query]
    if missing:
        raise UserError(f"{key} requires: {', '.join(missing)}")
    try:
        data = await fetch_json(f"{BASE}/api/{key}", query)
    except NotFound as e:
        return f"No data for {key} with these params ({e})."
    if isinstance(data, dict):
        data = [data]
    if not data:
        return f"No data for {key} with these params."
    limit = max(1, min(limit, 2000))
    total = len(data)
    data = data[:limit]
    if not isinstance(data[0], dict):  # plain lookup list
        lines = [", ".join(cell(fmt_value(x)) for x in data)]
    else:
        cols: list[str] = []
        for r in data:
            cols += [k for k, v in r.items() if k not in cols and not isinstance(v, (dict, list))]
        table = [[fmt_value(r.get(c, "")) if r.get(c) is not None else "" for c in cols] for r in data]
        lines = compact_table(cols, table, keep_last=False)
    if total > limit:
        lines.append(f"# truncated: {limit} of {total} rows; narrow params (dates, member states)")
    return "\n".join(lines)


def register(mcp: FastMCP) -> None:
    for fn in (agri_endpoints, agri_data):
        mcp.tool(annotations=READ_ONLY, output_schema=None)(fn)
