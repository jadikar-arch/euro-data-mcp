"""Smoke tests against the real APIs. Run with: uv run pytest -m live (CI runs them nightly)."""

import pytest
from fastmcp import Client

from europa_mcp import server, web

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
        out = await text("eurostat_data", dataset_id="prc_hpi_q", last_n=1,
                         filters={"geo": ["NL"], "purchase": ["TOTAL"], "unit": ["I15_Q"]})
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


async def test_find_data_ranks_headline_datasets_first():
    smap = server.get_map()
    await smap.ensure()
    assert smap.search("unemployment rate")[0]["id"] in ("une_rt_m", "une_rt_a", "une_rt_q")
    assert smap.search("inflation")[0]["id"] in ("prc_hicp_minr", "prc_hicp_aind")
    await web.aclose()
