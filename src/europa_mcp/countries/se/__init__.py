"""Sweden: Statistics Sweden (SCB), through its PxWeb API."""

from __future__ import annotations

from fastmcp import FastMCP

from ...common import load_hints

CODE = "se"
NAME = "Sweden"
HINTS = load_hints(__name__)

# English → Swedish statistics terms. The tables have English titles, so these let Swedish questions find them
# (find_data and scb_search apply them in both directions). Single words only.
SYNONYMS: dict[str, tuple[str, ...]] = {
    "population": (
        "befolkning",
        "folkmängd",
        "befolkningen",
        "folkmängden",
    ),
    "inhabitants": ("invånare",),
    "births": (
        "födda",
        "födelser",
    ),
    "deaths": (
        "döda",
        "dödsfall",
    ),
    "migration": (
        "flyttningar",
        "migration",
    ),
    "immigration": ("invandring",),
    "emigration": ("utvandring",),
    "households": ("hushåll",),
    "income": (
        "inkomst",
        "inkomster",
        "inkomsterna",
    ),
    "wages": (
        "löner",
        "lönerna",
    ),
    "salaries": ("löner",),
    "earnings": ("förvärvsinkomster",),
    "employment": (
        "sysselsättning",
        "sysselsatta",
    ),
    "unemployment": (
        "arbetslöshet",
        "arbetslösa",
        "arbetslösheten",
    ),
    "labour": ("arbetskraft",),
    "housing": (
        "bostäder",
        "boende",
    ),
    "dwellings": ("bostäder",),
    "rent": (
        "hyra",
        "hyror",
    ),
    "prices": (
        "priser",
        "priserna",
        "konsumentpriser",
    ),
    "inflation": (
        "inflation",
        "inflationen",
    ),
    "consumer": (
        "konsument",
        "konsumentprisindex",
    ),
    "energy": ("energi",),
    "electricity": (
        "el",
        "elektricitet",
    ),
    "emissions": ("utsläpp",),
    "environment": ("miljö",),
    "education": ("utbildning",),
    "students": (
        "studenter",
        "elever",
    ),
    "schools": ("skolor",),
    "health": ("hälsa",),
    "hospitals": ("sjukhus",),
    "crime": (
        "brott",
        "brottslighet",
    ),
    "traffic": ("trafik",),
    "transport": ("transporter",),
    "cars": (
        "personbilar",
        "bilar",
    ),
    "vehicles": ("fordon",),
    "tourism": ("turism",),
    "trade": ("handel",),
    "exports": ("export",),
    "imports": ("import",),
    "gdp": ("bnp",),
    "economy": ("ekonomi",),
    "government": ("offentlig",),
    "debt": ("skuld",),
    "companies": ("företag",),
    "agriculture": ("jordbruk",),
    "forest": ("skog",),
    "municipality": ("kommun",),
    "municipalities": ("kommuner",),
    "county": ("län",),
    "elections": ("val",),
    "pensions": ("pensioner",),
    "construction": ("byggande",),
}


def register(mcp: FastMCP) -> None:
    from ... import pxweb
    from .source import SRC

    pxweb.register(mcp, SRC)


def map_builders():
    from . import mapping

    return {"SCB": mapping.build_scb}


async def start() -> None:
    pass


async def stop() -> None:
    pass  # uses the shared web client, closed by the eu package
