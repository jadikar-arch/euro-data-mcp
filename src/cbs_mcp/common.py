"""Helpers shared by every tool module: error wrapping and compact text tables."""

from __future__ import annotations

import functools
import logging
from typing import Any

from .client import CBSError

log = logging.getLogger("cbs_mcp")

READ_ONLY = {"readOnlyHint": True, "openWorldHint": True}


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


def clip(s: Any, n: int = 200) -> str:
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[:n].rsplit(" ", 1)[0] + "…"


def compact_table(cols: list[str], table: list[list[str]], keep_last: bool = True) -> list[str]:
    """`fixed: col=v; …` for columns constant across rows, then a `|` table of the rest."""
    if not table:
        return []
    last = len(cols) - 1
    keep = [
        i for i in range(len(cols))
        if (keep_last and i == last) or len({t[i] for t in table}) > 1
    ] or [last]
    out = []
    fixed = [f"{cols[i]}={table[0][i]}" for i in range(len(cols)) if i not in keep and table[0][i]]
    if fixed:
        out.append("fixed: " + "; ".join(cell(f) for f in fixed))
    out.append("|".join(cell(cols[i]) for i in keep))
    out += ["|".join(cell(t[i]) for i in keep) for t in table]
    return out


def as_list(v: Any) -> list[str]:
    """Accept 'a', 'a,b' or ['a','b'] from the model."""
    if v is None:
        return []
    items = v if isinstance(v, (list, tuple, set)) else str(v).split(",")
    return [s for s in (str(x).strip() for x in items) if s]
