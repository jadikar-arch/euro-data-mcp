"""Netherlands: CBS (Statistics Netherlands) open data."""

from __future__ import annotations

from fastmcp import FastMCP

from ...common import load_hints
from .index import SYNONYMS  # noqa: F401  (English → Dutch statistics terms, used by find_data)

CODE = "nl"
NAME = "Netherlands"
HINTS = load_hints(__name__)


def register(mcp: FastMCP) -> None:
    from . import cbs

    cbs.register(mcp)


def map_builders():
    from . import mapping

    return {"CBS": mapping.build_cbs}


async def start() -> None:
    from . import cbs

    cbs.ensure_sync_task()


async def stop() -> None:
    from . import client

    await client.aclose()
