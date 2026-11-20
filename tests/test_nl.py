"""Offline tests for the Netherlands: CBS OData tools and the find_data map builder."""

from __future__ import annotations

import httpx
import pytest
import respx

from europa_mcp import server
from europa_mcp.countries.nl import cbs, mapping
from europa_mcp.sourcemap import SourceMap

BASE = cbs.BASE
DESC = "Aantal inwoners per regio. Gegevens beschikbaar vanaf: 1995 tot en met 2026."
CATALOG = [
    {
        "Identifier": "37230ned",
        "Title": "Bevolkingsontwikkeling; regio per maand",
        "Description": DESC,
        "Status": "Regulier",
        "Modified": "2026-11-13T00:00:00+01:00",
        "ObservationCount": 1000,
    },
    {
        "Identifier": "83625NED",
        "Title": "Werkloosheid; leeftijd",
        "Description": "Werklozen naar leeftijd. Gegevens beschikbaar vanaf: 2003.",
        "Status": "Regulier",
        "Modified": "2026-10-01T00:00:00+02:00",
        "ObservationCount": 500,
    },
    {
        "Identifier": "70072NED",
        "Title": "Bevolking; oude tabel",
        "Description": "Oude bevolkingscijfers.",
        "Status": "Gediscontinueerd",
        "Modified": "2015-01-01T00:00:00+01:00",
        "ObservationCount": 10,
    },
]
DIMS = [
    {
        "Identifier": "RegioS",
        "Title": "Regio's",
        "Kind": "GeoDimension",
        "CodesUrl": f"{BASE}/CBS/37230ned/RegioSCodes",
        "GroupsUrl": f"{BASE}/CBS/37230ned/RegioSGroups",
    },
    {
        "Identifier": "Perioden",
        "Title": "Perioden",
        "Kind": "TimeDimension",
        "CodesUrl": f"{BASE}/CBS/37230ned/PeriodenCodes",
        "GroupsUrl": "",
    },
]
MEASURES = [
    {"Identifier": "M000098", "Title": "Bevolking aan het begin van de periode", "Unit": "aantal"},
    {"Identifier": "M000099", "Title": "Levend geborenen", "Unit": "aantal"},
    {"Identifier": "M1", "Title": "Seizoengecorrigeerd", "Unit": "x 1000", "MeasureGroupId": "mg1"},
    {"Identifier": "M2", "Title": "Seizoengecorrigeerd", "Unit": "%", "MeasureGroupId": "mg2"},
]
REGIONS = [
    {"Identifier": "GM0363", "Title": "Amsterdam", "DimensionGroupId": "g1"},
    {"Identifier": "GM0518", "Title": "'s-Gravenhage (gemeente)", "DimensionGroupId": "g1"},
    {"Identifier": "PV27", "Title": "Noord-Holland", "DimensionGroupId": "g2"},
]
PERIODS = [
    {"Identifier": "2026MM08", "Title": "2026 augustus", "Status": "Voorlopig"},
    {"Identifier": "2025JJ00", "Title": "2025", "Status": "Definitief"},
]
OBS = [
    {
        "Measure": "M000098",
        "Value": 933680.0,
        "StringValue": "933680",
        "ValueAttribute": "None",
        "RegioS": "GM0363",
        "Perioden": "2026MM08",
    },
    {
        "Measure": "M000099",
        "Value": None,
        "StringValue": "",
        "ValueAttribute": "Impossible",
        "RegioS": "GM0363",
        "Perioden": "2026MM08",
    },
]


def odata(rows: list[dict], count: int | None = None) -> httpx.Response:
    body: dict = {"value": rows}
    if count is not None:
        body["@odata.count"] = count
    return httpx.Response(200, json=body)


