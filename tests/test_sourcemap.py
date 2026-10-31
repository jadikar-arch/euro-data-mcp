"""The cross-source map behind find_data: building, ranking and the tool output."""

from __future__ import annotations

import pytest
from fastmcp import Client

from europa_mcp import server, sourcemap
from europa_mcp.countries import eu
from europa_mcp.countries.eu.mapping import toc_entries
from europa_mcp.sourcemap import SourceMap, expand

TOC = (
    '"title"\t"code"\t"type"\t"last update of data"\t"last table structure change"\t"data start"\t"data end"\t"values"\n'
    '"Database by themes"\t"data"\t"folder"\t" "\t" "\t" "\t" "\t\n'
    '"    Economy and finance"\t"economy"\t"folder"\t" "\t" "\t" "\t" "\t\n'
    '"        Prices"\t"prc"\t"folder"\t" "\t" "\t" "\t" "\t\n'
    '"            House price index - quarterly data"\t"prc_hpi_q"\t"dataset"\t"01.10.2026"\t" "\t"2005-Q1"\t"2026-Q2"\t1\n'
    '"    Population and social conditions"\t"popul"\t"folder"\t" "\t" "\t" "\t" "\t\n'
    '"        Gas prices for household consumers"\t"nrg_pc_202"\t"dataset"\t"01.10.2026"\t" "\t"2007"\t"2025"\t1\n'
    '"Tables by themes"\t"t"\t"folder"\t" "\t" "\t" "\t" "\t\n'
    '"    Housing"\t"th"\t"folder"\t" "\t" "\t" "\t" "\t\n'
    '"        House price index - quarterly data"\t"prc_hpi_q"\t"dataset"\t"01.10.2026"\t" "\t"2005-Q1"\t"2026-Q2"\t1\n'
)

ENTRIES = {
    "Eurostat": toc_entries(TOC),
    "Destatis": [
        {"source": "Destatis", "id": "12411-0010", "title": "Bevölkerung: Bundesländer, Stichtag", "path": "",
         "keywords": "Bevölkerungsstand", "period": "", "updated": "", "call": 'govdata_table("12411-0010")'},
        {"source": "Destatis", "id": "61262-0001", "title": "Häuserpreisindex, Preisindex für Bauland", "path": "",
         "keywords": "Wohnimmobilien", "period": "", "updated": "", "call": 'govdata_table("61262-0001")'},
    ],
    "Agrifood": [
        {"source": "Agrifood", "id": "pigmeat/prices", "title": "Pigmeat (carcasses and piglets) prices",
         "path": "EU agri-food > Pigmeat", "keywords": "pigmeat prices pork pig carcass", "period": "", "updated": "",
         "call": 'agri_data("pigmeat/prices", params={memberStateCodes})'},
    ],
}


@pytest.fixture
def smap(tmp_path, monkeypatch):
    m = SourceMap(tmp_path / "map.db", synonyms=server.all_synonyms())
    for builder, rows in ENTRIES.items():
        m.replace(builder, rows)
    m.replace("eu-curated", [{**e, "path": "", "period": "", "updated": ""} for e in eu.HINTS["entries"]])
    monkeypatch.setattr(server, "SOURCE_MAP", m)
    return m


def test_toc_entries_keep_theme_path_and_dedupe():
    rows = {r["id"]: r for r in toc_entries(TOC)}
    assert set(rows) == {"prc_hpi_q", "nrg_pc_202"}
    hpi = rows["prc_hpi_q"]
    assert hpi["path"] == "Economy and finance > Prices"
    assert "Housing" in hpi["keywords"]  # second location in the theme tree
    assert (hpi["period"], hpi["updated"], hpi["call"]) == (
        "2005-Q1–2026-Q2", "2026-10-01", 'eurostat_describe("prc_hpi_q")')


def test_words_of_splits_paths_and_camel_case():
    assert sourcemap.words_of("rawMilk/prices") == "raw milk prices rawmilk prices"
    assert sourcemap.words_of("adopted-texts") == "adopted texts"


def test_expand_uses_both_directions_and_hints(smap):
    groups = expand("bevölkerung pork chômage", smap.synonyms)
    assert "population" in groups[0]  # German → English (reversed de.SYNONYMS)
    assert "pigmeat" in groups[1]  # hints.json synonym
    assert "unemployment" in groups[2]  # multilingual hint, accents folded


