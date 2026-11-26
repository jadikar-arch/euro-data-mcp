"""find_data map entries for Latvia: one row per CSB table."""

from __future__ import annotations

from ... import pxweb
from ...sourcemap import Entry
from . import HINTS
from .source import SRC


async def build_csb() -> list[Entry]:
    return await pxweb.map_entries(SRC, HINTS["headline"].get(SRC.name))
