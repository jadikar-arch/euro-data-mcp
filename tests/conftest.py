"""A tiny fake of the CBS OData API, routed through respx."""

from __future__ import annotations

import re

import httpx
import pytest
import respx

from europa_mcp import server
from europa_mcp.countries.nl import cbs, client
from europa_mcp.countries.nl.index import Index

BASE = client.BASE_URL

CATALOG = [
    {
        "Identifier": "37230ned", "Catalog": "CBS", "Version": "v1", "Status": "Regulier",
        "Title": "Bevolkingsontwikkeling; regio per maand", "Modified": "2026-09-30T00:00:00+02:00",
        "ObservationCount": 24,
        "Description": "Veranderingen in de bevolkingsomvang per regio.\n\n"
        "Gegevens beschikbaar vanaf: januari 2002\n\nStatus van de cijfers: ...",
    },
    {
        "Identifier": "83625NED", "Catalog": "CBS", "Version": "v1", "Status": "Regulier",
        "Title": "Bestaande koopwoningen; gemiddelde verkoopprijzen, regio",
        "Modified": "2026-02-17T00:00:00+01:00", "ObservationCount": 23095,
        "Description": "Gemiddelde verkoopprijs.\nGegevens beschikbaar vanaf: 1995\n",
    },
    {
        "Identifier": "00372", "Catalog": "CBS", "Version": "v1", "Status": "Gediscontinueerd",
        "Title": "Bevolking; oude tabel", "Modified": "2010-01-01T00:00:00+01:00",
        "ObservationCount": 10, "Description": "Oud.",
    },
]

DIMS = [
    {"Identifier": "RegioS", "Title": "Regio's", "Kind": "GeoDimension",
     "CodesUrl": f"{BASE}/CBS/37230ned/RegioSCodes", "GroupsUrl": f"{BASE}/CBS/37230ned/RegioSGroups"},
    {"Identifier": "Perioden", "Title": "Perioden", "Kind": "TimeDimension",
     "CodesUrl": f"{BASE}/CBS/37230ned/PeriodenCodes", "GroupsUrl": f"{BASE}/CBS/37230ned/PeriodenGroups"},
]
MEASURES = [
    {"Identifier": "M000098", "Title": "Bevolking aan het begin van de periode", "Unit": "aantal"},
    {"Identifier": "M000134", "Title": "Overledenen", "Unit": "aantal"},
]
REGIONS = [
    {"Identifier": "NL01", "Title": "Nederland", "DimensionGroupId": "NL"},
    {"Identifier": "GM0363", "Title": "Amsterdam", "DimensionGroupId": "GMPV27"},
    {"Identifier": "CR23", "Title": "Groot-Amsterdam (CR)", "DimensionGroupId": "CRPV27"},
    {"Identifier": "GM0599", "Title": "Rotterdam", "DimensionGroupId": "GMPV28"},
]
GROUPS = [
    {"Id": "NL", "Title": "Nederland", "ParentId": None},
    {"Id": "GMPV", "Title": "Gemeenten per provincie", "ParentId": None},
    {"Id": "GMPV27", "Title": "Noord-Holland (PV)", "ParentId": "GMPV"},
    {"Id": "GMPV28", "Title": "Zuid-Holland (PV)", "ParentId": "GMPV"},
    {"Id": "CRPV", "Title": "COROP gebieden per provincie", "ParentId": None},
    {"Id": "CRPV27", "Title": "Noord-Holland (PV)", "ParentId": "CRPV"},
]
PERIODS = [
    {"Identifier": p, "Title": t, "DimensionGroupId": None, "Status": "Definitief"}
    for p, t in [("2025JJ00", "2025"), ("2026MM07", "2026 juli"), ("2026MM08", "2026 augustus")]
]
OBS = [
    {"Measure": "M000098", "Value": 944322.0, "StringValue": None, "ValueAttribute": "None",
     "RegioS": "GM0363", "Perioden": "2026MM08"},
    {"Measure": "M000098", "Value": 945451.0, "StringValue": None, "ValueAttribute": "None",
     "RegioS": "GM0363", "Perioden": "2026MM07"},
    {"Measure": "M000098", "Value": 680000.0, "StringValue": None, "ValueAttribute": "None",
     "RegioS": "GM0599", "Perioden": "2026MM08"},
    {"Measure": "M000134", "Value": None, "StringValue": None, "ValueAttribute": "Impossible",
     "RegioS": "GM0363", "Perioden": "2026MM08"},
]