def test_short_terms_do_not_prefix_match(smap):
    ids = [r["id"] for r in smap.search("house prices", ["Eurostat"])]
    assert ids[0] == "prc_hpi_q"  # 'house' must not match 'household'
    assert smap.search("house prices", ["Eurostat"])[0]["coverage"] == 1.0
    assert all(r["coverage"] < 1.0 for r in smap.search("house prices") if r["id"] == "nrg_pc_202")


def test_own_words_beat_synonyms(smap):
    assert smap.search("bevölkerung")[0]["id"] == "12411-0010"
    assert smap.search("pork prices")[0]["id"] == "pigmeat/prices"


def test_replace_only_touches_its_builder(smap):
    smap.replace("Agrifood", [])
    assert smap.count("Agrifood") == 0
    assert smap.count("European Parliament") == 2  # curated EP entries survive
    assert smap.count("Destatis") == 2


def test_headline_dataset_beats_title_match_at_equal_coverage(tmp_path):
    toc = (
        '"title"\t"code"\t"type"\t"last update of data"\t"last table structure change"\t"data start"\t"data end"\t"values"\n'
        '"    Labour market"\t"lm"\t"folder"\t" "\t" "\t" "\t" "\t\n'
        '"        Headline indicators"\t"hi"\t"folder"\t" "\t" "\t" "\t" "\t\n'
        '"            Tax rate on low wage earners - unemployment trap"\t"earn_nt_unemtrp"\t"dataset"\t"01.10.2026"\t" "\t"2001"\t"2025"\t1\n'
        '"            Unemployment by sex and age - monthly data"\t"une_rt_m"\t"dataset"\t"30.10.2026"\t" "\t"1983-01"\t"2026-09"\t1\n'
    )
    m = SourceMap(tmp_path / "m.db", synonyms={})
    m.replace("Eurostat", toc_entries(toc, {"une_rt_m": "unemployment rate jobless"}))
    ranked = m.search("unemployment rate")
    assert [r["id"] for r in ranked] == ["une_rt_m", "earn_nt_unemtrp"]
    # A real "Headline indicators" folder in the path must not count as the headline mark.
    assert m.search("unemployment trap")[0]["id"] == "earn_nt_unemtrp"


async def call(**args) -> str:
    async with Client(server.mcp) as c:
        result = await c.call_tool("find_data", args, raise_on_error=False)
    return "".join(getattr(b, "text", "") for b in result.content)


async def test_find_data_returns_a_ranked_list_for_the_user_to_choose_from(smap):
    out = await call(query="house prices")
    lines = out.splitlines()
    assert lines[0].startswith("Ranked matches for 'house prices' (best first")
    assert lines[1] == "rank|match|source|id|title|period|breakdowns|next call"
    assert lines[2] == ('1|100%|Eurostat|prc_hpi_q|House price index - quarterly data|2005-Q1–2026-Q2||'
                        'eurostat_describe("prc_hpi_q")')
    assert any(ln.split("|")[2:4] == ["Destatis", "61262-0001"] for ln in lines[3:])
    assert lines[-3].startswith("# sources: Eurostat = EU/EEA country comparisons")
    assert lines[-2] == server.ASK_USER_NOTE
    assert lines[-1].startswith('# not it? dataeu_search("house prices")')


def test_breakdowns_are_shown_to_people_choosing(tmp_path, monkeypatch):
    m = SourceMap(tmp_path / "m.db", synonyms={})
    m.replace("Eurostat", toc_entries(TOC, breakdowns={"prc_hpi_q": ("regional regions nuts2", "NUTS 2 regions")}))
    rows = m.search("house prices")
    assert rows[0]["detail"] == "NUTS 2 regions"
    assert server.option_label(1, rows[0]) == (
        "1. House price index - quarterly data (Eurostat prc_hpi_q; 2005-Q1–2026-Q2; by NUTS 2 regions)")


async def choose(smap, answer, mode="auto"):
    """Run find_data in a client that supports elicitation and answers with `answer`.
    mode='auto' negotiates the 2026-07-28 protocol (input_required round trip); 'legacy' an older
    one where the server asks in the middle of the call."""
    asked = []

    async def handler(message, response_type, params, context):
        asked.append((message, params.requested_schema))
        return answer(params.requested_schema) if callable(answer) else answer

    async with Client(server.mcp, elicitation_handler=handler, mode=mode) as c:
        r = await c.call_tool("find_data", {"query": "prices"}, raise_on_error=False)
    return "".join(getattr(b, "text", "") for b in r.content), asked


def options(schema) -> list[str]:
    value = schema["properties"]["value"]
    return value.get("enum") or [o["const"] for o in value.get("oneOf", [])]


