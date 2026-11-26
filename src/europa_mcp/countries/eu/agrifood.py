"""EU agri-food market data (DG AGRI): prices, production and indicators per sector."""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.parse import urlencode

from fastmcp import FastMCP

from ...common import (
    EC_LICENCE,
    READ_ONLY,
    NotFound,
    UserError,
    as_list,
    cache_dir,
    cell,
    compact_table,
    fmt_value,
    fold,
    safe,
    source_line,
)
from ...web import Memo, fetch_json

log = logging.getLogger("europa_mcp")

BASE = "https://api.tech.ec.europa.eu/agrifood"
SPEC = Memo(ttl=24 * 3600)
RAW = Memo(ttl=24 * 3600)
SPEC_FILE = "agrifood-openapi.json"


async def raw_spec() -> dict[str, Any]:
    """The service's OpenAPI document. It is saved on disk after every successful download; when the
    service is down (it answers HTTP 500 for hours at times) the saved copy is used, so parameter checks and
    the find_data map keep working. Only when there is no saved copy does the outage reach the user."""
    path = cache_dir() / SPEC_FILE

    async def load():
        try:
            spec = await fetch_json(f"{BASE}/v3/api-docs")
            if not isinstance(spec, dict) or "paths" not in spec:
                raise UserError("api.tech.ec.europa.eu returned no OpenAPI document")
        except UserError as e:
            try:
                saved = json.loads(path.read_text("utf-8"))
            except (OSError, ValueError):
                raise e from None
            log.warning("agrifood: %s; using the OpenAPI copy saved on %s", e, path.stat().st_mtime)
            return saved, False
        try:
            path.write_text(json.dumps(spec), "utf-8")
        except OSError as e:
            log.info("agrifood: OpenAPI document not saved: %s", e)
        return spec, True

    spec, live = await RAW.get("raw", load)
    if not live:
        RAW.clear()  # the next call tries the live service again
    return spec


async def endpoints() -> dict[str, dict[str, Any]]:
    """endpoint ('cereal/prices') → {'params': {name: (required, description)}}, from OpenAPI."""

    async def load():
        spec = await raw_spec()
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
    if "dd/yy/yyyy" in desc:  # typo in the olive oil docs; the API takes dd/mm/yyyy
        return "dd/mm/yyyy"
    for token in (
        "dd/mm/yyyy",
        "yyyy/yyyy",
        "yyyy/yy",
        "yyyy/mm",
        "yyyy",
        "'annual' or 'monthly'",
        "'monthly' or 'short'",
    ):
        if token in desc:
            return token
    return ""


FORMATS = {  # _hint → what each (comma-separated) value must look like
    "dd/mm/yyyy": re.compile(r"(0[1-9]|[12]\d|3[01])/(0[1-9]|1[0-2])/\d{4}"),
    "yyyy/yyyy": re.compile(r"\d{4}/\d{4}"),
    "yyyy/yy": re.compile(r"\d{4}/\d{2}"),
    "yyyy/mm": re.compile(r"\d{4}/(0[1-9]|1[0-2])"),
    "yyyy": re.compile(r"\d{4}"),
    "'annual' or 'monthly'": re.compile(r"annual|monthly"),
    "'monthly' or 'short'": re.compile(r"monthly|short"),
}


def check_format(name: str, desc: str, vals: list[str]) -> None:
    """Reject a badly formatted value before the API turns it into a bare 500."""
    fmt = _hint(desc)
    pat = FORMATS.get(fmt)
    for v in vals:
        if pat and not pat.fullmatch(v):
            iso = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", v)
            tip = f"; e.g. {iso[3]}/{iso[2]}/{iso[1]}" if iso and fmt == "dd/mm/yyyy" else ""
            raise UserError(f"{name} must be {fmt} (got {v}){tip}.")


def parse_price(s: str) -> tuple[float | None, str]:
    """'€145.25' / '€233,59' / '€1.234,50' → (value, currency). The API mixes decimal separators."""
    m = re.fullmatch(r"\s*([^\d\s.,-]*)\s*(-?[\d.,]+)\s*([^\d\s.,]*)\s*", s or "")
    if not m:
        return None, ""
    sym, num = m[1] or m[3], m[2]
    if "," in num and "." in num:  # the last separator is the decimal one
        dec = "," if num.rfind(",") > num.rfind(".") else "."
        num = num.replace("." if dec == "," else ",", "").replace(dec, ".")
    elif num.count(",") == 1:
        num = num.replace(",", ".")
    elif num.count(",") > 1 or num.count(".") > 1:  # thousands only
        num = num.replace(",", "").replace(".", "")
    try:
        value = float(num)
    except ValueError:
        return None, ""
    return value, {"€": "EUR", "$": "USD", "£": "GBP"}.get(sym, sym)


def with_values(row: dict[str, Any]) -> dict[str, Any]:
    """Add numeric `value` and `currency` after a text `price` such as '€233,59'."""
    if not isinstance(row.get("price"), str):
        return row
    value, cur = parse_price(row["price"])
    if value is None:
        return row
    out: dict[str, Any] = {}
    for k, v in row.items():
        out[k] = v
        if k == "price":
            out["value"], out["currency"] = value, cur
    return out


def _resolve(name: str, eps: dict[str, Any]) -> str:
    key = name.strip().strip("/").removeprefix("api/")
    if key in eps:
        return key
    by_lc = {k.lower(): k for k in eps}
    if key.lower() in by_lc:
        return by_lc[key.lower()]
    near = [k for k in eps if fold(key.split("/")[0]) in fold(k)][:8]
    raise UserError(
        f"Unknown endpoint '{name}'." + (f" Did you mean: {', '.join(near)}?" if near else "") + " See agri_endpoints."
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
            raise UserError(f"Unknown param '{name}' for {key}. Valid: {', '.join(allowed) or 'none'}")
        vals = as_list(val)
        check_format(real, allowed[real][1], vals)
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
    data = [with_values(r) if isinstance(r, dict) else r for r in data[:limit]]
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
    url = f"{BASE}/api/{key}" + (f"?{urlencode(query)}" if query else "")
    lines.append(
        source_line(url, EC_LICENCE.replace("European Union", "European Union (DG AGRI agri-food data portal)"))
    )
    return "\n".join(lines)


def register(mcp: FastMCP) -> None:
    for fn in (agri_endpoints, agri_data):
        mcp.tool(annotations=READ_ONLY, output_schema=None)(fn)
