"""Smoke test against the real CBS API. Run with: uv run pytest -m live"""

import pytest
from fastmcp import Client

from europa_mcp import server, web
from europa_mcp.countries.nl import cbs, client
from europa_mcp.countries.nl.index import Index

pytestmark = pytest.mark.live


async def test_amsterdam_population_end_to_end(tmp_path, monkeypatch):
    idx = Index(tmp_path / "index.db")
    await idx.sync(details=False)
    monkeypatch.setattr(cbs, "INDEX", idx)
    monkeypatch.setattr(cbs, "ensure_sync_task", lambda: None)

    async with Client(server.mcp) as c:
        async def text(name, **args):
            r = await c.call_tool(name, args, raise_on_error=False)
            out = "".join(getattr(b, "text", "") for b in r.content)
            assert len(out) < 8000, f"{name} response too large (~{len(out) // 4} tokens)"
            return out

        assert "37230ned" in await text("cbs_search", query="bevolking regio")
        assert "M000098" in await text("cbs_describe", dataset_id="37230ned")
        assert "GM0363|Amsterdam" in await text(
            "cbs_codes", dataset_id="37230ned", dimension="RegioS", query="Amsterdam"
        )
        out = await text(
            "cbs_data", dataset_id="37230ned", measures=["M000098"],
            filters={"RegioS": ["GM0363"]}, latest=True,
        )
    value = int(out.splitlines()[-1])
    assert 800_000 < value < 1_200_000
    await client.aclose()


async def test_eu_apis_end_to_end():
    """One real call per EU API; each must answer compactly."""
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
        value = [ln for ln in out.splitlines() if not ln.startswith("#")][-1].split("|")[-1]
        assert 100 < float(value) < 500
        for agency in ("empl", "grow", "taxud"):
            assert "|" in await text("eurostat_search", query="", agency=agency, limit=1)
        assert "pigmeat/prices" in await text("agri_endpoints", query="pig")
        assert "|NL|" in await text("ep_meps", country="NL")
        assert "dataportaal" in await text("dataeu_search", query="cbs", country="nl", limit=3)
    await web.aclose()
