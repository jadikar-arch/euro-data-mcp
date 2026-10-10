import httpx
import pytest
import respx

from cbs_mcp import client
from cbs_mcp.client import BASE_URL, CBSError, NotFound, eq_any, get_json, get_rows, quote


@pytest.fixture(autouse=True)
async def _close():
    yield
    await client.aclose()


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    async def instant(_):
        return None

    monkeypatch.setattr(client.asyncio, "sleep", instant)


def test_quote_escapes_single_quotes():
    assert quote("Regio's") == "'Regio''s'"
    assert eq_any("RegioS", ["A", "B'"]) == "(RegioS eq 'A' or RegioS eq 'B''')"


@respx.mock
async def test_retries_on_5xx_then_succeeds():
    route = respx.get(f"{BASE_URL}/x").mock(
        side_effect=[httpx.Response(503), httpx.Response(429), httpx.Response(200, json={"ok": 1})]
    )
    assert await get_json("/x") == {"ok": 1}
    assert route.call_count == 3


@respx.mock
async def test_gives_up_after_three_attempts():
    respx.get(f"{BASE_URL}/x").mock(return_value=httpx.Response(500))
    with pytest.raises(CBSError, match="after 3 attempts"):
        await get_json("/x")


@respx.mock
async def test_400_surfaces_short_api_message():
    msg = "The query specified in the URI is not valid. Could not find a property named 'Regio'."
    respx.get(f"{BASE_URL}/x").mock(return_value=httpx.Response(400, json={"error": {"message": msg}}))
    with pytest.raises(CBSError, match=r"^CBS API error 400: Could not find a property named 'Regio'"):
        await get_json("/x")


@respx.mock
async def test_404_is_not_found():
    respx.get(f"{BASE_URL}/x").mock(return_value=httpx.Response(404))
    with pytest.raises(NotFound):
        await get_json("/x")


@respx.mock
async def test_follows_next_link_until_limit():
    respx.get(f"{BASE_URL}/rows", params={"$skip": "2"}).mock(
        return_value=httpx.Response(200, json={"value": [{"i": 2}, {"i": 3}],
                                               "@odata.nextLink": f"{BASE_URL}/rows?$skip=4"})
    )
    respx.get(f"{BASE_URL}/rows").mock(
        return_value=httpx.Response(200, json={"value": [{"i": 0}, {"i": 1}], "@odata.count": 9,
                                               "@odata.nextLink": f"{BASE_URL}/rows?$skip=2"})
    )
    rows, total = await get_rows("/rows", {"$count": "true"}, limit=3)
    assert [r["i"] for r in rows] == [0, 1, 2]
    assert total == 9
