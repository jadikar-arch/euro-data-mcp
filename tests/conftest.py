"""Shared test setup: no background work, so each test drives what it needs."""

import pytest

from europa_mcp import preview, server
from europa_mcp.sourcemap import SourceMap

PRIVATE_HOSTS = {"intranet.example": "10.0.0.7", "rebind.example": "127.0.0.1"}


@pytest.fixture(autouse=True)
def no_background_tasks(monkeypatch):
    """The server lifespan starts the find_data map refresh; tests build maps themselves."""
    monkeypatch.setattr(server, "ensure_map_task", lambda: None)
    # An empty map by default (never the user's cache); tests that need entries install their own.
    monkeypatch.setattr(server, "SOURCE_MAP", SourceMap(":memory:", synonyms=server.all_synonyms()))


@pytest.fixture(autouse=True)
def fake_dns(monkeypatch):
    """Offline DNS for the preview URL check: every host is public except PRIVATE_HOSTS."""
    async def resolve(host: str) -> list[str]:
        return [PRIVATE_HOSTS.get(host, "93.184.215.14")]

    monkeypatch.setattr(preview, "resolve", resolve)