_EQ = re.compile(r"(\w+) eq '((?:[^']|'')*)'")


def odata_filter(rows: list[dict], expr: str | None) -> list[dict]:
    """Supports the subset we emit: and-ed groups of `F eq 'x' or F eq 'y'` and tolower()."""
    if not expr:
        return rows
    lower = re.match(r"tolower\((\w+)\) eq '(.*)'", expr)
    if lower:
        f, v = lower.groups()
        return [r for r in rows if str(r.get(f, "")).lower() == v]
    allowed: dict[str, set[str]] = {}
    for f, v in _EQ.findall(expr):
        allowed.setdefault(f, set()).add(v.replace("''", "'"))
    return [r for r in rows if all(str(r.get(f)) in vs for f, vs in allowed.items())]


def page(rows: list[dict], params: httpx.QueryParams) -> dict:
    rows = odata_filter(rows, params.get("$filter"))
    if ob := params.get("$orderby"):
        field, *desc = ob.split()
        rows = sorted(rows, key=lambda r: str(r.get(field)), reverse=bool(desc))
    total = len(rows)
    top = params.get("$top")
    rows = rows[: int(top)] if top is not None else rows
    if sel := params.get("$select"):
        keep = sel.split(",")
        rows = [{k: r.get(k) for k in keep} for r in rows]
    body: dict = {"@odata.context": "x", "value": rows}
    if params.get("$count") == "true":
        body["@odata.count"] = total
    return body


class FakeCBS:
    def __init__(self):
        self.catalog = [dict(r) for r in CATALOG]
        self.calls: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/odata/v1")
        self.calls.append(path)
        p = request.url.params
        tables = {
            "/Datasets": self.catalog,
            "/CBS/37230ned/Dimensions": DIMS,
            "/CBS/37230ned/MeasureCodes": MEASURES,
            "/CBS/37230ned/RegioSCodes": REGIONS,
            "/CBS/37230ned/RegioSGroups": GROUPS,
            "/CBS/37230ned/PeriodenCodes": PERIODS,
            "/CBS/37230ned/PeriodenGroups": [],
            "/CBS/37230ned/Observations": OBS,
            "/CBS/83625NED/Dimensions": [{"Identifier": "RegioS", "Title": "Regio's"}],
            "/CBS/83625NED/MeasureCodes": [{"Identifier": "M001534", "Title": "Gemiddelde verkoopprijs"}],
            "/ReleaseCalendar": [],
        }
        if path not in tables:
            return httpx.Response(404, json={"error": {"message": "not found"}})
        return httpx.Response(200, json=page(tables[path], p))


@pytest.fixture(autouse=True)
def no_background_tasks(monkeypatch):
    """The server lifespan starts the CBS index sync and the map refresh; tests drive them directly."""
    monkeypatch.setattr(cbs, "ensure_sync_task", lambda: None)
    monkeypatch.setattr(server, "ensure_map_task", lambda: None)


@pytest.fixture
def fake_cbs():
    fake = FakeCBS()
    with respx.mock(base_url=BASE, assert_all_called=False) as mock:
        mock.route().mock(side_effect=fake)
        yield fake


@pytest.fixture
async def index(tmp_path, fake_cbs, monkeypatch):
    """A synced index wired into the server; background sync disabled."""
    idx = Index(tmp_path / "index.db")
    await idx.sync()
    monkeypatch.setattr(cbs, "INDEX", idx)
    monkeypatch.setattr(cbs, "ensure_sync_task", lambda: None)
    cbs.CACHE._data.clear()
    yield idx
    await client.aclose()
