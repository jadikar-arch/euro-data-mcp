"""Finland: Statistics Finland, through its PxWeb API."""

from __future__ import annotations

from fastmcp import FastMCP

from ...common import load_hints

CODE = "fi"
NAME = "Finland"
HINTS = load_hints(__name__)

# English → Finnish statistics terms. The tables have English titles, so these let Finnish questions find them
# (find_data and statfin_search apply them in both directions). Single words only.
SYNONYMS: dict[str, tuple[str, ...]] = {
    "population": (
        "väestö",
        "väestön",
        "väkiluku",
    ),
    "inhabitants": ("asukkaat",),
    "births": (
        "syntyneet",
        "syntyvyys",
        "syntyneiden",
        "syntyvyyden",
    ),
    "deaths": (
        "kuolleet",
        "kuolemat",
        "kuolleiden",
    ),
    "migration": (
        "muuttoliike",
        "muutto",
    ),
    "immigration": ("maahanmuutto",),
    "emigration": ("maastamuutto",),
    "households": (
        "kotitaloudet",
        "asuntokunnat",
    ),
    "income": (
        "tulot",
        "tulojen",
    ),
    "wages": (
        "palkat",
        "palkkojen",
    ),
    "salaries": ("palkat",),
    "earnings": ("ansiot",),
    "employment": (
        "työllisyys",
        "työlliset",
    ),
    "unemployment": (
        "työttömyys",
        "työttömät",
        "työttömyyden",
        "työttömyysaste",
    ),
    "labour": ("työvoima",),
    "housing": (
        "asuminen",
        "asunnot",
    ),
    "dwellings": ("asunnot",),
    "rent": ("vuokrat",),
    "prices": (
        "hinnat",
        "hintojen",
        "hintaindeksi",
    ),
    "inflation": (
        "inflaatio",
        "inflaation",
    ),
    "consumer": (
        "kuluttaja",
        "kuluttajahinnat",
        "kuluttajahintaindeksi",
    ),
    "energy": ("energia",),
    "electricity": ("sähkö",),
    "emissions": ("päästöt",),
    "environment": ("ympäristö",),
    "education": ("koulutus",),
    "students": ("opiskelijat",),
    "health": ("terveys",),
    "crime": ("rikokset",),
    "traffic": ("liikenne",),
    "transport": ("kuljetus",),
    "cars": (
        "henkilöautot",
        "autot",
    ),
    "tourism": ("matkailu",),
    "trade": ("kauppa",),
    "exports": ("vienti",),
    "imports": ("tuonti",),
    "gdp": ("bruttokansantuote",),
    "economy": ("talous",),
    "debt": ("velka",),
    "companies": ("yritykset",),
    "agriculture": ("maatalous",),
    "forest": ("metsä",),
    "municipality": ("kunta",),
    "municipalities": ("kunnat",),
    "elections": ("vaalit",),
    "pensions": ("eläkkeet",),
    "construction": ("rakentaminen",),
}


def register(mcp: FastMCP) -> None:
    from ... import pxweb
    from .source import SRC

    pxweb.register(mcp, SRC)


def map_builders():
    from . import mapping

    return {"StatFin": mapping.build_statfin}


async def start() -> None:
    pass


async def stop() -> None:
    pass  # uses the shared web client, closed by the eu package