async def test_user_picks_a_dataset_in_older_apps_too(smap):
    out, asked = await choose(smap, lambda schema: {"value": options(schema)[0]}, mode="legacy")
    assert asked and out.startswith("The user chose rank 1 of ") and "\nNext call: " in out


async def test_user_picks_a_dataset_in_the_app(smap):
    from fastmcp.client.elicitation import ElicitResult

    out, asked = await choose(smap, lambda schema: {"value": options(schema)[1]})
    assert asked and asked[0][0] == "Which dataset should be used for 'prices'? Best matches first."
    opts = options(asked[0][1])
    assert opts[0].startswith("1. ") and opts[-1] == "None of these"
    assert out.startswith("The user chose rank 2 of ") and "\nNext call: " in out

    out, _ = await choose(smap, lambda schema: {"value": "None of these"})
    assert out.startswith("The user said none of the") and 'dataeu_search("prices")' in out

    out, _ = await choose(smap, ElicitResult(action="decline"))
    assert out.startswith("Ranked matches for 'prices'") and server.CLOSED_NOTE in out
    assert "|0%|" not in out  # a fresh ranking, not the saved state


async def test_no_picker_when_the_app_cannot_show_one_or_ask_user_is_off(smap):
    out = await call(query="prices")  # plain client: no elicitation capability
    assert out.startswith("Ranked matches") and server.ASK_USER_NOTE in out
    out, asked = await choose(smap, lambda schema: {"value": options(schema)[0]})
    assert asked  # sanity: this client can show a picker
    async with Client(server.mcp, elicitation_handler=lambda *a: None) as c:
        r = await c.call_tool("find_data", {"query": "prices", "ask_user": False}, raise_on_error=False)
    assert "".join(getattr(b, "text", "") for b in r.content).startswith("Ranked matches")


async def test_find_data_source_filter_and_errors(smap):
    out = await call(query="votes", sources=["european"])
    assert "ep_votes(date=" in out and "## Eurostat" not in out
    assert (await call(query="x", sources=["nope"])).startswith("Error: Unknown sources")
    assert (await call(query="zzqx")).startswith("No mapped source matches 'zzqx'.")


async def test_ensure_runs_missing_builders_once(tmp_path):
    calls = []

    async def ok():
        calls.append("ok")
        return [{"source": "X", "id": "1", "title": "t"}]

    async def broken():
        calls.append("broken")
        raise RuntimeError("down")

    m = SourceMap(tmp_path / "m.db", builders={"ok": ok, "broken": broken})
    await m.ensure()
    await m.ensure()  # the failure is recorded, so nothing is retried on every call
    assert sorted(calls) == ["broken", "ok"]
    assert m.count("X") == 1 and m.missing() == []


def test_rows_of_retired_builders_are_pruned(tmp_path):
    async def ok():
        return []

    path = tmp_path / "m.db"
    old = SourceMap(path, builders={"ok": ok, "CBS": ok})
    old.replace("CBS", [{"source": "CBS", "id": "37230ned", "title": "Bevolking", "call": 'cbs_describe("x")'}])
    old.db.close()
    new = SourceMap(path, builders={"ok": ok})  # the CBS package is gone
    assert new.count("CBS") == 0
    assert new.search("bevolking") == [] and "CBS" not in new.missing()


def test_parse_metabase_turns_dimensions_into_breakdown_words():
    from europa_mcp.countries.eu.mapping import parse_metabase

    text = "\n".join([
        "demo_r_d2jan\tgeo\tEU27_2020", "demo_r_d2jan\tgeo\tNL", "demo_r_d2jan\tgeo\tNL3", "demo_r_d2jan\tgeo\tNL32",
        "demo_r_d2jan\tsex\tF", "demo_r_d2jan\tage\tY_LT5", "demo_r_d2jan\ttime\t2025",
        "une_rt_m\tgeo\tEA20", "une_rt_m\tgeo\tDE", "une_rt_m\tsex\tT",
        "urb_cpop1\tcities\tNL002C", "bad line",
    ])
    out = parse_metabase(text)
    assert out["demo_r_d2jan"] == ("age sex gender men women regional regions nuts2", "age, sex, NUTS 2 regions")
    assert out["une_rt_m"] == ("sex gender men women", "sex")  # EA20 is an aggregate, not a NUTS region
    assert out["urb_cpop1"] == ("cities city urban", "cities")


