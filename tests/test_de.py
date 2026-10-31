"""Offline tests for Germany: GovData (CKAN) tools, Destatis GENESIS tables and the find_data map."""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from fastmcp import Client

from europa_mcp import preview, server, web
from europa_mcp.countries.de import genesis, govdata, mapping
from europa_mcp.sourcemap import SourceMap

API = govdata.API
CSV_URI = govdata.EU_FILE_TYPE + "CSV"

# Time in the column headers, regions in rows; a title that wraps onto a second line.
POP_STATES = (
    "Tabelle: 12411-0010\n"
    "Bevölkerung: Bundesländer,;;;\n"
    "Stichtag;;;\n"
    "Fortschreibung des Bevölkerungsstandes;;;\n"
    "Bevölkerungsstand (Anzahl);;;\n"
    ";Stichtag;Stichtag;Stichtag\n"
    ";31.12.2023;31.12.2024;31.12.2025\n"
    "Bayern;13176426;13248928;13245503\n"
    "Berlin;3662381;3685265;3700577\n"
    "Bremen;.;x;/\n"
    "__________\n"
    '"Berlin: bis 1989 nur Berlin-West.\n\nAb 2022: Zensus 2022."\n'
    "© Statistisches Bundesamt (Destatis), 2026\n"
    "Stand: 16.06.2026 / 18:08:29\n"
)
# Time in two label columns (year; month), measures in columns with an index base year,
# future months not yet published.
CPI = (
    "Tabelle: 61111-0002\n"
    "Verbraucherpreisindex: Deutschland, Monate;;;\n"
    "Verbraucherpreisindex für Deutschland;;;\n"
    "Deutschland;;;\n"
    ";;Verbraucherpreisindex;Veränderung zum Vorjahresmonat\n"
    ";;2020=100;in (%)\n"
    "2026;August;125,8;+2,9\n"
    "2026;September;126,6;+3,3\n"
    "2026;Oktober;...;...\n"
    "__________\n"
    "© Statistisches Bundesamt (Destatis), 2026\n"
    "Stand: 13.10.2026 / 21:42:55\n"
)


def package(name: str, org: str = "berlin-open-data", **kw) -> dict:
    return {
        "name": name, "title": kw.get("title", name.replace("-", " ").title()), "notes": "Beschreibung.",
        "organization": {"name": org, "title": org.title()}, "groups": [{"name": "soci", "display_name": "x"}],
        "tags": [{"name": "einwohner"}], "license_title": "Datenlizenz Deutschland Namensnennung 2.0",
        "metadata_modified": "2026-10-01T00:00:00",
        "extras": [{"key": "politicalGeocodingLevelURI", "value": govdata.LEVEL_URI + "municipality"},
                   {"key": "identifier", "value": kw.get("identifier", "")}],
        "resources": kw.get("resources", []),
    }


DATASETS = {
    "einwohner-berlin": package("einwohner-berlin", resources=[
        {"format": CSV_URI, "name": "Einwohner 2025", "url": "https://daten.berlin.de/einwohner.csv"},
        {"format": "PDF", "name": "Bericht", "url": "https://daten.berlin.de/bericht.pdf"},
        {"format": CSV_URI, "name": "intern", "url": "http://10.0.0.5/x.csv"},
    ]),
    "bevolkerung-bundeslander-stichtag": package(
        "bevolkerung-bundeslander-stichtag", org=govdata.DESTATIS, title="Bevölkerung: Bundesländer, Stichtag",
        identifier="https://genesis.destatis.de/genesisWS/downloads/00/tables/12411-0010_00",
        resources=[{"format": CSV_URI, "url": genesis.DOWNLOAD.format("12411-0010")}]),
    "container-binnenschifffahrt": package(  # a Destatis table listed under another publisher
        "container-binnenschifffahrt", org="mcloud",
        identifier="https://genesis.destatis.de/genesisWS/downloads/00/tables/46321-0101_00"),
}
ORGS = [
    {"name": "berlin-open-data", "title": "Berlin Open Data", "package_count": 1000},
    {"name": "land-schleswig-holstein", "title": "Land Schleswig-Holstein", "package_count": 29103},
    {"name": "land-brandenburg", "title": "Land Brandenburg", "package_count": 139},
    {"name": govdata.DESTATIS, "title": "Statistisches Bundesamt", "package_count": 3153},
]


