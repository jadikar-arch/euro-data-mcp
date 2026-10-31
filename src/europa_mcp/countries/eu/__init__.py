"""EU level: Eurostat and DG EMPL/GROW/TAXUD, agri-food markets, European Parliament, data.europa.eu."""

from __future__ import annotations

from fastmcp import FastMCP

from ... import web
from ...common import load_hints

CODE = "eu"
NAME = "European Union"
HINTS = load_hints(__name__)
SYNONYMS: dict[str, list[str]] = {}  # English titles; EU-specific synonyms are in hints.json


def register(mcp: FastMCP) -> None:
    from . import agrifood, dataeuropa, europarl, eurostat

    for module in (eurostat, agrifood, europarl, dataeuropa):
        module.register(mcp)


def map_builders():
    from . import mapping

    return {
        "Eurostat": mapping.build_eurostat,
        "DG": mapping.build_dg,
        "Agrifood": mapping.build_agrifood,
        "European Parliament": mapping.build_europarl,
        "data.europa.eu": mapping.build_dataeu,
        "eu-curated": mapping.build_curated,
    }


async def start() -> None:
    pass


async def stop() -> None:
    await web.aclose()
