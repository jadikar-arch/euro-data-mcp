"""Netherlands: CBS (Statistics Netherlands) open data."""

from __future__ import annotations

from fastmcp import FastMCP

from ...common import load_hints

CODE = "nl"
NAME = "Netherlands"
HINTS = load_hints(__name__)

# English → Dutch statistics terms (the CBS catalogue is Dutch only). cbs_search ORs them into the
# query and find_data applies them in both directions, so English questions find Dutch titles.
SYNONYMS: dict[str, tuple[str, ...]] = {
    "population": ("bevolking", "inwoners"),
    "inhabitants": ("inwoners", "bevolking"),
    "people": ("personen", "bevolking"),
    "births": ("geboorte", "geborenen"),
    "deaths": ("overledenen", "sterfte"),
    "mortality": ("sterfte",),
    "migration": ("migratie",),
    "immigration": ("immigratie",),
    "emigration": ("emigratie",),
    "age": ("leeftijd",),
    "gender": ("geslacht",),
    "sex": ("geslacht",),
    "households": ("huishoudens",),
    "household": ("huishoudens",),
    "income": ("inkomen",),
    "wages": ("lonen",),
    "salary": ("lonen",),
    "employment": ("werkgelegenheid", "werkzame"),
    "unemployment": ("werkloosheid", "werkloze"),
    "jobs": ("banen",),
    "labour": ("arbeid",),
    "labor": ("arbeid",),
    "housing": ("woningen", "woon"),
    "houses": ("woningen", "koopwoningen"),
    "homes": ("woningen",),
    "dwellings": ("woningen",),
    "rent": ("huur",),
    "prices": ("prijzen", "prijs", "verkoopprijzen"),
    "inflation": ("inflatie", "cpi"),
    "consumer": ("consumenten",),
    "energy": ("energie",),
    "gas": ("aardgas", "gas"),
    "electricity": ("elektriciteit",),
    "emissions": ("emissies",),
    "environment": ("milieu",),
    "education": ("onderwijs",),
    "students": ("studenten", "leerlingen"),
    "health": ("gezondheid",),
    "healthcare": ("zorg",),
    "crime": ("criminaliteit", "misdrijven"),
    "traffic": ("verkeer",),
    "transport": ("vervoer", "verkeer"),
    "cars": ("personenauto",),
    "tourism": ("toerisme",),
    "hotels": ("logies",),
    "trade": ("handel",),
    "exports": ("uitvoer", "export"),
    "imports": ("invoer", "import"),
    "economy": ("economie",),
    "gdp": ("bbp", "bruto"),
    "government": ("overheid",),
    "debt": ("schuld",),
    "companies": ("bedrijven",),
    "businesses": ("bedrijven",),
    "bankruptcies": ("faillissementen",),
    "agriculture": ("landbouw",),
    "municipality": ("gemeente",),
    "municipalities": ("gemeenten",),
    "region": ("regio",),
    "regional": ("regio",),
    "province": ("provincie",),
    "neighbourhood": ("wijken", "buurten"),
    "neighborhood": ("wijken", "buurten"),
    "monthly": ("maand",),
    "quarterly": ("kwartaal",),
    "yearly": ("jaar",),
    "annual": ("jaar",),
    "social": ("sociale",),
    "benefits": ("uitkeringen",),
    "pensions": ("pensioen",),
    "religion": ("religie",),
    "elections": ("verkiezingen",),
    "construction": ("bouw",),
}


def register(mcp: FastMCP) -> None:
    from . import cbs

    cbs.register(mcp)


def map_builders():
    from . import mapping

    return {"CBS": mapping.build_cbs}


async def start() -> None:
    pass


async def stop() -> None:
    pass  # uses the shared web client, closed by the eu package
