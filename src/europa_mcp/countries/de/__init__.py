"""Germany: GovData (the national open data catalogue) and Destatis GENESIS tables linked from it."""

from __future__ import annotations

from fastmcp import FastMCP

from ...common import load_hints

CODE = "de"
NAME = "Germany"
HINTS = load_hints(__name__)

# English → German terms; govdata_search ORs them into the query and find_data applies them in
# both directions, so English questions find German titles.
SYNONYMS: dict[str, tuple[str, ...]] = {
    "population": ("bevölkerung", "einwohner"),
    "inhabitants": ("einwohner", "bevölkerung"),
    "residents": ("einwohner",),
    "births": ("geburten", "geborene"),
    "deaths": ("sterbefälle", "gestorbene"),
    "migration": ("wanderungen", "zuzüge", "fortzüge"),
    "foreigners": ("ausländer",),
    "households": ("haushalte",),
    "unemployment": ("arbeitslosigkeit", "arbeitslose"),
    "unemployed": ("arbeitslose",),
    "employment": ("erwerbstätige", "beschäftigte"),
    "employees": ("beschäftigte", "arbeitnehmer"),
    "jobs": ("beschäftigte", "erwerbstätige"),
    "wages": ("verdienste", "löhne"),
    "earnings": ("verdienste",),
    "income": ("einkommen",),
    "prices": ("preise", "preisindex", "preisindizes"),
    "price": ("preise", "preisindex", "preisindizes"),
    "inflation": ("verbraucherpreisindex",),
    "cpi": ("verbraucherpreisindex",),
    "housing": ("wohnungen", "wohnen", "wohngebäude"),
    "house": ("häuserpreisindex", "wohnimmobilien", "wohnungen"),
    "rent": ("miete", "mieten"),
    "construction": ("baugenehmigungen", "baufertigstellungen", "bau"),
    "buildings": ("gebäude",),
    "gdp": ("bruttoinlandsprodukt",),
    "economy": ("wirtschaft",),
    "industry": ("industrie", "verarbeitendes"),
    "companies": ("unternehmen", "betriebe"),
    "insolvencies": ("insolvenzen",),
    "trade": ("handel", "außenhandel"),
    "exports": ("ausfuhr", "exporte"),
    "imports": ("einfuhr", "importe"),
    "retail": ("einzelhandel",),
    "tourism": ("tourismus", "übernachtungen", "gäste"),
    "overnight": ("übernachtungen",),
    "nights": ("übernachtungen",),
    "stays": ("übernachtungen", "aufenthaltsdauer"),
    "arrivals": ("ankünfte",),
    "guests": ("gäste",),
    "hotels": ("beherbergungsbetriebe",),
    "transport": ("verkehr",),
    "traffic": ("verkehr", "verkehrszählung"),
    "accidents": ("unfälle", "verkehrsunfälle"),
    "energy": ("energie",),
    "electricity": ("strom", "elektrizität"),
    "gas": ("erdgas",),
    "emissions": ("emissionen", "treibhausgase"),
    "environment": ("umwelt",),
    "climate": ("klima",),
    "weather": ("wetter",),
    "water": ("wasser", "gewässer"),
    "groundwater": ("grundwasser",),
    "air": ("luft", "luftqualität"),
    "waste": ("abfall", "abfälle"),
    "noise": ("lärm",),
    "agriculture": ("landwirtschaft",),
    "farms": ("landwirtschaftliche", "betriebe"),
    "harvest": ("ernte",),
    "livestock": ("viehbestand", "tiere"),
    "forest": ("wald", "forst"),
    "food": ("lebensmittel", "nahrungsmittel"),
    "health": ("gesundheit",),
    "hospitals": ("krankenhäuser",),
    "education": ("bildung",),
    "schools": ("schulen", "schüler"),
    "students": ("studierende", "schüler"),
    "universities": ("hochschulen",),
    "crime": ("kriminalität", "straftaten"),
    "elections": ("wahlen", "wahl"),
    "budget": ("haushalt",),
    "taxes": ("steuern",),
    "tax": ("steuer", "steuern"),
    "debt": ("schulden",),
    "municipalities": ("gemeinden",),
    "municipality": ("gemeinde", "gemeinden"),
    "districts": ("kreise", "landkreise"),
    "states": ("bundesländer", "länder"),
    "map": ("karte",),
    "maps": ("karten",),
    "zoning": ("bebauungsplan", "bauleitplanung"),
    "cycling": ("radverkehr", "fahrrad"),
    "monuments": ("denkmal", "denkmäler"),
    "geodata": ("geodaten",),
}


def register(mcp: FastMCP) -> None:
    from . import genesis, govdata

    govdata.register(mcp)
    genesis.register(mcp)


def map_builders():
    from . import mapping

    return {"Destatis": mapping.build_destatis, "GovData": mapping.build_catalogue}


async def start() -> None:
    pass


async def stop() -> None:
    pass  # uses the shared web client, closed by the eu package