def test_breakdowns_route_by_region_questions(tmp_path):
    toc = (
        '"title"\t"code"\t"type"\t"last update of data"\t"last table structure change"\t"data start"\t"data end"\t"values"\n'
        '"    Population"\t"pop"\t"folder"\t" "\t" "\t" "\t" "\t\n'
        '"        Population on 1 January by age and sex"\t"demo_pjan"\t"dataset"\t"01.10.2026"\t" "\t"1960"\t"2025"\t1\n'
        '"        Population on 1 January by broad age group, sex and NUTS 3 region"\t"demo_r_pjanaggr3"\t"dataset"\t"01.10.2026"\t" "\t"1990"\t"2025"\t1\n'
    )
    m = SourceMap(tmp_path / "m.db", synonyms={})
    m.replace("Eurostat", toc_entries(toc, breakdowns={"demo_r_pjanaggr3": ("regional regions nuts3", "NUTS 3 regions")}))
    assert m.search("population by region")[0]["id"] == "demo_r_pjanaggr3"


async def test_eurostat_search_uses_the_map_ranking(smap):
    async with Client(server.mcp) as c:
        r = await c.call_tool("eurostat_search", {"query": "house prices"}, raise_on_error=False)
    out = "".join(getattr(b, "text", "") for b in r.content)
    assert out.splitlines()[1].startswith("prc_hpi_q|House price index - quarterly data|2005-Q1–2026-Q2|")


def test_stem_plurals_and_rnd():
    assert sourcemap.stem("bankruptcies") == "bankruptc" and sourcemap.stem("homicides") == "homicide"
    assert sourcemap.stem("cities") == "cities"  # stem would be too short to be useful
    assert sourcemap.stem("business") == "business" and sourcemap.stem("census") == "census"
    assert expand("R&D expenditure", {}) == [["research"], ["development"], ["expenditure"]]
    assert expand("inflation France", {}) == [["inflation"]]  # countries are filters, not topics


def test_demoted_neighbourhood_and_discontinued():
    assert sourcemap.demoted({"id": "enpe_demo_r_d3dens", "period": "2010–2025"}, 2026)
    assert sourcemap.demoted({"id": "prc_hicp_manr", "period": "1997–2021"}, 2026)
    assert not sourcemap.demoted({"id": "sdg_15_11", "period": "2015–2024"}, 2026)  # slow updates are fine
    assert not sourcemap.demoted({"id": "ep_votes", "period": ""}, 2026)


def test_headline_needs_its_own_words_not_just_the_title(tmp_path):
    toc = (
        '"title"\t"code"\t"type"\t"last update of data"\t"last table structure change"\t"data start"\t"data end"\t"values"\n'
        '"    Labour market"\t"lm"\t"folder"\t" "\t" "\t" "\t" "\t\n'
        '"        Part-time employment rate"\t"tesem100"\t"table"\t"01.10.2026"\t" "\t"2015"\t"2025"\t1\n'
        '"        Employment and labour force by sex and age - annual data"\t"lfsi_emp_a"\t"dataset"\t"01.10.2026"\t" "\t"2003"\t"2025"\t1\n'
        '"        Bankruptcy index - quarterly data"\t"sts_rb_q"\t"dataset"\t"01.10.2026"\t" "\t"2000-Q1"\t"2026-Q2"\t1\n'
    )
    m = SourceMap(tmp_path / "m.db", synonyms={})
    m.replace("Eurostat", toc_entries(toc, {"tesem100": "part-time", "lfsi_emp_a": "employment rate jobs"}))
    assert m.search("employment rate")[0]["id"] == "lfsi_emp_a"
    assert m.search("part-time employment")[0]["id"] == "tesem100"
    assert m.search("bankruptcies")[0]["id"] == "sts_rb_q"  # plural finds the singular


def test_old_cache_gets_the_breakdown_column_and_a_rebuild(tmp_path):
    import sqlite3

    path = tmp_path / "old.db"
    db = sqlite3.connect(path)
    db.executescript("""
        CREATE TABLE entries(source TEXT NOT NULL, id TEXT NOT NULL, title TEXT, path TEXT, keywords TEXT,
            period TEXT, updated TEXT, call TEXT, builder TEXT NOT NULL, PRIMARY KEY(source, id));
        CREATE TABLE map_meta(source TEXT PRIMARY KEY, built REAL, count INTEGER);
        INSERT INTO entries VALUES('Eurostat','x','t','','','','','c','Eurostat');
        INSERT INTO map_meta VALUES('Eurostat', 1.0, 1);""")
    db.commit()
    db.close()

    async def build():
        return []

    m = SourceMap(path, builders={"Eurostat": build})
    assert "detail" in {r[1] for r in m.db.execute("PRAGMA table_info(entries)")}
    assert m.missing() == ["Eurostat"]  # rebuilt on the next ensure()
