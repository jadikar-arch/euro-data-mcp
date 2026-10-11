"""Helpers shared by every country package: errors, error wrapping, text and compact tables."""

from __future__ import annotations

import functools
import json
import logging
import os
import unicodedata
from importlib.resources import files
from pathlib import Path
from typing import Any

from platformdirs import user_cache_dir

log = logging.getLogger("europa_mcp")


def setting(name: str, default: str = "", legacy: str | None = None) -> str:
    """EUROPA_<name> from the environment, falling back to its pre-rename CBS_* name."""
    return os.environ.get(f"EUROPA_{name}") or (os.environ.get(legacy) if legacy else None) or default


def load_hints(package: str) -> dict[str, Any]:
    """A country package's hand-written hints.json (sources, synonyms, keywords, entries)."""
    data = json.loads(files(package).joinpath("hints.json").read_text("utf-8"))
    return {k: data.get(k) or ({} if k != "entries" else []) for k in ("sources", "synonyms", "keywords", "entries")}


def cache_dir() -> Path:
    path = Path(setting("CACHE_DIR") or user_cache_dir("europa-mcp"))
    path.mkdir(parents=True, exist_ok=True)
    return path


class UserError(Exception):
    """A user-facing error: the message is safe to return to the model."""


class NotFound(UserError):
    pass


# Query words that never help ranking (English + Dutch; extend per language as countries are added).
STOPWORDS = set(
    "de het een en van in op voor met per naar over bij uit door is zijn wat hoe hoeveel welke "
    "the a an and of in on for with per to by from is are what how many much which latest "
    "recent current newest number total data statistics cbs nederland netherlands dutch "
    "aantal cijfers gegevens tabel hoeveelheid".split()
)


def fold(s: str) -> str:
    """Lowercase and strip accents (matches the FTS `remove_diacritics` tokenizer)."""
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).casefold()

READ_ONLY = {"readOnlyHint": True, "openWorldHint": True}


def safe(fn):
    """Turn known errors into short strings; never leak tracebacks to the model."""

    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        try:
            return await fn(*args, **kwargs)
        except UserError as e:
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
