"""Smoke tests against the real APIs. Run with: uv run pytest -m live (CI runs them nightly)."""

import pytest
from fastmcp import Client

from europa_mcp import server, web
from europa_mcp.countries import COUNTRIES
from europa_mcp.sourcemap import SourceMap

pytestmark = pytest.mark.live


def data_lines(out: str) -> list[str]:
    return [ln for ln in out.splitlines() if not ln.startswith(("#", "source:"))]


async def test_eu_apis_end_to_end():
    """One real call per EU API; each must answer compactly and cite its source."""
    async with Client(server.mcp) as c:

        async def text(name, **args):
            r = await c.call_tool(name, args, raise_on_error=False)
            out = "".join(getattr(b, "text", "") for b in r.content)
            assert not out.startswith("Error"), f"{name}: {out[:300]}"
            assert len(out) < 8000, f"{name} response too large (~{len(out) // 4} tokens)"
            return out

        assert "prc_hpi_q" in await text("eurostat_search", query="house price index")
        out = await text(
            "eurostat_data",
            dataset_id="prc_hpi_q",
            last_n=1,
            filters={"geo": ["NL"], "purchase": ["TOTAL"], "unit": ["I15_Q"]},
        )
        assert 100 < float(data_lines(out)[-1].split("|")[-1]) < 500
        assert out.splitlines()[-1].startswith("source: https://ec.europa.eu/eurostat/databrowser/view/")
        for agency in ("empl", "grow", "taxud"):
            assert "|" in await text("eurostat_search", query="", agency=agency, limit=1)
        assert "pigmeat/prices" in await text("agri_endpoints", query="pig")
        assert "|NL|" in await text("ep_meps", country="NL")
        assert "dataportaal" in await text("dataeu_search", query="cbs", country="nl", limit=3)
        assert "|" in await text("dataeu_search", query="air quality", sort="newest", limit=3)

        # Preview the first CSV that a publisher actually serves (some links are always dead).
        found = await text("dataeu_search", query="population", format="CSV", min_quality="good", limit=10)
        previews = []
        for ds in [ln.split("|")[0] for ln in data_lines(found)[1:]]:
            r = await c.call_tool("dataeu_preview", {"dataset_id": ds, "limit": 3}, raise_on_error=False)
            previews.append("".join(getattr(b, "text", "") for b in r.content))
            if not previews[-1].startswith("Error"):
                break
        assert "source: http" in previews[-1], previews


async def test_find_data_ranks_headline_datasets_first(tmp_path, monkeypatch):
    builders = {name: fn for c in COUNTRIES for name, fn in c.map_builders().items()}
    smap = SourceMap(tmp_path / "map.db", synonyms=server.all_synonyms(), builders=builders)
    await smap.build()
    assert smap.count("Eurostat") > 5000
    assert "zqheadline" in smap.db.execute("SELECT keywords FROM entries WHERE id='une_rt_m'").fetchone()[0]
    assert smap.search("unemployment rate")[0]["id"] in ("une_rt_m", "une_rt_a", "une_rt_q", "tps00203", "teilm020")
    assert smap.search("inflation")[0]["id"] in ("prc_hicp_minr", "prc_hicp_aind")
    assert smap.search("population by region")[0]["id"].startswith(("demo_r_", "tgs"))  # metabase breakdowns
    await web.aclose()


async def test_cbs_end_to_end():
    """The Netherlands: find a table, look up codes, fetch values; each answer cites CBS."""
    async with Client(server.mcp) as c:

        async def text(name, **args):
            r = await c.call_tool(name, args, raise_on_error=False)
            out = "".join(getattr(b, "text", "") for b in r.content)
            assert not out.startswith("Error"), f"{name}: {out[:300]}"
            assert len(out) < 8000, f"{name} response too large (~{len(out) // 4} tokens)"
            return out

        assert "37230ned" in await text("cbs_search", query="bevolkingsontwikkeling regio per maand")
        assert "RegioS|" in await text("cbs_describe", dataset_id="37230ned")
        assert "GM0363|Amsterdam" in await text(
            "cbs_codes", dataset_id="37230ned", dimension="RegioS", query="Amsterdam"
        )
        out = await text(
            "cbs_data", dataset_id="37230ned", measures=["M000098"], filters={"RegioS": ["GM0363"]}, latest=True
        )
        assert 500_000 < float(data_lines(out)[-1]) < 2_000_000
        assert out.splitlines()[-1].startswith("source: https://opendata.cbs.nl/")
        assert "Werkloosheidspercentage: Seizoengecorrigeerd" in await text(
            "cbs_data", dataset_id="80590ned", latest=True, limit=20
        )
