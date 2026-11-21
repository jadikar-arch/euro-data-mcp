"""Offline tests for the shared PxWeb connector and the four countries built on it (se, fi, ee, lv)."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
import respx
from fastmcp import FastMCP

from europa_mcp import pxweb
from europa_mcp.pxweb import PxSource

BASE = "https://px.example/api/v1/en/db"
SYNONYMS = {"population": ("befolkning",), "unemployment": ("arbetslöshet",)}


def page(table_id: str) -> str:
    return f"https://px.example/pxweb/{table_id}"


SRC = PxSource(
    prefix="tst",
    name="TST",
    agency="Statistics Testland",
    country="Testland",
    local="Testish",
    base=BASE,
    licence="CC0 1.0, Statistics Testland",
    page=page,
    synonyms=SYNONYMS,
    aliases={"gothenburg": "goteborg"},
    min_interval=0.0,
)

LST = PxSource(
    prefix="lst",
    name="LST",
    agency="Statistics Listland",
    country="Listland",
    local="Listish",
    base=BASE,
    licence="CC BY 4.0, Statistics Listland",
    page=page,
    min_interval=0.0,
    listing=True,
    archive=lambda tid: "/OLD/" in f"/{tid}",
)
LISTING = [
    {
        "id": f"T{i:02d}.px",
        "path": "/NEW/pop",
        "title": f"T{i:02d} -- Population by area {i}, 2000-2025",
        "published": "2026-02-03T00:00:00",
    }
    for i in range(25)
] + [
    {
        "id": "OLD1.px",
        "path": "/OLD/pop",
        "title": "OLD1 -- Population by area, 1990-2000",
        "published": "2020-01-01T00:00:00",
    }
]

ROOT = [
    {"id": "POP", "type": "l", "text": "Population"},
    {"id": "EMP", "type": "l", "text": "Labour market"},
    {"id": "BAD", "type": "l", "text": "Broken folder"},
]
POP = [
    {
        "id": "POP001.px",
        "type": "t",
        "text": "POP001: Population by region and sex, 1990-2025",
        "updated": "2026-01-02T08:00:00",
    },
    {
        "id": "HH01.px",
        "type": "t",
        "text": "HH01: Gas prices for household consumers",
        "updated": "2026-03-04T00:00:00",
    },
    {"id": "HP01.px", "type": "t", "text": "HP01: House price index 2010Q1 - 2026Q2", "updated": "2026-02-01T00:00:00"},
]
EMP = [
    {
        "id": "UN01",
        "type": "t",
        "text": "Unemployment rate by group 2000M01 - 2026M09",
        "updated": "2026-05-06T00:00:00",
    }
]

TABLES = {
    "POP/POP001.px": {
        "title": "Population by region and sex",
        "variables": [
            {
                "code": "Region",
                "text": "region",
                "values": ["00", "01", "02", "03"],
                "valueTexts": ["..Whole country", "..Capital", "..Capital city", "Pirkanmaa"],
                "elimination": True,
            },
            {
                "code": "Sex",
                "text": "sex",
                "values": ["1", "2"],
                "valueTexts": ["Males", "Females"],
                "elimination": True,
            },
            {
                "code": "ContentsCode",
                "text": "observations",
                "values": ["P1", "P2"],
                "valueTexts": ["Population", "Population change"],
            },
            {
                "code": "Year",
                "text": "year",
                "values": ["2023", "2024", "2025"],
                "valueTexts": ["2023", "2024", "2025"],
                "time": True,
            },
        ],
    },
    "EMP/UN01": {
        "title": "Unemployment rate by group",
        "variables": [
            {"code": "Group", "text": "group", "values": ["A", "B", "C"], "valueTexts": ["Total", "Men", "Women"]},
            {
                "code": "Month",
                "text": "month",
                "values": ["2026M08", "2026M09"],
                "valueTexts": ["2026M08", "2026M09"],
                "time": True,
            },
        ],
    },
}


class Fake:
    """A tiny PxWeb server: lists folders, serves table metadata, answers POST queries."""

    def __init__(self) -> None:
        self.gets: list[str] = []
        self.posts: list[dict] = []
        self.bad = 400  # status of the folder that cannot be listed
        self.rate_limited = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/api/v1/en/db").strip("/")
        if request.method == "GET":
            self.gets.append(path)
            if self.rate_limited:
                return httpx.Response(429, headers={"Retry-After": "0"}, text="Too Many Requests")
            if request.url.params.get("query") == "*":
                return httpx.Response(200, json=LISTING)
            if path == "":
                return httpx.Response(200, json=ROOT)
            if path == "POP":
                return httpx.Response(200, json=POP)
            if path == "EMP":
                return httpx.Response(200, json=EMP)
            if path == "BAD":
                return httpx.Response(self.bad, text="Bad Request")
            if path in TABLES:
                return httpx.Response(200, json=TABLES[path])
            return httpx.Response(404, json={"error": "not found"})
        body = json.loads(request.content)
        self.posts.append(body)
        return self.answer(path, body)

    def answer(self, path: str, body: dict) -> httpx.Response:
        meta = TABLES[path]
        sel = {q["code"]: q["selection"] for q in body["query"]}
        required = [v["code"] for v in meta["variables"] if not v.get("elimination") and v["code"] not in sel]
        if required:
            return httpx.Response(400, text="Bad Request")
        if path == "EMP/UN01":
            months = ["2026M08", "2026M09"]
            top = int(sel["Month"]["values"][0]) if sel["Month"]["filter"] == "top" else None
            months = months[-top:] if top else sel["Month"]["values"]
            groups = sel["Group"]["values"]
            rows = [{"key": [g, m], "values": ["5.4" if g == "A" else ".."]} for g in groups for m in months]
            cols = [
                {"code": "Group", "text": "group", "type": "d"},
                {"code": "Month", "text": "month", "type": "t"},
                {"code": "Unemployment rate by group", "text": "Unemployment rate by group", "type": "c"},
            ]
            return httpx.Response(200, json={"columns": cols, "comments": [], "data": rows})
        years = ["2023", "2024", "2025"]
        sel_y = sel["Year"]
        years = years[-int(sel_y["values"][0]) :] if sel_y["filter"] == "top" else sel_y["values"]
        regions = sel["Region"]["values"] if "Region" in sel else None
        cols = [{"code": "Year", "text": "year", "type": "t"}]
        if regions:
            cols.insert(0, {"code": "Region", "text": "region", "type": "d"})
        # servers name the measure columns after the table, not the contents code: the code maps by position
        cols += [{"code": "Population by region and sex", "text": "Population by region and sex", "type": "c"}] * len(
            sel["ContentsCode"]["values"]
        )
        rows = []
        for r in regions or [None]:
            for y in years:
                values = [str(1000 + int(y) - 2000 + (int(r) if r else 0)), "-" if y == "2023" else "7"]
                rows.append({"key": ([r] if r else []) + [y], "values": values[: len(sel["ContentsCode"]["values"])]})
        return httpx.Response(200, json={"columns": cols, "comments": [], "data": rows})


@pytest.fixture
def fake():
    pxweb.CATALOG.clear()
    pxweb.META.clear()
    pxweb._loading.clear()
    f = Fake()
    with respx.mock(assert_all_called=False) as mock:
        mock.route(url__startswith=BASE).mock(side_effect=f)
        yield f
    pxweb.CATALOG.clear()
    pxweb.META.clear()


@pytest.fixture
def tools(fake):
    mcp = FastMCP("t")
    pxweb.register(mcp, SRC)
    return mcp


async def call(mcp: FastMCP, name: str, **args) -> str:
    from fastmcp import Client

    async with Client(mcp) as c:
        r = await c.call_tool(name, args, raise_on_error=False)
    return "".join(getattr(b, "text", "") for b in r.content)


# ---- catalogue --------------------------------------------------------------------------


async def test_catalogue_walk_skips_a_refused_folder_keeps_the_rest_and_is_cached_on_disk(fake):
    rows = await pxweb.catalog(SRC)
    assert [r["id"] for r in rows] == ["EMP/UN01", "POP/HH01.px", "POP/HP01.px", "POP/POP001.px"]
    assert rows[3]["path"] == "Population" and rows[3]["updated"] == "2026-01-02"
    assert rows[0]["short"] == "UN01" and rows[3]["short"] == "POP001.px"
    walked = len(fake.gets)
    pxweb.CATALOG.clear()  # a restart: the saved catalogue is used, the folder tree is not walked again
    again = await pxweb.catalog(SRC)
    assert [r["id"] for r in again] == [r["id"] for r in rows] and len(fake.gets) == walked


@pytest.fixture
def instant(monkeypatch):
    """No real waiting: retries, throttles and the 429 pause finish at once."""
    real = asyncio.sleep

    async def quick(_delay, *a, **k):
        await real(0)

    monkeypatch.setattr(asyncio, "sleep", quick)
    monkeypatch.setattr(pxweb, "RATE_LIMIT_PAUSE", 0.0)


async def test_folders_that_failed_for_transient_reasons_are_retried_and_the_catalogue_is_not_saved(fake, instant):
    from europa_mcp.common import cache_dir

    fake.bad = 503
    rows = await pxweb.catalog(SRC)
    assert len(rows) == 4  # the other folders are still usable now
    assert pxweb.INCOMPLETE["tst"] == 1 and not (cache_dir() / "pxweb-tst.json").exists()
    assert fake.gets.count("BAD") >= 6  # three attempts, then one more try of the whole folder
    mcp = FastMCP("t")
    pxweb.register(mcp, SRC)
    assert "# 1 folders of the table list could not be read; the list may be incomplete" in await call(
        mcp, "tst_search", query="unemployment"
    )


async def test_a_folder_the_server_refuses_for_good_is_skipped_without_marking_the_list_incomplete(fake):
    from europa_mcp.common import cache_dir

    await pxweb.catalog(SRC)  # BAD answers 400 every time
    assert not pxweb.INCOMPLETE["tst"] and (cache_dir() / "pxweb-tst.json").exists()


async def test_a_one_request_listing_replaces_the_walk_and_archived_tables_are_hidden_by_default(fake):
    mcp = FastMCP("t")
    pxweb.register(mcp, LST)
    rows = await pxweb.catalog(LST)
    assert len(rows) == 26 and fake.gets == [""]  # one request, no folder walk
    old = next(r for r in rows if r["id"] == "OLD/pop/OLD1.px")
    assert old["archived"] == "1" and old["short"] == "OLD1.px" and old["updated"] == "2020-01-01"
    assert "OLD1" not in await call(mcp, "lst_search", query="population")
    assert "OLD1.px|OLD1 -- Population by area, 1990-2000 [discontinued]|2020-01-01" in await call(
        mcp, "lst_search", query="population", include_discontinued=True, limit=50
    )
    entries = await pxweb.map_entries(LST)
    assert len(entries) == 25 and all("OLD" not in e["id"] for e in entries)  # archives stay out of find_data


async def test_describe_marks_an_archived_table(fake):
    mcp = FastMCP("t")
    pxweb.register(mcp, LST)
    TABLES["OLD/pop/OLD1.px"] = {"title": "Old", "variables": TABLES["EMP/UN01"]["variables"]}
    try:
        out = await call(mcp, "lst_describe", table_id="OLD1")
    finally:
        del TABLES["OLD/pop/OLD1.px"]
    assert "status: discontinued (archive folder); prefer a current table" in out


async def test_a_rate_limited_interactive_call_says_so_and_pauses_the_source(fake, instant):
    fake.rate_limited = True
    t = pxweb.Throttle(0.0)
    with pytest.raises(pxweb.UserError, match="is limiting requests"):
        await pxweb.call(SRC, "POP/POP001.px")
    assert len(fake.gets) == 3  # web.fetch tried three times, our call once: no hammering
    t.block(0.0)


async def test_the_throttle_never_sends_more_than_the_per_minute_cap():
    t = pxweb.Throttle(0.0, per_minute=2)
    await t.wait()
    await t.wait()
    t._sent[0] -= 59.95  # the oldest request is 0.05 s from leaving the 60-second window
    start = asyncio.get_running_loop().time()
    await t.wait()
    assert asyncio.get_running_loop().time() - start >= 0.04


async def test_short_id_is_the_full_path_when_two_folders_hold_the_same_table():
    rows = pxweb.finish(
        [
            {"id": "A/X1", "title": "t", "path": "", "updated": ""},
            {"id": "B/X1", "title": "t", "path": "", "updated": ""},
            {"id": "B/Y2.px", "title": "t", "path": "", "updated": ""},
        ]
    )
    assert [r["short"] for r in rows] == ["A/X1", "B/X1", "Y2.px"]


async def test_a_slow_first_walk_answers_still_loading_and_keeps_walking(fake, monkeypatch):
    monkeypatch.setattr(pxweb, "CATALOG_WAIT", 0.01)
    real = pxweb.call

    async def slow(*a, **k):
        await asyncio.sleep(0.2)
        return await real(*a, **k)

    monkeypatch.setattr(pxweb, "call", slow)
    with pytest.raises(pxweb.UserError, match="still loading"):
        await pxweb.catalog(SRC, wait=0.01)
    rows = await pxweb.catalog(SRC, wait=None)  # the same walk finishes; nothing starts twice
    assert len(rows) == 4


async def test_throttle_spaces_requests():
    t = pxweb.Throttle(0.05)
    start = asyncio.get_running_loop().time()
    for _ in range(3):
        await t.wait()
    assert asyncio.get_running_loop().time() - start >= 0.09


# ---- search -----------------------------------------------------------------------------


async def test_search_matches_whole_words_so_house_prices_never_return_household_tables(tools):
    out = await call(tools, "tst_search", query="house prices")
    assert out.splitlines()[:2] == ["id|title|updated", "HP01.px|HP01: House price index 2010Q1 - 2026Q2|2026-02-01"]
    assert "HH01" not in out  # 'household' is not 'house'


async def test_search_translates_local_words_and_says_when_only_some_words_match(tools):
    assert "POP001.px" in await call(tools, "tst_search", query="befolkning")
    out = await call(tools, "tst_search", query="population zebras")
    assert "# no table matches all the words; these match only some of them" in out
    assert (await call(tools, "tst_search", query="zzzz")).startswith("No tables match 'zzzz'")
    assert (await call(tools, "tst_search", query="the of")).startswith("Error: Give topic keywords")


async def test_search_uses_abbreviations_and_the_topic_folder(tools):
    assert "UN01" in await call(tools, "tst_search", query="jobless")  # jobless → unemployment
    out = await call(tools, "tst_search", query="gdp")
    assert out.startswith("No tables match")


# ---- describe / codes -------------------------------------------------------------------


async def test_describe_says_which_variables_are_required_optional_time_and_measures(tools):
    out = await call(tools, "tst_describe", table_id="UN01")
    lines = out.splitlines()
    assert lines[0] == "UN01: Unemployment rate by group" and "updated: 2026-05-06" in lines
    assert "topic: Labour market" in lines
    assert "Group|group|3 (A=Total, B=Men, C=Women)|required: choose values (or '*' for all)" in lines
    assert "Month|month|2026M08, 2026M09|time: newest period by default, last_n=N for more" in lines
    pop = await call(tools, "tst_describe", table_id="pop001")  # case and the .px suffix do not matter
    assert "Region|region|4 (00=..Whole country, 01=..Capital, 02=..Capital city…)|optional: omitted" in pop
    assert "measures (code|text):" in pop and "P2|Population change" in pop


async def test_codes_ignores_hierarchy_dots_orders_exact_first_and_lists_time_newest_first(tools):
    out = await call(tools, "tst_codes", table_id="POP001.px", variable="region", query="capital")
    assert out.splitlines() == ["code|text", "01|..Capital", "02|..Capital city"]
    assert (await call(tools, "tst_codes", table_id="POP001.px", variable="Year")).splitlines()[1] == "2025|2025"
    assert (await call(tools, "tst_codes", table_id="POP001.px", variable="Region", query="atlantis")).startswith(
        "No codes match"
    )
    assert (await call(tools, "tst_codes", table_id="POP001.px", variable="nope")).startswith(
        "Error: Unknown variable 'nope'"
    )


# ---- data -------------------------------------------------------------------------------


async def test_data_defaults_to_the_latest_period_and_all_measures_and_cites_the_source(tools, fake):
    out = await call(tools, "tst_data", table_id="POP001.px", filters={"Region": ["Capital"]})
    lines = out.splitlines()
    assert lines[0] == "POP001.px: Population by region and sex"
    assert "fixed: region=..Capital; year=2025" in lines  # the latest period; hierarchy dots kept in the label
    assert lines[-1] == "source: https://px.example/pxweb/POP/POP001.px · licence: CC0 1.0, Statistics Testland"
    assert "# omitted variables use the server default (normally the total): sex" in lines
    sent = {q["code"]: q["selection"] for q in fake.posts[-1]["query"]}
    assert sent["Year"] == {"filter": "top", "values": ["1"]} and sent["ContentsCode"]["values"] == ["P1", "P2"]
    assert "Sex" not in sent and fake.posts[-1]["response"] == {"format": "json"}


async def test_data_labels_measures_by_position_when_the_server_names_columns_after_the_table(tools):
    out = await call(tools, "tst_data", table_id="POP001.px", filters={"Region": ["00"]}, last_n=2)
    assert "measure" in out and "Population|" in out and "Population change|" in out


async def test_data_omits_missing_symbols_and_counts_them(tools):
    out = await call(tools, "tst_data", table_id="POP001.px", filters={"Region": ["00"], "Year": ["2023"]})
    assert "# omitted empty cells: {'-': 1}" in out and "Population change" not in out.split("# omitted")[0]


async def test_data_requires_a_choice_for_variables_that_cannot_be_omitted(tools):
    out = await call(tools, "tst_data", table_id="UN01")
    assert (
        out == "Error: Choose values for: Group (group, 3 values). Look codes up with tst_codes; '*' means all values."
    )
    ok = await call(tools, "tst_data", table_id="UN01", filters={"Group": ["Total"]}, last_n=1)
    assert "2026M09" in ok and "5.4" in ok and "# omitted variables" not in ok


async def test_data_wildcard_star_selects_all_values_and_non_numeric_gaps_are_not_shown_as_numbers(tools):
    out = await call(tools, "tst_data", table_id="UN01", filters={"Group": ["*"]}, last_n=1)
    assert "Total" in out and "Men" not in out  # '..' = not available, so men and women have no value
    assert "# omitted empty cells: {'..': 2}" in out


async def test_data_refuses_unknown_ambiguous_and_over_broad_requests_before_asking_the_server(tools, fake):
    assert (await call(tools, "tst_data", table_id="UN01", filters={"Group": ["Zzz"]})).startswith(
        "Error: Unknown value 'Zzz' for Group"
    )
    assert (await call(tools, "tst_data", table_id="UN01", filters={"Nope": ["A"]})).startswith(
        "Error: Unknown variable"
    )
    assert (await call(tools, "tst_data", table_id="UN01", filters={"Group": ["A"]}, last_n=1, limit=0)).count(
        "5.4"
    ) == 1
    both = await call(tools, "tst_data", table_id="UN01", filters={"Group": ["A"], "Month": ["2026M08"]}, last_n=2)
    assert both == "Error: Use either last_n or a filter on Month, not both."
    posts = len(fake.posts)
    monkeypatched = pxweb.MAX_CELLS
    pxweb.MAX_CELLS = 3
    try:
        out = await call(tools, "tst_data", table_id="POP001.px", filters={"Region": ["*"], "Year": ["*"]})
    finally:
        pxweb.MAX_CELLS = monkeypatched
    assert out.startswith("Error: query too broad (~24 values, max 3)") and len(fake.posts) == posts


async def test_a_label_shared_by_two_codes_asks_for_the_code(fake):
    meta = {
        "title": "t",
        "variables": [
            {"code": "A", "text": "area", "values": ["1", "2"], "valueTexts": ["Riga", "Rīga"], "elimination": True}
        ],
    }
    var = {"code": "A", "text": "area", "values": ["1", "2"], "texts": ["Riga", "Rīga"], "elim": True, "time": False}
    with pytest.raises(pxweb.UserError, match="label of several codes in A \\(1, 2\\)"):
        pxweb.pick_values(SRC, var, ["riga"])
    assert meta  # the metadata shape the server sends


async def test_unknown_table_and_a_table_in_a_folder_the_walk_skipped(tools, fake):
    assert (await call(tools, "tst_describe", table_id="nosuch")).startswith("Error: Unknown TST table 'nosuch'")
    TABLES["BAD/LOST.px"] = {"title": "Lost table", "variables": TABLES["EMP/UN01"]["variables"]}
    try:
        out = await call(tools, "tst_describe", table_id="BAD/LOST.px")
    finally:
        del TABLES["BAD/LOST.px"]
    assert out.startswith("BAD/LOST.px: Lost table")


# ---- find_data map ----------------------------------------------------------------------


async def test_map_entries_have_period_updated_call_and_headline_marker(fake):
    rows = await pxweb.map_entries(SRC, {"UN01": "unemployment rate jobless"})
    by_id = {r["id"]: r for r in rows}
    un = by_id["EMP/UN01"]
    assert un["source"] == "TST" and un["period"] == "2000M01–2026M09" and un["updated"] == "2026-05-06"
    assert un["call"] == 'tst_describe("EMP/UN01")' and un["path"] == "TST > Labour market"
    assert un["keywords"] == "zqheadline unemployment rate jobless zqend"  # a headline key may be the short code
    rows = await pxweb.map_entries(SRC, {"EMP/UN01": "unemployment rate jobless"})  # or the full path
    assert next(r for r in rows if r["id"] == "EMP/UN01")["keywords"] == "zqheadline unemployment rate jobless zqend"
    assert next(r for r in rows if r["id"] == "POP/POP001.px")["keywords"] == ""
    assert pxweb.period_of("Population 1990-2025") == "1990–2025" and pxweb.period_of("No range here") == ""


# ---- the four countries -----------------------------------------------------------------

PAGES = {
    "se": (
        "BE/BE0101/BE0101A/BefolkningNy",
        "https://www.statistikdatabasen.scb.se/pxweb/en/ssd/START__BE__BE0101__BE0101A/BefolkningNy/",
    ),
    "fi": ("vaerak/11rb.px", "https://pxdata.stat.fi/PxWeb/pxweb/en/StatFin/StatFin__vaerak/11rb.px/"),
    "ee": (
        "rahvastik/rahvastikunaitajad-ja-koosseis/rahvaarv-ja-rahvastiku-koosseis/RV0240.PX",
        "https://andmed.stat.ee/en/stat/rahvastik__rahvastikunaitajad-ja-koosseis__rahvaarv-ja-rahvastiku-koosseis/RV0240.PX",
    ),
    "lv": ("POP/IR/IRS/IRS010", "https://data.stat.gov.lv/pxweb/en/OSP_PUB/START__POP__IR__IRS/IRS010/"),
}
LICENCES = {"se": "CC0 1.0", "fi": "CC BY 4.0", "ee": "CC BY-SA 4.0", "lv": "CC BY 4.0"}


@pytest.mark.parametrize("cc", ["se", "fi", "ee", "lv"])
def test_each_country_is_wired_to_its_office(cc):
    import importlib

    pkg = importlib.import_module(f"europa_mcp.countries.{cc}")
    src = importlib.import_module(f"europa_mcp.countries.{cc}.source").SRC
    table, url = PAGES[cc]
    assert src.page(table) == url
    assert LICENCES[cc] in src.licence
    assert src.base.startswith("https://") and "/en/" in src.base  # English titles
    assert pkg.CODE == cc and src.name in pkg.HINTS["sources"] and src.name in pkg.map_builders()
    assert pkg.HINTS["headline"][src.name], "the most-asked tables must be marked headline"
    assert all(len(v) >= 1 for v in pkg.SYNONYMS.values())
    assert all(w == w.strip() and " " not in w for v in pkg.SYNONYMS.values() for w in v), "single words only"
    # a local word and its English term reach the same group both ways
    assert pxweb.query_groups(src, "population") and pxweb.query_groups(src, next(iter(pkg.SYNONYMS["population"])))


def test_sweden_and_finland_are_throttled_to_their_published_limits():
    from europa_mcp.countries.fi.source import SRC as FI
    from europa_mcp.countries.se.source import SRC as SE

    assert SE.min_interval >= 1.0 and SE.per_minute <= 58  # 10 calls per 10 seconds
    assert FI.per_minute <= 30 and FI.listing  # Statistics Finland answers 429 above ~30 a minute


def test_archives_are_recognised_where_the_offices_keep_discontinued_tables():
    from europa_mcp.countries.ee.source import SRC as EE
    from europa_mcp.countries.lv.source import SRC as LV

    assert EE.archive("Lepetatud_tabelid/Majandus. Arhiiv/TS40.PX") and not EE.archive("majandus/turism/TU17.PX")
    assert LV.archive("POP/ID/A_ID/IMS040") and not LV.archive("POP/ID/IDS/IDS010m")


async def test_a_table_with_many_measures_asks_which_ones_instead_of_dumping_them_all(fake):
    many = {
        "title": "Key figures",
        "variables": [
            {
                "code": "ContentsCode",
                "text": "information",
                "values": [f"M{i}" for i in range(8)],
                "valueTexts": [f"Measure {i}" for i in range(8)],
            },
            {"code": "Year", "text": "year", "values": ["2025"], "valueTexts": ["2025"], "time": True},
        ],
    }
    TABLES["POP/KEY.px"] = many
    pxweb.META.clear()
    mcp = FastMCP("t")
    pxweb.register(mcp, SRC)
    try:
        out = await call(mcp, "tst_data", table_id="POP/KEY.px")
        assert (
            out
            == "Error: Choose values for: ContentsCode (information, 8 measures). Look codes up with tst_codes; '*' means all values."
        )
        desc = await call(mcp, "tst_describe", table_id="POP/KEY.px")
        assert "ContentsCode|information|8|measures: required, choose some (more than 6; '*' = all)" in desc
    finally:
        del TABLES["POP/KEY.px"]


async def test_a_table_caveat_is_printed_with_describe_and_data(fake):
    noted = PxSource(**{**SRC.__dict__, "note": lambda tid: "values are rounded" if tid.endswith("POP001.px") else ""})
    mcp = FastMCP("t")
    pxweb.register(mcp, noted)
    assert "note: values are rounded" in await call(mcp, "tst_describe", table_id="POP001.px")
    out = await call(mcp, "tst_data", table_id="POP001.px", filters={"Region": ["00"]})
    assert out.splitlines()[-2] == "# note: values are rounded" and out.splitlines()[-1].startswith("source: ")
    assert "note:" not in await call(mcp, "tst_describe", table_id="UN01")


def test_sweden_warns_about_the_cell_key_method_only_on_ckm_tables():
    from europa_mcp.countries.se.source import SRC as SE

    assert "randomly adjusted by up to ±3" in SE.note("BE/BE0101/BE0101A/BefolkManadCKM")
    assert "totals may not equal" in SE.note("BE/BE0101/BE0101H/FoddaKCKM")
    assert SE.note("BE/BE0101/BE0101A/BefolkningNy") == ""