def facet(items: dict[str, int]) -> dict:
    return {"items": [{"name": k, "display_name": k, "count": v} for k, v in items.items()]}


class FakeCKAN:
    def __init__(self):
        self.searches: list[dict] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        action = request.url.path.rsplit("/", 1)[-1]
        p = dict(request.url.params)
        ok = lambda result: httpx.Response(200, json={"success": True, "result": result})  # noqa: E731
        if action == "organization_list":
            return ok(ORGS)
        if action == "package_show":
            if p["id"] not in DATASETS:
                return httpx.Response(404, json={"success": False, "error": {"message": "Nicht gefunden"}})
            return ok(DATASETS[p["id"]])
        if action == "package_search":
            self.searches.append(p)
            fq = p.get("fq", "")
            if "facet.field" in p:
                fields = json.loads(p["facet.field"])
                f = {"organization": facet({"land-schleswig-holstein": 4210, "land-brandenburg": 5}),
                     "tags": facet({"opendata": 900, "grundwasser": 300, "pegel": 120}),
                     "res_format": facet({CSV_URI: 50, "http://publications.europa.eu/resource/authority/file-type/WMS_SRVC": 40})}
                return ok({"count": 4210 if "organization:" in fq else 56305, "results": [],
                           "search_facets": {k: f[k] for k in fields}})
            if fq.startswith("organization:" + govdata.DESTATIS):
                return ok({"count": 1, "results": [{
                    "name": "bevolkerung-bundeslander-stichtag", "title": "Bevölkerung: Bundesländer, Stichtag",
                    "tags": ["bayern", "bundesländer", "januar", "opendata"], "groups": ["soci"],
                    "identifier": "https://genesis.destatis.de/genesisWS/downloads/00/tables/12411-0010_00",
                    "modified": "2026-06-16T18:08:29"}]})
            if "nichts" in p.get("q", ""):
                return ok({"count": 0, "results": []})
            return ok({"count": 42, "results": [
                {"name": "einwohner-berlin", "title": "Einwohner in Berlin", "organization": "berlin-open-data",
                 "res_format": [CSV_URI, "PDF"], "metadata_modified": "2026-10-01T00:00:00"},
                {"name": "bevolkerung-bundeslander-stichtag", "title": "Bevölkerung: Bundesländer, Stichtag",
                 "organization": govdata.DESTATIS, "res_format": [CSV_URI],
                 "identifier": "https://genesis.destatis.de/genesisWS/downloads/00/tables/12411-0010_00",
                 "metadata_modified": "2026-06-16T00:00:00"},
            ]})
        return httpx.Response(404, json={"success": False, "error": {"message": "unknown action"}})


@pytest.fixture(autouse=True)
async def fresh():
    govdata.ORGS.clear()
    genesis.TABLES.clear()
    yield
    await web.aclose()


@pytest.fixture
def fake():
    ckan = FakeCKAN()
    with respx.mock(assert_all_called=False) as mock:
        mock.route(url__startswith=API).mock(side_effect=ckan)
        mock.get(genesis.DOWNLOAD.format("12411-0010")).respond(200, content=POP_STATES.encode("latin-1"))
        mock.get(genesis.DOWNLOAD.format("61111-0002")).respond(200, content=CPI.encode("latin-1"))
        mock.get(genesis.DOWNLOAD.format("99999-9999")).respond(404, text="Not Found")
        mock.get("https://daten.berlin.de/einwohner.csv").respond(
            200, content="Bezirk;Einwohner\nMitte;397134\nPankow;424307\n".encode("utf-8"))
        yield ckan


async def call(tool: str, **args) -> str:
    async with Client(server.mcp) as c:
        result = await c.call_tool(tool, args, raise_on_error=False)
    return "".join(getattr(b, "text", "") for b in result.content)


# ---- Destatis GENESIS tables ------------------------------------------------------


