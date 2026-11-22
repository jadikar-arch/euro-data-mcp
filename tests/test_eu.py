"""Offline tests for the EU modules (Eurostat family, agri-food, European Parliament, data.europa.eu)."""

from __future__ import annotations

import json

import pytest
import respx
from fastmcp import Client

from europa_mcp import server, web
from europa_mcp.countries.eu import agrifood, dataeuropa, europarl, eurostat, mapping

ESTAT = eurostat.AGENCIES["eurostat"][0]

STRUCTURE_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<m:Structure xmlns:m="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message"
  xmlns:s="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure"
  xmlns:c="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common">
 <m:Structures>
  <s:Dataflows><s:Dataflow id="PRC_HPI_Q" agencyID="ESTAT">
   <c:Annotations>
    <c:Annotation><c:AnnotationTitle>1000</c:AnnotationTitle><c:AnnotationType>OBS_COUNT</c:AnnotationType></c:Annotation>
    <c:Annotation><c:AnnotationTitle>2005-Q1</c:AnnotationTitle><c:AnnotationType>OBS_PERIOD_OVERALL_OLDEST</c:AnnotationTitle></c:Annotation>
   </c:Annotations>
   <c:Name xml:lang="de">Hauspreisindex</c:Name><c:Name xml:lang="en">House price index</c:Name>
  </s:Dataflow></s:Dataflows>
  <s:Codelists>
   <s:Codelist id="GEO"><c:Name xml:lang="en">Geo</c:Name>
    <s:Code id="DE"><c:Name xml:lang="en">Germany</c:Name></s:Code>
    <s:Code id="NL"><c:Name xml:lang="en">Netherlands</c:Name></s:Code>
   </s:Codelist>
   <s:Codelist id="UNIT"><c:Name xml:lang="en">Unit</c:Name>
    <s:Code id="I15_Q"><c:Name xml:lang="en">Index, 2015=100</c:Name></s:Code>
   </s:Codelist>
  </s:Codelists>
  <s:Concepts><s:ConceptScheme id="CS">
   <s:Concept id="geo"><c:Name xml:lang="en">Geopolitical entity</c:Name></s:Concept>
   <s:Concept id="unit"><c:Name xml:lang="en">Unit of measure</c:Name></s:Concept>
  </s:ConceptScheme></s:Concepts>
  <s:DataStructures><s:DataStructure id="DSD"><s:DataStructureComponents><s:DimensionList>
   <s:Dimension id="geo" position="2"><s:ConceptIdentity><Ref id="geo"/></s:ConceptIdentity>
    <s:LocalRepresentation><s:Enumeration><Ref id="GEO"/></s:Enumeration></s:LocalRepresentation></s:Dimension>
   <s:Dimension id="unit" position="1"><s:ConceptIdentity><Ref id="unit"/></s:ConceptIdentity>
    <s:LocalRepresentation><s:Enumeration><Ref id="UNIT"/></s:Enumeration></s:LocalRepresentation></s:Dimension>
   <s:TimeDimension id="TIME_PERIOD" position="3"/>
  </s:DimensionList></s:DataStructureComponents></s:DataStructure></s:DataStructures>
 </m:Structures>
