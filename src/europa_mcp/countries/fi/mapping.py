"""find_data map entries for Finland: one row per StatFin table."""

from __future__ import annotations

from ... import pxweb
from ...sourcemap import Entry
from . import HINTS
from .source import SRC


async def build_statfin() -> list[Entry]:
    return await pxweb.map_entries(SRC, HINTS["headline"].get(SRC.name))
