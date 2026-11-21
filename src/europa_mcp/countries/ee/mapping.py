"""find_data map entries for Estonia: one row per StatEE table."""

from __future__ import annotations

from ... import pxweb
from ...sourcemap import Entry
from . import HINTS
from .source import SRC


async def build_statee() -> list[Entry]:
    return await pxweb.map_entries(SRC, HINTS["headline"].get(SRC.name))
