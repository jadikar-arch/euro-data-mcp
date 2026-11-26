"""find_data map entries for Sweden: one row per SCB table."""

from __future__ import annotations

from ... import pxweb
from ...sourcemap import Entry
from . import HINTS
from .source import SRC


async def build_scb() -> list[Entry]:
    return await pxweb.map_entries(SRC, HINTS["headline"].get(SRC.name))
