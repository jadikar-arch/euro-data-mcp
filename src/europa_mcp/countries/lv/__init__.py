"""Latvia: Central Statistical Bureau of Latvia (CSB), through its PxWeb API."""

from __future__ import annotations

from fastmcp import FastMCP

from ...common import load_hints

CODE = "lv"
NAME = "Latvia"
HINTS = load_hints(__name__)

# English → Latvian statistics terms. The tables have English titles, so these let Latvian questions find them
# (find_data and csb_search apply them in both directions). Single words only.
SYNONYMS: dict[str, tuple[str, ...]] = {
    "population": (
        "iedzīvotāji",
        "iedzīvotāju",
        "iedzīvotājiem",
    ),
    "inhabitants": ("iedzīvotāji",),
    "births": (
        "dzimušie",
        "dzimušo",
    ),
    "deaths": (
        "mirušie",
        "mirušo",
    ),
    "migration": ("migrācija",),
    "immigration": ("imigrācija",),
    "emigration": ("emigrācija",),
    "households": ("mājsaimniecības",),
    "income": (
        "ienākumi",
        "ienākumu",
    ),
    "wages": (
        "alga",
        "algas",
        "darba",
    ),
    "salaries": ("alga",),
    "earnings": ("darba",),
    "employment": ("nodarbinātība",),
    "unemployment": (
        "bezdarbs",
        "bezdarba",
        "bezdarbnieki",
    ),
    "labour": ("darbaspēks",),
    "housing": ("mājokļi",),
    "dwellings": ("dzīvokļi",),
    "rent": ("īre",),
    "prices": (
        "cenas",
        "cenu",
    ),
    "inflation": (
        "inflācija",
        "inflācijas",
    ),
    "consumer": ("patēriņa",),
    "energy": ("enerģija",),
    "electricity": ("elektroenerģija",),
    "emissions": ("emisijas",),
    "environment": ("vide",),
    "education": ("izglītība",),
    "students": ("studenti",),
    "health": ("veselība",),
    "crime": ("noziegumi",),
    "traffic": ("satiksme",),
    "transport": ("transports",),
    "cars": ("automašīnas",),
    "tourism": ("tūrisms",),
    "trade": ("tirdzniecība",),
    "exports": ("eksports",),
    "imports": ("imports",),
    "gdp": ("iekšzemes",),
    "economy": ("ekonomika",),
    "debt": ("parāds",),
    "companies": ("uzņēmumi",),
    "agriculture": ("lauksaimniecība",),
    "forest": ("meži",),
    "municipality": ("pašvaldība",),
    "elections": ("vēlēšanas",),
    "pensions": ("pensijas",),
    "construction": ("būvniecība",),
}


def register(mcp: FastMCP) -> None:
    from ... import pxweb
    from .source import SRC

    pxweb.register(mcp, SRC)


def map_builders():
    from . import mapping

    return {"CSB": mapping.build_csb}


async def start() -> None:
    pass


async def stop() -> None:
    pass  # uses the shared web client, closed by the eu package