def test_parse_wrapped_title_headers_and_notes():
    t = genesis.parse("12411-0010", POP_STATES)
    assert t.title == "Bevölkerung: Bundesländer, Stichtag"
    assert t.meta == ["Fortschreibung des Bevölkerungsstandes", "Bevölkerungsstand (Anzahl)"]
    assert t.columns == ["Stichtag 31.12.2023", "Stichtag 31.12.2024", "Stichtag 31.12.2025"]
    assert t.rows[0] == (("Bayern",), ["13176426", "13248928", "13245503"])
    assert (t.stand, t.notes) == ("16.06.2026", "Berlin: bis 1989 nur Berlin-West. Ab 2022: Zensus 2022.")


async def test_table_time_in_columns_query_and_last_n(fake):
    out = await call("govdata_table", table_id="12411-0010", query="berlin", last_n=2)
    assert out.splitlines()[:3] == [
        "12411-0010: Bevölkerung: Bundesländer, Stichtag",
        "about: Fortschreibung des Bevölkerungsstandes; Bevölkerungsstand (Anzahl)", "as of: 16.06.2026"]
    assert "fixed: label=Berlin\nperiod|value\nStichtag 31.12.2025|3700577\nStichtag 31.12.2024|3685265\n" in out
    assert "notes: Berlin: bis 1989" in out


async def test_table_time_in_rows_skips_unpublished_and_base_year(fake):
    out = await call("govdata_table", table_id="61111-0002", last_n=1)
    assert "fixed: period=2026; period2=September" in out  # Oktober is '...' (not yet published)
    assert "Verbraucherpreisindex 2020=100|126.6" in out  # German decimal converted
    assert "Veränderung zum Vorjahresmonat in (%)|+3.3" in out


async def test_table_symbols_truncation_and_errors(fake):
    out = await call("govdata_table", table_id="12411-0010", query="Bremen")
    assert "# symbols: . = secret; / = too uncertain; x = not applicable" in out
    out = await call("govdata_table", table_id="12411-0010_00", limit=2)
    assert "# truncated: 2 of 9 values; add query= or last_n=" in out
    assert "# first-column labels: Bayern, Berlin, Bremen" in out
    assert (await call("govdata_table", table_id="12411-0010", query="Hamburg")).splitlines()[-1] == \
        "# rows: Bayern, Berlin, Bremen"
    assert (await call("govdata_table", table_id="99999-9999")).startswith("Error: Unknown Destatis table")
    assert (await call("govdata_table", table_id="population")).startswith("Error: 'population' is not a GENESIS")


# ---- GovData catalogue ----------------------------------------------------------------


def test_solr_query_translates_and_boosts_titles():
    q = govdata.solr_query("Population Berlin")
    assert q == ("text:(population OR bevölkerung OR einwohner) AND text:(berlin) AND "
                 "(title:(population OR bevölkerung OR einwohner OR berlin)^5 OR *:*)")
    assert govdata.solr_query("  ") == "*:*"


async def test_search_filters_and_destatis_values_column(fake):
    out = await call("govdata_search", query="einwohner", theme="Population", publisher="berlin",
                     format="csv", level="Gemeinde", limit=2)
    fq = fake.searches[-1]["fq"]
    assert "groups:soci" in fq and "organization:berlin-open-data" in fq
    assert f'res_format:("CSV" OR "{CSV_URI}"' in fq
    assert f'extras_politicalGeocodingLevelURI:"{govdata.LEVEL_URI}municipality"' in fq
    lines = out.splitlines()
    assert lines[0] == "id|title|publisher|formats|modified|values"
    assert lines[1] == "einwohner-berlin|Einwohner in Berlin|berlin-open-data|CSV,PDF|2026-10-01|"
    assert lines[2].endswith('|statistisches-bundesamt|CSV|2026-06-16|govdata_table("12411-0010")')
    assert lines[-1] == "# 2 of 42; page=1 for more, or add theme/publisher/format filters"


async def test_search_errors(fake):
    assert (await call("govdata_search", query="nichts")).startswith("No GovData datasets match")
    assert (await call("govdata_search", query="x", theme="space")).startswith("Error: Unknown theme 'space'. Valid: envi")
    out = await call("govdata_search", query="x", publisher="land")
    assert out.startswith("Error: Publisher 'land' is ambiguous: land-schleswig-holstein")
    assert (await call("govdata_search", query="x", level="planet")).startswith("Error: Unknown level")


