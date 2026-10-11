"""<Country name>: <source names, e.g. Statistics <Country> (<acronym>)>."""

from __future__ import annotations

from fastmcp import FastMCP

from ...common import load_hints

CODE = "<cc>"  # ISO 3166-1 alpha-2, lowercase
NAME = "<Country name in English>"
HINTS = load_hints(__name__)

# English → local-language statistics terms; find_data applies them in both directions so
# English queries find local titles and local queries find English titles.
SYNONYMS: dict[str, tuple[str, ...]] = {
    # "population": ("<local word>",),
}


def register(mcp: FastMCP) -> None:
    from . import source  # rename: one module per API, e.g. ssb.py

    source.register(mcp)


def map_builders():
    from . import mapping

    return {"<SOURCE>": mapping.build_source}  # key: builder name, unique server-wide


async def start() -> None:
    """Start background work (e.g. a catalogue index sync). Most countries need nothing."""


async def stop() -> None:
    """Close clients that are not the shared `web` client."""
