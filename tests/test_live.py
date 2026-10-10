"""Smoke test against the real CBS API. Run with: uv run pytest -m live"""

import pytest
from fastmcp import Client

from cbs_mcp import client, server
from cbs_mcp.index import Index

pytestmark = pytest.mark.live


async def test_amsterdam_population_end_to_end(tmp_path, monkeypatch):
    idx = Index(tmp_path / "index.db")
    await idx.sync(details=False)
    monkeypatch.setattr(server, "INDEX", idx)
    monkeypatch.setattr(server, "ensure_sync_task", lambda: None)

    async with Client(server.mcp) as c:
        async def text(name, **args):
            r = await c.call_tool(name, args, raise_on_error=False)
            out = "".join(getattr(b, "text", "") for b in r.content)
            assert len(out) < 8000, f"{name} response too large (~{len(out) // 4} tokens)"
            return out

        assert "37230ned" in await text("search_datasets", query="bevolking regio")
        assert "M000098" in await text("describe_dataset", dataset_id="37230ned")
        assert "GM0363|Amsterdam" in await text(
            "list_codes", dataset_id="37230ned", dimension="RegioS", query="Amsterdam"
        )
        out = await text(
            "get_observations", dataset_id="37230ned", measures=["M000098"],
            filters={"RegioS": ["GM0363"]}, latest=True,
        )
    value = int(out.splitlines()[-1])
    assert 800_000 < value < 1_200_000
    await client.aclose()