async def test_dataset_details(fake):
    out = await call("govdata_dataset", dataset_id="bevolkerung-bundeslander-stichtag")
    assert "themes: Population and society" in out
    assert "level: municipality" in out
    assert 'values: govdata_table("12411-0010")' in out
    out = await call("govdata_dataset", dataset_id="einwohner-berlin")
    assert "1|CSV|Einwohner 2025|https://daten.berlin.de/einwohner.csv" in out
    assert (await call("govdata_dataset", dataset_id="nope")).startswith("Error: Unknown dataset 'nope'")


async def test_preview_csv_and_refusals(fake):
    out = await call("govdata_preview", dataset_id="einwohner-berlin", file=1)
    assert out.splitlines()[:4] == ["einwohner-berlin file 1: CSV, 2 columns", "Bezirk|Einwohner",
                                    "Mitte|397134", "Pankow|424307"]
    assert out.splitlines()[-1].startswith("source: https://daten.berlin.de/einwohner.csv · licence: ")
    assert (await call("govdata_preview", dataset_id="einwohner-berlin", file=2)).startswith(
        "Error: einwohner-berlin file 2 is PDF; only CSV/JSON can be previewed")
    assert (await call("govdata_preview", dataset_id="einwohner-berlin", file=3)).startswith("Error: Can't preview")
    assert (await call("govdata_preview", dataset_id="einwohner-berlin", file=9)).startswith("Error: file must be 1..3")
    out = await call("govdata_preview", dataset_id="bevolkerung-bundeslander-stichtag")
    assert out == 'This is Destatis table 12411-0010; use govdata_table("12411-0010") for its values.'


def test_json_rows_reads_geojson_and_wrapped_lists():
    geo = {"type": "FeatureCollection", "features": [{"properties": {"name": "A", "n": 1}}]}
    assert preview.json_rows(geo) == [["name", "n"], ["A", "1"]]
    assert preview.json_rows({"meta": 1, "data": [{"a": {"b": 2}}]}) == [["a"], ['{"b": 2}']]


# ---- find_data map ---------------------------------------------------------------------


async def test_map_builders(fake):
    rows = await mapping.build_destatis()
    assert rows == [{
        "source": "Destatis", "id": "12411-0010", "title": "Bevölkerung: Bundesländer, Stichtag",
        "path": "Destatis > Population and society", "keywords": "bayern bundesländer", "period": "",
        "updated": "2026-06-16", "call": 'govdata_table("12411-0010")'}]
    rows = {r["id"]: r for r in await mapping.build_catalogue()}
    assert len(rows) == len(govdata.THEMES) + len(govdata.THEMES)  # one slice per theme (Brandenburg < 20)
    envi = rows["envi/land-schleswig-holstein"]
    assert envi["title"] == "Environment data from Land Schleswig-Holstein: 4,210 datasets"
    assert envi["keywords"] == "Umwelt grundwasser pegel CSV WMS"  # 'opendata' is noise
    assert envi["call"] == 'govdata_search("<German keywords>", theme="envi", publisher="land-schleswig-holstein")'
    assert rows["envi"]["title"] == "Environment (Umwelt): 56,305 datasets"


async def test_find_data_reaches_german_tables_in_english_and_german(tmp_path, fake, monkeypatch):
    m = SourceMap(tmp_path / "map.db", synonyms=server.all_synonyms())
    m.replace("Destatis", await mapping.build_destatis())
    monkeypatch.setattr(server, "SOURCE_MAP", m)
    for q in ("population by state", "Bevölkerung Bundesländer"):
        out = await call("find_data", query=q, sources=["Destatis"])
        assert '12411-0010|Bevölkerung: Bundesländer, Stichtag|Population and society||govdata_table("12411-0010")' in out


async def test_destatis_table_found_by_url_whatever_the_publisher(fake):
    out = await call("govdata_dataset", dataset_id="container-binnenschifffahrt")
    assert 'values: govdata_table("46321-0101")' in out
    assert govdata.table_id("https://example.org/tables/46321-0101_00") == ""  # not a Destatis URL
