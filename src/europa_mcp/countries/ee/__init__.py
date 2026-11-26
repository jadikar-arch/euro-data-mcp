"""Estonia: Statistics Estonia, through its PxWeb API."""

from __future__ import annotations

from fastmcp import FastMCP

from ...common import load_hints

CODE = "ee"
NAME = "Estonia"
HINTS = load_hints(__name__)

# English → Estonian statistics terms. The tables have English titles, so these let Estonian questions find them
# (find_data and statee_search apply them in both directions). Single words only.
SYNONYMS: dict[str, tuple[str, ...]] = {
    "population": (
        "rahvastik",
        "rahvaarv",
        "rahvastiku",
        "rahvaarvu",
        "elanikkond",
    ),
    "inhabitants": ("elanikud",),
    "births": (
        "sünnid",
        "sündide",
        "sündimus",
    ),
    "deaths": (
        "surmad",
        "surmade",
        "suremus",
    ),
    "migration": ("ränne",),
    "immigration": ("sisseränne",),
    "emigration": ("väljaränne",),
    "households": ("leibkonnad",),
    "income": (
        "sissetulek",
        "sissetulekud",
    ),
    "wages": (
        "palk",
        "palgad",
        "palgaandmed",
    ),
    "salaries": ("palk",),
    "earnings": ("palk",),
    "employment": ("tööhõive",),
    "unemployment": (
        "töötus",
        "töötuse",
        "töötud",
    ),
    "labour": ("tööjõud",),
    "housing": ("eluase",),
    "dwellings": ("eluruumid",),
    "rent": ("üür",),
    "prices": (
        "hinnad",
        "hindade",
        "hinnaindeks",
    ),
    "inflation": (
        "inflatsioon",
        "inflatsiooni",
    ),
    "consumer": (
        "tarbija",
        "tarbijahinnad",
        "tarbijahinnaindeks",
    ),
    "energy": ("energia",),
    "electricity": ("elekter",),
    "emissions": ("heitkogused",),
    "environment": ("keskkond",),
    "education": ("haridus",),
    "students": (
        "õpilased",
        "üliõpilased",
    ),
    "health": ("tervis",),
    "crime": ("kuriteod",),
    "traffic": ("liiklus",),
    "transport": ("transport",),
    "cars": ("sõiduautod",),
    "tourism": ("turism",),
    "trade": ("kaubandus",),
    "exports": ("eksport",),
    "imports": ("import",),
    "gdp": ("skp",),
    "economy": ("majandus",),
    "debt": ("võlg",),
    "companies": ("ettevõtted",),
    "agriculture": ("põllumajandus",),
    "forest": ("mets",),
    "municipality": ("omavalitsus",),
    "county": ("maakond",),
    "elections": ("valimised",),
    "pensions": ("pensionid",),
    "construction": ("ehitus",),
}


def register(mcp: FastMCP) -> None:
    from ... import pxweb
    from .source import SRC

    pxweb.register(mcp, SRC)


def map_builders():
    from . import mapping

    return {"StatEE": mapping.build_statee}


async def start() -> None:
    pass


async def stop() -> None:
    pass  # uses the shared web client, closed by the eu package
