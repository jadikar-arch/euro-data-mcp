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


async def test_find_data_groups_by_source_with_next_call(smap):
    out = await call(query="house prices")
    lines = out.splitlines()
    assert lines[0] == "id|title|topic|period|next call"
    assert lines[1].startswith("## Eurostat: EU/EEA country comparisons")
    assert lines[2] == ('prc_hpi_q|House price index - quarterly data|Prices|2005-Q1–2026-Q2|'
                        'eurostat_describe("prc_hpi_q")')
    assert "## Destatis:" in out and 'govdata_table("61262-0001")' in out
    assert lines[-1].startswith('# not it? dataeu_search("house prices")')


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