</m:Structure>""".replace(
    b"</c:AnnotationTitle><c:AnnotationType>OBS_PERIOD_OVERALL_OLDEST</c:AnnotationTitle>",
    b"</c:AnnotationTitle><c:AnnotationType>OBS_PERIOD_OVERALL_OLDEST</c:AnnotationType>",
)

JSONSTAT = {
    "label": "House price index",
    "updated": "2026-10-01T11:00:00+0200",
    "id": ["unit", "geo", "time"],
    "size": [1, 2, 2],
    "dimension": {
        "unit": {
            "label": "Unit of measure",
            "category": {"index": {"I15_Q": 0}, "label": {"I15_Q": "Index, 2015=100"}},
        },
        "geo": {
            "label": "Geopolitical entity",
            "category": {"index": {"DE": 0, "NL": 1}, "label": {"DE": "Germany", "NL": "Netherlands"}},
        },
        "time": {"label": "Time", "category": {"index": {"2026-Q1": 0, "2026-Q2": 1}}},
    },
    "value": {"0": 153.1, "1": 153.5, "2": 221.43, "3": 222.62},
    "status": {"3": "p"},
}

TOC = (
    '"title"\t"code"\t"type"\t"last update of data"\t"last table structure change"\t"data start"\t"data end"\t"values"\n'
    '"Database by themes"\t"data"\t"folder"\t" "\t" "\t" "\t" "\t\n'
    '"    House price index - quarterly data"\t"prc_hpi_q"\t"dataset"\t"01.10.2026"\t"01.10.2026"\t"2005-Q1"\t"2026-Q2"\t32753\n'
    '"    House price index - quarterly data"\t"prc_hpi_q"\t"dataset"\t"01.10.2026"\t"01.10.2026"\t"2005-Q1"\t"2026-Q2"\t32753\n'
    '"    Unemployment by sex and age"\t"une_rt_m"\t"dataset"\t"02.10.2026"\t"02.10.2026"\t"1983-01"\t"2026-08"\t1\n'
)


@pytest.fixture(autouse=True)
async def fresh():
    for memo in (
        eurostat.CATALOGS,
        eurostat.STRUCTURES,
        agrifood.SPEC,
        agrifood.RAW,
        europarl.SPEC,
        europarl.MEPS,
        europarl.SITTINGS,
        europarl.ORGS,
        dataeuropa.USE_CASES,
    ):
        memo.clear()
    yield
    await web.aclose()


async def call(tool: str, **args) -> str:
    async with Client(server.mcp) as c:
        result = await c.call_tool(tool, args, raise_on_error=False)
    return "".join(getattr(b, "text", "") for b in result.content)


# ---- Eurostat ---------------------------------------------------------------------


def test_parse_toc_dedupes_and_formats_dates():
    rows = eurostat.parse_toc(TOC)
    assert [r["id"] for r in rows] == ["prc_hpi_q", "une_rt_m"]
    assert rows[0] == {
        "id": "prc_hpi_q",
        "title": "House price index - quarterly data",
        "period": "2005-Q1–2026-Q2",
        "updated": "2026-10-01",
    }


def test_rank_prefers_all_words_and_exact_id():
    rows = eurostat.parse_toc(TOC)
    assert [r["id"] for r in eurostat.rank(rows, "house price")] == ["prc_hpi_q"]
    assert eurostat.rank(rows, "une_rt_m")[0]["id"] == "une_rt_m"


def test_parse_structure_orders_dims_and_reads_annotations():
    st = eurostat.parse_structure(STRUCTURE_XML, "eurostat")
    assert st.title == "House price index"
    assert [d.id for d in st.dims] == ["unit", "geo"]
    assert st.dim("GEO").codes == {"DE": "Germany", "NL": "Netherlands"}
    assert st.dim("Geopolitical entity").id == "geo"
    assert (st.obs_count, st.oldest, st.time_id) == (1000, "2005-Q1", "TIME_PERIOD")


def test_jsonstat_rows_decodes_sparse_values():
    cols, rows, ids = eurostat.jsonstat_rows(JSONSTAT)
    assert cols == ["Unit of measure", "Geopolitical entity", "Time"]
    assert rows[3] == ["Index, 2015=100", "Netherlands", "2026-Q2", "222.62", "p"]
    assert ids[-1] == "time"


@pytest.fixture
def fake_eurostat():
    with respx.mock(assert_all_called=False) as mock:
        mock.get(f"{ESTAT}/catalogue/toc/txt").respond(200, text=TOC)
        mock.get(url__regex=rf"{ESTAT}/sdmx/2.1/dataflow/ESTAT/PRC_HPI_Q/latest.*").respond(200, content=STRUCTURE_XML)
        mock.get(url__regex=rf"{ESTAT}/sdmx/2.1/dataflow/ESTAT/NOPE/latest.*").respond(404, text="no")
        data = mock.get(url__regex=rf"{ESTAT}/statistics/1.0/data/PRC_HPI_Q.*").respond(200, json=JSONSTAT)
        yield data


async def test_eurostat_search_and_describe(fake_eurostat):
    out = await call("eurostat_search", query="house price")
    assert out == "id|title|period|updated\nprc_hpi_q|House price index - quarterly data|2005-Q1–2026-Q2|2026-10-01"
    out = await call("eurostat_describe", dataset_id="prc_hpi_q")
    assert out.startswith("PRC_HPI_Q: House price index (eurostat)")
    assert "geo|Geopolitical entity|2|DE=Germany, NL=Netherlands" in out


async def test_eurostat_codes(fake_eurostat):
    assert await call("eurostat_codes", dataset_id="prc_hpi_q", dimension="geo", query="nether") == (
        "code|label\nNL|Netherlands"
    )


async def test_eurostat_data_table_newest_first(fake_eurostat):
    out = await call("eurostat_data", dataset_id="prc_hpi_q", filters={"geo": ["nl", "DE"]}, last_n=2)
    lines = out.splitlines()
    assert lines[1] == "fixed: Unit of measure=Index, 2015=100"
    assert lines[2] == "Geopolitical entity|Time|flag|value"
    assert lines[3:5] == ["Germany|2026-Q2||153.5", "Netherlands|2026-Q2|p|222.62"]
    assert lines[-1] == (
        "source: https://ec.europa.eu/eurostat/databrowser/view/prc_hpi_q/default/table?lang=en"
        " · licence: CC BY 4.0, © European Union (Eurostat)"
    )
    sent = fake_eurostat.calls.last.request.url.params
    assert sent.get_list("geo") == ["NL", "DE"] and sent["lastTimePeriod"] == "2"


async def test_eurostat_data_errors(fake_eurostat, monkeypatch):
    out = await call("eurostat_data", dataset_id="prc_hpi_q", filters={"geo": ["XX"]})
    assert out.startswith("Error: Unknown code 'XX' for geo. Examples: DE, NL")
    monkeypatch.setattr(eurostat, "MAX_CELLS", 10)
    out = await call("eurostat_data", dataset_id="prc_hpi_q")
    assert out.startswith("Error: query too broad") and "geo(2)" in out
    assert not fake_eurostat.called
    out = await call("eurostat_describe", dataset_id="nope")
    assert out == "Error: Unknown dataset 'nope' at eurostat. Use eurostat_search(query, agency)."
    assert (await call("eurostat_search", query="x", agency="dg foo")).startswith("Error: Unknown agency")


@pytest.mark.parametrize(
    ("args", "error"),
    [
        ({"since": "2024", "until": "2020"}, "since (2024) is after until (2020)."),
        ({"since": "2024-Q2", "until": "2024-Q1"}, "since (2024-Q2) is after until (2024-Q1)."),
        ({"last_n": 3, "since": "2015"}, "Use last_n or since/until, not both."),
        ({"since": "2025-13"}, "since='2025-13' is not a valid period. Use 2024, 2024-Q1, 2024-03, 2024-S1"),
        ({"limit": -5}, "limit must be at least 1 (got -5)."),
        ({"last_n": 0}, "last_n must be at least 1 (got 0)."),
    ],
)
async def test_eurostat_data_checks_time_and_limit_locally(fake_eurostat, monkeypatch, args, error):
    async def no_request(*_a, **_k):
        raise AssertionError("invalid input must not reach the API")

    monkeypatch.setattr(eurostat, "structure", no_request)
    out = await call("eurostat_data", dataset_id="prc_hpi_q", filters={"geo": ["DE"]}, **args)
    assert out.startswith(f"Error: {error}")
    assert not fake_eurostat.called


def test_eurostat_valid_periods_pass():
    eurostat.check_time(None, "2024-Q4", "2024", 10)  # until=2024 means the end of 2024
    eurostat.check_time(None, "2024-03", "2024-03", 10)
    eurostat.check_time(None, "2024-W05", "2024-03-15", 10)


async def test_eurostat_data_empty_says_what_the_dataset_covers(fake_eurostat):
    fake_eurostat.respond(200, json={**JSONSTAT, "value": {}, "status": {}})
    out = await call("eurostat_data", dataset_id="prc_hpi_q", filters={"geo": ["DE"]}, since="2030")
    assert out.splitlines()[-1] == "No values for these filters and period; the dataset covers 2005-Q1–."


async def test_eurostat_describe_shows_whole_labels_that_clipping_would_merge(monkeypatch):
    long = "Purchasing power standard (PPS, EU27 from 2020), per inhabitant"
    dim = eurostat.Dim("unit", "Unit", {"A": long, "B": long + " in percentage of the EU27 average"})
    st = eurostat.Structure("eurostat", "X", "X", [dim], None, None, "", "", "")

    async def fake_structure(*_a):
        return st

    monkeypatch.setattr(eurostat, "structure", fake_structure)
    out = await call("eurostat_describe", dataset_id="x")
    assert f"B={long} in percentage of the EU27 average" in out


# ---- agri-food --------------------------------------------------------------------

AGRI_SPEC = {
    "paths": {
        "/api/pigmeat/prices": {
            "get": {
                "parameters": [
                    {"name": "memberStateCodes", "in": "query"},
                    {"name": "beginDate", "in": "query", "description": "The optional date (dd/mm/yyyy) start"},
                ]
            }
        },
        "/api/oliveOil/production": {"get": {"parameters": [{"name": "granularity", "in": "query", "required": True}]}},
        "/api/cereal/products": {"get": {}},
    }
}


@pytest.fixture
def fake_agri():
    with respx.mock(assert_all_called=False) as mock:
        mock.get(f"{agrifood.BASE}/v3/api-docs").respond(200, json=AGRI_SPEC)
        prices = mock.get(f"{agrifood.BASE}/api/pigmeat/prices").respond(
            200,
            json=[
                {"memberStateCode": "NL", "price": "€108.79", "unit": "100 KG", "weekNumber": 40},
                {"memberStateCode": "DE", "price": "€155.34", "unit": "100 KG", "weekNumber": 40},
            ],
        )
        mock.get(f"{agrifood.BASE}/api/cereal/products").respond(404, json={"message": "No results found"})
        yield prices


async def test_agri_endpoints(fake_agri):
    out = await call("agri_endpoints", query="pig")
    assert "pigmeat/prices|memberStateCodes, beginDate[dd/mm/yyyy]" in out
    assert "olive" not in out
    out = await call("agri_endpoints")
    assert "oliveOil/production|granularity*" in out
    assert "code lookups (no params): cereal/products" in out


async def test_agri_data(fake_agri):
    out = await call("agri_data", endpoint="/api/pigmeat/prices", params={"memberstatecodes": ["NL", "DE"]})
    assert out.splitlines()[:-1] == [
        "fixed: currency=EUR; unit=100 KG; weekNumber=40",
        "memberStateCode|price|value",
        "NL|€108.79|108.79",
        "DE|€155.34|155.34",
    ]
    assert out.splitlines()[-1] == (
        f"source: {agrifood.BASE}/api/pigmeat/prices?memberStateCodes=NL%2CDE"
        " · licence: CC BY 4.0, © European Union (DG AGRI agri-food data portal)"
    )
    assert fake_agri.calls.last.request.url.params["memberStateCodes"] == "NL,DE"
    assert (await call("agri_data", endpoint="pigmeat/prices", params={"foo": 1})).startswith(
        "Error: Unknown param 'foo' for pigmeat/prices. Valid: memberStateCodes, beginDate"
    )
    assert await call("agri_data", endpoint="oliveOil/production") == (
        "Error: oliveOil/production requires: granularity"
    )
    assert (await call("agri_data", endpoint="cereal/products")).startswith("No data for cereal/products")
    assert "Did you mean: pigmeat/prices" in await call("agri_data", endpoint="pig/prices")


async def test_agri_data_checks_formats_before_calling(fake_agri):
    out = await call(
        "agri_data", endpoint="pigmeat/prices", params={"memberStateCodes": "NL", "beginDate": "2026-09-01"}
    )
    assert out == "Error: beginDate must be dd/mm/yyyy (got 2026-09-01); e.g. 01/09/2026."
    assert not fake_agri.called  # no request upstream, so no opaque 500 after retries


@pytest.mark.parametrize(
    ("text", "value"),
    [("€145.25", 145.25), ("€233,59", 233.59), ("€1.234,50", 1234.5), ("€1,234.50", 1234.5), ("12", 12.0)],
)
def test_agri_prices_get_a_numeric_value(text, value):
    assert agrifood.parse_price(text)[0] == value
    assert agrifood.with_values({"price": text, "unit": "T"})["value"] == value
    assert agrifood.with_values({"price": 3.5}) == {"price": 3.5}  # already numeric: unchanged


def test_agri_olive_oil_date_typo_still_means_day_month_year():
    assert agrifood._hint("The optional date (dd/yy/yyyy) interval start") == "dd/mm/yyyy"


# ---- European Parliament ----------------------------------------------------------

EP = europarl.BASE
EP_SPEC = {
    "components": {
        "parameters": {
            "limit": {"name": "limit", "in": "query"},
            "text": {"name": "text", "in": "query"},
            "year": {"name": "year", "in": "query"},
        }
    },
    "paths": {
        "/meps/{mep-id}": {"get": {"parameters": []}},
        "/meps/show-current": {"get": {"parameters": [{"$ref": "#/components/parameters/limit"}]}},
        "/adopted-texts": {
            "get": {"parameters": [{"$ref": "#/components/parameters/text"}, {"$ref": "#/components/parameters/limit"}]}
        },
    },
}
DECISIONS = {
    "data": [
        {
            "id": "eli/dl/event/D2",
            "activity_order": "2.0",
            "activity_label": {"en": "§ 41", "nl": "§ 41"},
            "decision_method": "def/ep-decision-methods/VOTE_ELECTRONIC_ROLLCALL",
            "decision_outcome": "def/ep-statuses/ADOPTED",
            "inverse_consists_of": ["eli/dl/event/ITM-1"],
            "number_of_votes_favor": 517,
            "number_of_votes_against": 102,
            "number_of_votes_abstention": 43,
            "had_voter_against": ["person/42"],
        },
        {
            "id": "eli/dl/event/D1",
            "activity_order": "1.0",
            "activity_label": {"en": "After § 5"},
            "decision_method": "def/ep-decision-methods/VOTE_HAND",
            "decision_outcome": "def/ep-statuses/REJECTED",
            "inverse_consists_of": ["eli/dl/event/ITM-2"],
        },
    ]
}
VOTE_ITEMS = {
    "data": [
        {"id": "eli/dl/event/ITM-1", "activity_label": {"en": "Report on Ukraine"}},
        {"id": "eli/dl/event/ITM-2", "activity_label": {"en": "Water resilience"}},
    ]
}


@pytest.fixture
def fake_ep():
    with respx.mock(assert_all_called=False) as mock:
        mock.get(f"{EP}/").respond(200, json=EP_SPEC)
        mock.get(f"{EP}/meps/show-current").respond(
            200,
            json={
                "data": [
                    {
                        "identifier": "1",
                        "label": "Lara WOLTERS",
                        "api:country-of-representation": "NL",
                        "api:political-group": "S&D",
                    },
                    {
                        "identifier": "2",
                        "label": "Bart GROOTHUIS",
                        "api:country-of-representation": "NL",
                        "api:political-group": "Renew",
                    },
                    {
                        "identifier": "3",
                        "label": "Hans MEIER",
                        "api:country-of-representation": "DE",
                        "api:political-group": "EPP",
                    },
                ]
            },
        )
        mock.get(f"{EP}/meetings/MTG-PL-2026-07-08/decisions").respond(200, json=DECISIONS)
        mock.get(f"{EP}/meetings/MTG-PL-2026-07-08/vote-results").respond(200, json=VOTE_ITEMS)
        mock.get(f"{EP}/meetings/MTG-PL-2026-08-01/decisions").respond(204)
        mock.get(f"{EP}/meetings/MTG-PL-2026-08-01/vote-results").respond(204)
        mock.get(f"{EP}/corporate-bodies").respond(200, json={"data": [{"id": "org/7005", "label": "DROI"}]})
        texts = mock.get(f"{EP}/adopted-texts").respond(
            200,
            json={
                "meta": {"total": 30},
                "data": [
                    {
                        "id": "eli/dl/doc/TA-10-2024-0066",
                        "type": "Work",
                        "document_date": "2024-12-18",
                        "is_about": ["http://eurovoc.europa.eu/1"],
                        "is_realized_by": [
                            {"id": "eli/dl/doc/TA-10-2024-0066/nl", "title": {"nl": "Huisvesting"}},
                            {
                                "id": "eli/dl/doc/TA-10-2024-0066/en",
                                "title": {"en": "Housing crisis"},
                                "is_embodied_by": [{"is_exemplified_by": "distribution/doc/TA_en.pdf"}],
                            },
                        ],
                        "work_type": "def/ep-document-types/TEXT_ADOPTED",
                    }
                ],
            },
        )
        mock.get(f"{EP}/meps/197500").respond(
            200,
            json={
                "data": [
                    {
                        "id": "person/197500",
                        "label": "Mounir SATOURI",
                        "hasMembership": [
                            {
                                "memberDuring": {"startDate": "2024-07-23"},
                                "organization": "org/7005",
                                "role": "def/ep-roles/CHAIR",
                                "membershipClassification": "def/ep-entities/COMMITTEE",
                            },
                            {
                                "memberDuring": {"startDate": "2019-07-02", "endDate": "2024-07-15"},
                                "organization": "org/1",
                            },
                        ],
                    }
                ]
            },
        )
        yield texts


async def test_ep_meps_filters(fake_ep):
    out = await call("ep_meps", country="nl", group="renew")
    assert out.splitlines()[:2] == ["id|name|country|group", "2|Bart GROOTHUIS|NL|Renew"]
    assert out.splitlines()[2].startswith(f"source: {europarl.BASE}/meps/show-current · licence:")
    assert "Lara WOLTERS" in await call("ep_meps", name="wolters")


async def test_ep_votes(fake_ep):
    out = await call("ep_votes", date="2026-07-08")
    assert out.splitlines()[:-1] == [
        "topic|item|outcome|method|for|against|abstain|vote_id",
        "Water resilience|After § 5|REJECTED|HAND||||",
        "Report on Ukraine|§ 41|ADOPTED|ELECTRONIC_ROLLCALL|517|102|43|",
    ]
    assert out.splitlines()[-1].startswith(f"source: {europarl.BASE}/meetings/MTG-PL-2026-07-08/decisions")
    out = await call("ep_votes", date="2026-07-08", mep_id="42")
    assert out.splitlines()[1:-1] == ["Report on Ukraine|§ 41|ADOPTED|ELECTRONIC_ROLLCALL|517|102|43||against"]
    assert (await call("ep_votes", date="2026-08-01")).startswith("No plenary votes on 2026-08-01")
    assert (await call("ep_votes", date="8 July")).startswith("Error: date must be YYYY-MM-DD")


async def test_ep_query_compacts_documents(fake_ep):
    out = await call("ep_query", endpoint="adopted-texts", params={"text": "housing"}, limit=1)
    assert "title: Housing crisis" in out
    assert "files: https://data.europarl.europa.eu/distribution/doc/TA_en.pdf" in out
    assert "work_type: document-types/TEXT_ADOPTED" in out
    assert "eurovoc" not in out and "Huisvesting" not in out
    assert out.splitlines()[-2] == "# 1 of 30; use offset=1 or narrow params"
    assert out.splitlines()[-1].startswith(f"source: {europarl.BASE}/adopted-texts · licence:")
    sent = fake_ep.calls.last.request.url.params
    assert sent["search-language"] == "en" and sent["format"] == "application/ld+json"


async def test_ep_query_memberships_and_validation(fake_ep):
    out = await call("ep_query", endpoint="meps/197500")
    assert "current memberships: CHAIR COMMITTEE DROI (since 2024-07-23)" in out
    assert "past memberships: 1" in out
    assert (await call("ep_query", endpoint="adopted-texts", params={"foo": 1})).startswith(
        "Error: Unknown param 'foo' for adopted-texts"
    )
    assert (await call("ep_query", endpoint="nope")).startswith("Error: Unknown endpoint 'nope'. Roots:")


def test_vote_labels_keep_the_amendment_number():
    label = "A10-0272/2026 – Nils Ušakovs, Michalis Hadjipantela – Before § 1 – Am 12"
    assert europarl.vote_label(label) == "A10-0272/2026 – Before § 1 – Am 12"
    long = "A10-0272/2026 – Names – " + "x" * 80 + " – Am 34"
    assert europarl.vote_label(long).endswith("– Am 34") and len(europarl.vote_label(long)) == 70


def test_votes_follow_voting_order_not_per_item_order():
    item = lambda parent, order, ts="": {  # noqa: E731
        "inverse_consists_of": [parent],
        "activity_order": order,
        "activity_start_date": ts,
        "id": f"{parent}-{order}",
    }
    decisions = [item("B", "1.0", "2026-10-21T13:40"), item("A", "2.0"), item("A", "1.0", "2026-10-21T13:20")]
    assert [d["id"] for d in europarl.voting_order(decisions)] == ["A-1.0", "A-2.0", "B-1.0"]


async def test_ep_votes_tells_same_label_budget_lines_apart():
    same = {
        "activity_label": {"en": "03 02 02"},
        "decision_method": "def/ep-decision-methods/VOTE_HAND",
        "inverse_consists_of": ["eli/dl/event/ITM-2"],
    }
    decisions = [
        {**same, "id": "x1", "activity_order": "3.0", "decisionAboutId": "437", "notation_votingId": "199085"},
        {**same, "id": "x2", "activity_order": "4.0", "decisionAboutId": "222", "notation_votingId": "199086"},
    ]
    with respx.mock(assert_all_called=False) as mock:
        mock.get(f"{EP}/meetings/MTG-PL-2026-10-21/decisions").respond(200, json={"data": decisions})
        mock.get(f"{EP}/meetings/MTG-PL-2026-10-21/vote-results").respond(200, json=VOTE_ITEMS)
        rows = (await call("ep_votes", date="2026-10-21")).splitlines()[1:-1]
    assert [r.split("|")[1] for r in rows] == ["03 02 02 – Am 437", "03 02 02 – Am 222"]
    assert [r.split("|")[-1] for r in rows] == ["199085", "199086"]


async def test_ep_query_meetings_are_one_line_each():
    meeting = {
        "activity_id": "MTG-PL-2026-01-19",
        "activity_date": "2026-01-19",
        "activity_label": {"en": "Monday, 19 January 2026"},
        "consists_of": [f"item{i}" for i in range(24)],
        "had_participant_person": [f"person/{i}" for i in range(700)],  # the bulk of the 1 KB+ records
    }
    with respx.mock(assert_all_called=False) as mock:
        mock.get(f"{EP}/").respond(200, json={"paths": {"/meetings": {"get": {"parameters": []}}}})
        mock.get(f"{EP}/meetings").respond(200, json={"data": [meeting] * 50})
        out = await call("ep_query", endpoint="meetings", limit=50)
    lines = out.splitlines()
    assert lines[:2] == ["date|id|label|agenda_items", "2026-01-19|MTG-PL-2026-01-19|Monday, 19 January 2026|24"]
    assert len(out) < 15_000


async def test_ep_query_output_has_a_size_budget(fake_ep, monkeypatch):
    monkeypatch.setattr(europarl, "MAX_CHARS", 50)
    fake_ep.respond(200, json={"meta": {"total": 30}, "data": [{"id": f"doc{i}", "label": "x" * 40} for i in range(5)]})
    out = await call("ep_query", endpoint="adopted-texts", limit=5)
    assert out.count("- id: doc") == 1
    assert out.splitlines()[-2] == "# 1 of 30; use offset=1 or narrow params"


def test_match_path_prefers_literal_segments():
    templates = {"meps/{mep-id}": {"a"}, "meps/show-current": {"b"}}
    assert europarl.match_path("meps/show-current", templates) == ("meps/show-current", {"b"})
    assert europarl.match_path("/meps/123", templates) == ("meps/123", {"a"})


# ---- data.europa.eu ---------------------------------------------------------------


@pytest.fixture
def fake_portal():
    with respx.mock(assert_all_called=False) as mock:
        mock.get(f"{dataeuropa.SEARCH}/search", params={"filter": "catalogue"}).respond(
            200,
            json={
                "result": {
                    "results": [
                        {
                            "id": "govdata",
                            "title": {"en": "GovData"},
                            "count": 169190,
                            "description": {
                                "de": "Das Datenportal für Deutschland",
                                "en": "The data portal for Germany",
                            },
                            "language": [{"id": "de"}],
                            "country": {"label": "Germany"},
                            "source_type": "dcat-ap",
                            "publisher": {"name": "GKSt GovData"},
                            "homepage": "https://www.govdata.de",
                            "modified": "2026-10-01T08:00:00Z",
                        },
                        {"id": "empty", "title": {"en": "Empty"}, "count": 0},
                    ]
                }
            },
        )
        mock.get(f"{dataeuropa.SEARCH}/search", params={"limit": "0"}).respond(
            200,
            json={
                "result": {
                    "count": 5291,
                    "results": [],
                    "facets": [
                        {
                            "id": "catalog",
                            "items": [
                                {"id": "dataportaal", "title": "Dataportaal", "count": 3356},
                                {"id": "ngr-nl", "title": "Georegister", "count": 1874},
                                {"id": "none", "title": "Nothing", "count": 0},
                            ],
                        },
                        {"id": "categories", "items": [{"id": "ENVI", "title": {"en": "Environment"}, "count": 943}]},
                    ],
                }
            },
        )
        search = mock.get(f"{dataeuropa.SEARCH}/search").respond(
            200,
            json={
                "result": {
                    "count": 1806,
                    "results": [
                        {
                            "id": "4420-food-prices",
                            "title": {"nl": "Voedselprijzen", "en": "Food prices"},
                            "description": {"en": "<p>Average consumer prices | per product.</p>"},
                            "country": {"id": "nl"},
                            "catalog": {"id": "dataportaal"},
                            "distributions": [
                                {"format": {"id": "JSON"}},
                                {"format": {"id": "JSON"}},
                                {"format": {"id": "CSV"}},
                            ],
                            "catalog_record": {"modified": "2026-08-12T00:06:15Z"},
                        }
                    ],
                }
            },
        )
        mock.get(f"{dataeuropa.SEARCH}/datasets/4420-food-prices").respond(
            200,
            json={
                "result": {
                    "id": "4420-food-prices",
                    "title": {"en": "Food prices"},
                    "description": {"en": "Average prices."},
                    "country": {"label": "Netherlands"},
                    "quality_meas": {"scoring": 185},
                    "distributions": [
                        {
                            "format": {"id": "CSV"},
                            "title": {"en": "Data"},
                            "download_url": ["https://x/data.csv"],
                            "license": {"label": "CC BY 4.0"},
                        },
                        {"format": {"id": "PDF"}, "access_url": ["https://x/report.pdf"]},
                        {"format": {"id": "CSV"}, "download_url": ["https://intranet.example/x.csv"]},
                        {"format": {"id": "CSV"}, "download_url": ["https://x/moved.csv"]},
                    ],
                }
            },
        )
        mock.get("https://x/data.csv").respond(
            200, text="product;price\nbread;2.10\nmilk;1.05\n", headers={"content-type": "text/csv"}
        )
        mock.get("https://x/moved.csv").respond(302, headers={"location": "http://rebind.example/secret.csv"})
        mock.get(f"{dataeuropa.SEARCH}/datasets/nope").respond(404, json={"message": "not found"})
        sparql = mock.get(f"{dataeuropa.PORTAL}/sparql").respond(
            200,
            json={
                "head": {"vars": ["d", "n"]},
                "results": {
                    "bindings": [
                        {"d": {"value": "http://data.europa.eu/88u/dataset/a"}, "n": {"value": "1"}},
                        {"d": {"value": "http://data.europa.eu/88u/dataset/b"}},
                    ]
                },
            },
        )
        mock.get(f"{dataeuropa.MQA}/countries/NLD").respond(
            200,
            json={
                "result": {
                    "results": [
                        {
                            "score": {"value": 3.958, "max": 7.5, "date": "2026-10-04"},
                            "counts": {"value": {"datasets": 4321}},
                            "coverage": {
                                "value": {
                                    "dataset": [
                                        {"metric": "titleAvailability", "importance": "Mandatory", "coverage": 99.95},
                                        {"metric": "relationAvailability", "importance": "Optional", "coverage": None},
                                    ]
                                }
                            },
                        }
                    ]
                }
            },
        )
        mock.get(f"{dataeuropa.PORTAL}/en/export-use-cases").respond(
            200,
            text=(
                'Country,Title,Description,"Date of Publication",Region,Sector,Nature,PDF\n'
                "Netherlands,Old app,Maps,31/05/2016,,Transport,,\n"
                "Netherlands,New app,Flood maps,17/02/2021,,Environment,,\n"
                "Spain,Papelea,Legal help,01/01/2022,,Government,,\n"
            ),
        )
        yield search, sparql


async def test_dataeu_search(fake_portal):
    search, _ = fake_portal
    out = await call("dataeu_search", query="food prices", country="NL", format="csv", limit=1)
    assert out.splitlines() == [
        "id|title|country|catalogue|formats|modified|about",
        "4420-food-prices|Food prices|nl|dataportaal|JSON,CSV|2026-08-12|Average consumer prices / per product.",
        "# 1 of 1,806; page=1 for more or add filters",
    ]
    assert json.loads(search.calls.last.request.url.params["facets"]) == {"country": ["nl"], "format": ["CSV"]}
    await call("dataeu_search", query="x", category="food")
    assert json.loads(search.calls.last.request.url.params["facets"]) == {"categories": ["AGRI"]}
    await call("dataeu_search", query="x", category="health", hvd=True, min_quality="Good")
    assert json.loads(search.calls.last.request.url.params["facets"]) == {
        "categories": ["HEAL"],
        "is_hvd": ["true"],
        "scoring": ["excellentScoring", "goodScoring"],
    }
    assert (await call("dataeu_search", query="x", category="space")).startswith("Error: Unknown category 'space'")
    assert (await call("dataeu_search", query="x", min_quality="top")).startswith("Error: min_quality must be")


async def test_dataeu_facets(fake_portal):
    out = await call("dataeu_facets", query="air quality", country="nl", by="catalogue,category", top=1)
    assert out.splitlines() == [
        "5,291 datasets match 'air quality' with {'country': ['nl']}",
        "catalogue|datasets|name",
        "dataportaal|3,356|Dataportaal",
        "# 1 of 2 catalogue values",
        "category|datasets|name",
        "ENVI|943|Environment",
    ]
    assert (await call("dataeu_facets", by="size")).startswith("Error: Unknown by 'size'")


async def test_dataeu_catalogue_map(fake_portal):
    assert await mapping.build_dataeu() == [
        {
            "source": "data.europa.eu",
            "id": "govdata",
            "title": "GovData: 169,190 datasets",
            "path": "data.europa.eu > Germany",
            "keywords": "The data portal for Germany Das Datenportal für Deutschland GKSt GovData govdata.de dcat-ap Germany",
            "period": "",
            "updated": "2026-10-01",
            "call": 'dataeu_search("...", catalogue="govdata")',
        }
    ]


async def test_dataeu_dataset(fake_portal):
    out = await call("dataeu_dataset", dataset_id="4420-food-prices")
    assert "country: Netherlands" in out and "quality score: 185" in out
    assert "1|CSV|Data|CC BY 4.0|https://x/data.csv" in out
    assert "dataeu_preview(id, file=n)" in out
    assert await call("dataeu_dataset", dataset_id="nope") == "Error: Unknown dataset 'nope'. Use dataeu_search."


async def test_dataeu_sparql(fake_portal):
    _, sparql = fake_portal
    out = await call("dataeu_sparql", query="SELECT ?d ?n WHERE { ?d ?p ?n }", limit=1)
    assert out.splitlines() == ["d|n", "dataset/a|1", "# truncated at 1 rows; add LIMIT/OFFSET or filters"]
    assert sparql.calls.last.request.url.params["query"].endswith("LIMIT 2")
    assert (await call("dataeu_sparql", query="DELETE WHERE { ?s ?p ?o }")).startswith("Error: Only read-only")
    assert (await call("dataeu_sparql", query='SELECT ?s WHERE { ?s ?p "drop" }')).startswith("d|n")


async def test_dataeu_quality_and_use_cases(fake_portal):
    out = await call("dataeu_quality", scope="country", id="nld")
    assert out.splitlines()[0] == "country nld: score 3.96/7.5 (2026-10-04)"
    assert out.splitlines()[3:] == [
        "relationAvailability|dataset|Optional|0",
        "titleAvailability|dataset|Mandatory|100.0",
    ]
    assert (await call("dataeu_quality", scope="country", id="NL")).startswith("Error: country id must be")
    out = await call("dataeu_use_cases", country="netherlands")
    assert out.splitlines()[1].startswith("New app|Netherlands|Environment|2021-02-17")
    assert "Papelea" not in out


async def test_dataeu_search_sort_and_language(fake_portal):
    search, _ = fake_portal
    out = await call("dataeu_search", query="food prices", sort="newest", language="nl", limit=1)
    sent = search.calls.last.request.url.params
    assert sent["sort"] == "relevance desc"  # newest = relevant hits re-sorted by date locally
    assert sent["limit"] == "100"
    assert sent["includes"].endswith(",description.en,description.nl")
    assert "4420-food-prices|Voedselprijzen|" in out  # title in the requested language
    assert (await call("dataeu_search", query="x", sort="oldest")).startswith("Error: sort must be one of")


async def test_dataeu_search_newest_keeps_relevance(fake_portal):
    search, _ = fake_portal
    hit = lambda i, day: {"id": i, "title": {"en": i}, "catalog_record": {"modified": f"2026-{day}T00:00:00Z"}}  # noqa: E731
    search.respond(
        200,
        json={"result": {"count": 1862, "results": [hit("charging-a", "01-05"), hit("charging-b", "10-30")]}},
    )
    out = await call("dataeu_search", query="electric vehicle charging stations", sort="newest", limit=5)
    ids = [line.split("|")[0] for line in out.splitlines()[1:3]]
    assert ids == ["charging-b", "charging-a"]  # the relevant hits, newest first
    assert out.splitlines()[-1] == "# newest first among the 2 most relevant of 1,862 matches"


async def test_dataeu_sparql_syntax_error_is_short(fake_portal):
    _, sparql = fake_portal
    sparql.respond(
        400,
        text="Virtuoso 37000 Error SP030: SPARQL compiler, line 0: Parentheses are not balanced at '}'\n\n"
        "SPARQL query:\ndefine sql:big-data-const 0\nSELECT ?s WHERE { FILTER( }\nLIMIT 101",
    )
    out = await call("dataeu_sparql", query="SELECT ?s WHERE { FILTER( }")
    assert out == "Error: SPARQL syntax error: Parentheses are not balanced at '}'"


def test_dataeu_descriptions_lose_html():
    assert dataeuropa.plain("<p><strong>Air &amp; water</strong> quality</p>", 100) == "Air & water quality"


async def test_dataeu_use_cases_say_how_old_they_are(fake_portal):
    out = await call("dataeu_use_cases", country="netherlands")
    assert out.splitlines()[-1].startswith("# published 2016–2021")


async def test_dataeu_preview(fake_portal):
    out = await call("dataeu_preview", dataset_id="4420-food-prices", file=1)
    assert out.splitlines() == [
        "4420-food-prices file 1: CSV, 2 columns",
        "product|price",
        "bread|2.10",
        "milk|1.05",
        "# showing 2 of 2 rows",
        "source: https://x/data.csv · licence: CC BY 4.0",
    ]
    assert (await call("dataeu_preview", dataset_id="4420-food-prices", file=2)).startswith(
        "Error: 4420-food-prices file 2 is PDF; only CSV/JSON"
    )
    assert (await call("dataeu_preview", dataset_id="4420-food-prices", file=9)).startswith("Error: file must be 1..4")
    assert await call("dataeu_preview", dataset_id="nope") == "Error: Unknown dataset 'nope'. Use dataeu_search."


async def test_dataeu_preview_refuses_private_hosts_and_redirects(fake_portal):
    # A hostname that resolves to a private address, and a public URL redirecting to one.
    for n in (3, 4):
        out = await call("dataeu_preview", dataset_id="4420-food-prices", file=n)
        assert out.startswith("Error: Can't preview"), out


def test_dataeu_newest_pool_drops_loose_matches():
    rows = [
        {"id": "a", "title": {"en": "Charging stations for electric vehicles"}},
        {"id": "b", "title": {"en": "Meteorological Data of Station RODOS"}},
        {"id": "c", "title": {"en": "Electric vehicle charging points"}, "description": {"en": "Station list"}},
    ]
    kept = dataeuropa.best_matches(rows, "electric vehicle charging stations")
    assert [r["id"] for r in kept] == ["a", "c"]


async def test_agrifood_uses_the_saved_openapi_copy_while_the_service_is_down():
    from europa_mcp.common import cache_dir

    with respx.mock(assert_all_called=False) as mock:
        mock.get(f"{agrifood.BASE}/v3/api-docs").respond(200, json=AGRI_SPEC)
        assert "pigmeat/prices" in await agrifood.endpoints()
    assert (cache_dir() / agrifood.SPEC_FILE).is_file()  # saved after the download

    agrifood.SPEC.clear()
    agrifood.RAW.clear()
    with respx.mock(assert_all_called=False) as mock:
        down = mock.get(f"{agrifood.BASE}/v3/api-docs").respond(500, json={"message": "An internal error occurred"})
        assert "pigmeat/prices" in await agrifood.endpoints()  # served from the saved copy
        # the missing-parameter check does not need the live service either
        assert (await call("agri_data", endpoint="oliveOil/production")).startswith(
            "Error: oliveOil/production requires:"
        )
        agrifood.RAW.clear()
        agrifood.SPEC.clear()
        calls = down.call_count
        await agrifood.endpoints()
        assert down.call_count > calls  # the live service is tried again on the next call, not after a day


async def test_agrifood_outage_without_a_saved_copy_reaches_the_user():
    with respx.mock(assert_all_called=False) as mock:
        mock.get(f"{agrifood.BASE}/v3/api-docs").respond(500, json={"message": "An internal error occurred"})
        assert (await call("agri_data", endpoint="pigmeat/prices")).startswith("Error: api.tech.ec.europa.eu error 500")
