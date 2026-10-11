import pytest
from fastmcp import Client

from cbs_mcp import server


async def call(name: str, **args) -> str:
    async with Client(server.mcp) as c:
        result = await c.call_tool(name, args, raise_on_error=False)
    return "".join(getattr(b, "text", "") for b in result.content)


async def test_tools_listed_with_short_docs(index):
    async with Client(server.mcp) as c:
        tools = {t.name: t for t in await c.list_tools()}
    assert set(tools) == {
        "search_datasets", "describe_dataset", "list_codes", "get_observations", "upcoming_releases",
        "eurostat_search", "eurostat_describe", "eurostat_codes", "eurostat_data",
        "agri_endpoints", "agri_data", "ep_meps", "ep_votes", "ep_query",
        "dataeu_search", "dataeu_dataset", "dataeu_sparql", "dataeu_quality", "dataeu_use_cases",
    }
    for t in tools.values():
        assert len(t.description.strip().splitlines()) <= 3
        assert t.output_schema is None  # text only, no duplicated structured payload


async def test_search_datasets(index):
    out = await call("search_datasets", query="bevolking")
    assert out.splitlines()[0] == "id|title|period|status|modified"
    assert "37230ned|Bevolkingsontwikkeling; regio per maand|januari 2002|Regulier" in out
    assert "00372" not in out


async def test_describe_dataset(index):
    out = await call("describe_dataset", dataset_id="37230NED")
    assert out.startswith("37230ned: Bevolkingsontwikkeling")
    assert "RegioS|Regio's|Geo|4" in out
    assert "Perioden|Perioden|Time|3 (latest 2026MM08 = 2026 augustus)" in out
    assert "M000098|Bevolking aan het begin van de periode|aantal" in out


async def test_list_codes_finds_municipality_with_group(index):
    out = await call("list_codes", dataset_id="37230ned", dimension="regios", query="amsterdam")
    lines = out.splitlines()
    assert lines[0] == "code|title|group"
    assert lines[1] == "GM0363|Amsterdam|Gemeenten per provincie"  # exact title ranks first


async def test_list_codes_place_alias(index, monkeypatch):
    monkeypatch.setitem(server.PLACE_ALIASES, "mokum", "amsterdam")
    out = await call("list_codes", dataset_id="37230ned", dimension="RegioS", query="Mokum")
    assert "GM0363|Amsterdam" in out


async def test_list_codes_time_newest_first_and_measures(index):
    out = await call("list_codes", dataset_id="37230ned", dimension="Perioden", limit=1)
    assert out.splitlines()[1] == "2026MM08|2026 augustus"
    assert "# 1 of 3" in out
    out = await call("list_codes", dataset_id="37230ned", dimension="Measures", query="overl")
    assert "M000134|Overledenen|aantal" in out


async def test_get_observations_latest(index):
    out = await call(
        "get_observations", dataset_id="37230ned", measures=["m000098"],
        filters={"regios": ["GM0363"]}, latest=True,
    )
    assert "fixed: Regio's=Amsterdam; Perioden=2026 augustus;" in out
    assert out.splitlines()[-1] == "944322"


async def test_get_observations_table_and_empty_cells(index):
    out = await call("get_observations", dataset_id="37230ned", filters={"RegioS": ["GM0363"]})
    assert "fixed: Regio's=Amsterdam; measure=Bevolking aan het begin van de periode" in out
    assert "Perioden|value\n2026 augustus|944322\n2026 juli|945451" in out  # newest first
    assert "# omitted empty cells: {'Impossible': 1}" in out


async def test_get_observations_truncation(index):
    out = await call(
        "get_observations", dataset_id="37230ned", measures=["M000098"],
        filters={"RegioS": ["GM0363", "GM0599"]}, limit=2,
    )
    assert "# truncated: 2 of 3 rows" in out


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        ({}, "Error: query too broad"),
        ({"filters": {"Regio": ["x"]}}, "Error: Unknown dimension 'Regio'. Valid: RegioS, Perioden, Measures"),
        ({"measures": ["M9"], "filters": {"RegioS": ["GM0363"]}}, "Error: Unknown measure 'M9'"),
    ],
)
async def test_get_observations_errors(index, args, expected, monkeypatch):
    monkeypatch.setattr(server, "MAX_EST_ROWS", 10)  # fake table has 24 rows
    out = await call("get_observations", dataset_id="37230ned", **args)
    assert out.startswith(expected)
    assert "Traceback" not in out


async def test_unknown_dataset(index):
    out = await call("describe_dataset", dataset_id="nope")
    assert out == "Error: Unknown dataset 'nope'. Use search_datasets to find one."


async def test_upcoming_releases_empty(index):
    assert await call("upcoming_releases", days=3) == "No releases scheduled in the next 3 days."