class Fake:
    """Routes CBS requests by path; remembers the last Observations query."""

    def __init__(self) -> None:
        self.obs_params: dict[str, str] = {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/odata/v1")
        q = dict(request.url.params)
        if path == "/Datasets":
            return odata(CATALOG)
        if path == "/ReleaseCalendar":
            return odata([{"DatasetIdentifier": "37230NED", "ReleaseDate": "2026-11-20T00:00:00+01:00"}], 1)
        if path.startswith("/CBS/99999"):
            return httpx.Response(404, json={"error": {"message": "not found"}})
        if path == "/CBS/37230ned/Dimensions":
            return odata(DIMS)
        if path == "/CBS/37230ned/MeasureCodes":
            return odata(MEASURES)
        if path == "/CBS/37230ned/MeasureGroups":
            return odata(
                [
                    {"Id": "mg1", "Title": "Groei", "ParentId": None},
                    {"Id": "mg2", "Title": "Natuurlijk", "ParentId": "mg1"},
                ]
            )
        if path == "/CBS/37230ned/RegioSCodes":
            return odata(REGIONS, 3) if q.get("$top") != "0" else odata([], 3)
        if path == "/CBS/37230ned/PeriodenCodes":
            if q.get("$top") == "0":
                return odata([], 2)
            return odata(PERIODS[:1] if q.get("$orderby") else PERIODS, 2)
        if path == "/CBS/37230ned/RegioSGroups":
            return odata(
                [
                    {"Id": "g1", "Title": "Gemeenten", "ParentId": None},
                    {"Id": "g2", "Title": "Provincies", "ParentId": None},
                ]
            )
        if path == "/CBS/37230ned/Observations":
            self.obs_params = q
            if "ValueAttribute" in q.get("$filter", ""):  # the latest-period probe
                return odata([{"Perioden": "2026MM08"}])
            return odata(OBS, 2)
        return httpx.Response(400, json={"error": {"message": f"unexpected {path}"}})


@pytest.fixture
def fake():
    cbs.CATALOG.clear()
    cbs.META.clear()
    f = Fake()
    with respx.mock(assert_all_called=False) as mock:
        mock.route(url__startswith=BASE).mock(side_effect=f)
        yield f
    cbs.CATALOG.clear()
    cbs.META.clear()


async def test_search_ranks_title_hits_and_hides_discontinued(fake):
    out = await cbs.cbs_search("bevolking")
    lines = out.splitlines()
    assert lines[0] == "id|title|period|status|modified"
    assert lines[1].startswith(
        "37230ned|Bevolkingsontwikkeling; regio per maand|1995 tot en met 2026|Regulier|2026-11-13"
    )
    assert "70072NED" not in out
    assert "70072NED" in await cbs.cbs_search("bevolking", include_discontinued=True)


async def test_search_translates_english_and_reports_no_match(fake):
    assert "37230ned" in await cbs.cbs_search("population")  # → bevolking, inwoners
    assert "83625NED" in await cbs.cbs_search("unemployment")
    assert (await cbs.cbs_search("zzzz")).startswith("No tables match 'zzzz'")
    assert (await cbs.cbs_search("the of")).startswith("Error: Give topic keywords")


async def test_describe_lists_dimensions_measures_and_latest_period(fake):
    out = await cbs.cbs_describe("37230NED")  # ids are case-insensitive
    assert out.startswith("37230ned: Bevolkingsontwikkeling; regio per maand")
    assert "period: 1995 tot en met 2026" in out
    assert "RegioS|Regio's|Geo|3" in out
    assert "Perioden|Perioden|Time|2 (latest 2026MM08 = 2026 augustus)" in out
    assert "M000098|Bevolking aan het begin van de periode|aantal" in out
    # a measure title that repeats across groups is prefixed with its group path
    assert "M1|Groei: Seizoengecorrigeerd|x 1000" in out
    assert "M2|Groei > Natuurlijk: Seizoengecorrigeerd|%" in out


async def test_codes_by_title_alias_and_time_status(fake):
    assert "GM0363|Amsterdam|Gemeenten" in await cbs.cbs_codes("37230ned", "RegioS", "amsterdam")
    assert "GM0518|'s-Gravenhage (gemeente)" in await cbs.cbs_codes("37230ned", "RegioS", "Den Haag")
    out = await cbs.cbs_codes("37230ned", "Perioden")
    assert out.splitlines()[:2] == ["code|title|status", "2026MM08|2026 augustus|Voorlopig"]
    assert "M000099|Levend geborenen|aantal" in await cbs.cbs_codes("37230ned", "Measures", "geboren")
    assert (await cbs.cbs_codes("37230ned", "RegioS", "Atlantis")).startswith("No codes match")
    assert (await cbs.cbs_codes("37230ned", "Nope")).startswith("Error: Unknown dimension 'Nope'")


async def test_data_titles_fixed_columns_empty_cells_and_source(fake):
    out = await cbs.cbs_data("37230ned", ["M000098", "M000099"], {"RegioS": ["GM0363"]}, latest=True)
    lines = out.splitlines()
    assert lines[0] == "37230ned: Bevolkingsontwikkeling; regio per maand"
    assert (
        "fixed: Regio's=Amsterdam; Perioden=2026 augustus; measure=Bevolking aan het begin van de periode; unit=aantal"
        in out
    )
    assert "# omitted empty cells: {'Impossible': 1}" in out
    assert lines[-1] == (
        "source: https://opendata.cbs.nl/#/CBS/nl/dataset/37230ned/table · "
        "licence: CC BY 4.0, © Centraal Bureau voor de Statistiek (CBS)"
    )
    assert "933680" in out
    f = fake.obs_params["$filter"]
    assert "(RegioS eq 'GM0363')" in f and "Perioden eq '2026MM08'" in f and "Measure eq 'M000098'" in f
    assert fake.obs_params["$orderby"] == "Perioden desc"


async def test_data_rejects_unknown_measure_filter_and_overbroad_queries(fake):
    assert (await cbs.cbs_data("37230ned", ["M999"])).startswith("Error: Unknown measure 'M999'")
    assert (await cbs.cbs_data("37230ned", filters={"Nope": ["x"]})).startswith("Error: Unknown dimension")
    CATALOG[0]["ObservationCount"] = 5_000_000
    try:
        cbs.CATALOG.clear()
        out = await cbs.cbs_data("37230ned")
        assert out.startswith("Error: query too broad (~5,000,000 rows). Add filters on: RegioS, Perioden, measures")
    finally:
        CATALOG[0]["ObservationCount"] = 1000


async def test_unknown_table_and_vanished_table(fake):
    assert (await cbs.cbs_describe("00000xx")).startswith("Error: Unknown CBS table '00000xx'")
    ds = {"id": "99999NED"}
    with pytest.raises(cbs.UserError, match="no longer exists"):
        await cbs.ds_rows(ds, "Dimensions", {})


async def test_releases_join_catalogue_titles(fake):
    out = await cbs.cbs_releases(days=30)
    assert out.splitlines() == ["date|id|title", "2026-11-20 00:00|37230NED|Bevolkingsontwikkeling; regio per maand"]


async def test_odata_error_message_is_short():
    from europa_mcp.web import fetch_json

    msg = "The query specified in the URI is not valid. Could not find a property named 'Regio'."
    with respx.mock() as mock:
        mock.route(url__startswith=BASE).respond(400, json={"error": {"message": msg}})
        with pytest.raises(cbs.UserError, match=r"error 400: Could not find a property named 'Regio'\.$"):
            await fetch_json(BASE + "/x")


async def test_map_has_one_row_per_regular_table_with_titles_as_keywords(fake):
    rows = await mapping.build_cbs()
    assert [r["id"] for r in rows] == ["37230ned", "83625NED"]  # discontinued tables are left out
    first = rows[0]
    assert first["source"] == "CBS" and first["period"] == "1995 tot en met 2026" and first["updated"] == "2026-11-13"
    assert first["call"] == 'cbs_describe("37230ned")'
    assert first["source"] in server.SOURCES
    assert "Levend geborenen" in first["keywords"] and "Regio's" in first["keywords"]


async def test_find_data_finds_dutch_tables_from_english_and_dutch_questions(fake):
    smap = SourceMap(":memory:", synonyms=server.all_synonyms())
    smap.replace("CBS", await mapping.build_cbs())
    for q in ("population", "births per municipality", "bevolking"):
        top = smap.search(q)[0]
        assert top["id"] == "37230ned", q
    assert smap.search("unemployment")[0]["id"] == "83625NED"
