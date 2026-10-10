"""Thin async client for the CBS OData v4 API (https://datasets.cbs.nl/odata/v1)."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Iterable
from typing import Any

import httpx

log = logging.getLogger("cbs_mcp")

BASE_URL = os.environ.get("CBS_BASE_URL", "https://datasets.cbs.nl/odata/v1").rstrip("/")
RETRY_STATUS = {429, 500, 502, 503, 504}
ATTEMPTS = 3
SERVER_PAGE = 100_000  # rows per page before the server emits @odata.nextLink


class CBSError(Exception):
    """A user-facing error: the message is safe to return to the model."""


class NotFound(CBSError):
    pass


_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=httpx.Timeout(30.0),
            headers={"Accept": "application/json", "User-Agent": "cbs-mcp"},
            follow_redirects=True,
        )
    return _client


async def aclose() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def _error_message(resp: httpx.Response) -> str:
    try:
        msg = resp.json()["error"]["message"]
    except Exception:
        msg = resp.text[:200]
    # The API repeats its prefix; keep the useful tail.
    return msg.replace("The query specified in the URI is not valid. ", "").strip()


async def get_json(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """GET a path (or absolute nextLink URL) with retry on 429/5xx and network errors."""
    client = get_client()
    for attempt in range(ATTEMPTS):
        try:
            resp = await client.get(path, params=params)
        except httpx.TransportError as e:
            if attempt == ATTEMPTS - 1:
                raise CBSError(f"CBS API unreachable: {type(e).__name__}") from None
        else:
            if resp.status_code == 404:
                raise NotFound(f"Not found: {path}")
            if resp.status_code < 400:
                return resp.json()
            if resp.status_code not in RETRY_STATUS:
                raise CBSError(f"CBS API error {resp.status_code}: {_error_message(resp)}")
            if attempt == ATTEMPTS - 1:
                raise CBSError(f"CBS API error {resp.status_code} after {ATTEMPTS} attempts")
            retry_after = resp.headers.get("Retry-After", "")
            if retry_after.isdigit():
                await asyncio.sleep(min(int(retry_after), 10))
                continue
        await asyncio.sleep(0.5 * 2**attempt)
    raise AssertionError("unreachable")


async def get_rows(
    path: str, params: dict[str, Any] | None = None, limit: int | None = None
) -> tuple[list[dict[str, Any]], int | None]:
    """Fetch `value` rows, following @odata.nextLink until `limit` rows.

    Returns (rows, total) where total is @odata.count if `$count=true` was requested.
    """
    params = dict(params or {})
    if limit is not None:
        params["$top"] = limit
    data = await get_json(path, params)
    rows: list[dict[str, Any]] = list(data.get("value", []))
    total = data.get("@odata.count")
    next_link = data.get("@odata.nextLink")
    while next_link and (limit is None or len(rows) < limit):
        data = await get_json(next_link)
        rows.extend(data.get("value", []))
        next_link = data.get("@odata.nextLink")
    if limit is not None:
        rows = rows[:limit]
    return rows, total


def quote(value: str) -> str:
    """OData string literal: single quotes doubled."""
    return "'" + str(value).replace("'", "''") + "'"


def eq_any(field: str, values: Iterable[str]) -> str:
    """`(F eq 'a' or F eq 'b')`."""
    parts = [f"{field} eq {quote(v)}" for v in values]
    if not parts:
        raise ValueError("no values")
    return "(" + " or ".join(parts) + ")"


def clean(row: dict[str, Any]) -> dict[str, Any]:
    """Drop @odata.* keys, nulls and empty strings."""
    return {
        k: v for k, v in row.items() if not k.startswith("@odata") and v is not None and v != ""
    }


class TTLCache:
    """Tiny in-memory TTL cache for metadata; entries can be dropped per dataset."""

    def __init__(self, ttl: float = 6 * 3600):
        self.ttl = ttl
        self._data: dict[tuple, tuple[float, Any]] = {}

    def get(self, key: tuple) -> Any:
        hit = self._data.get(key)
        if hit is None or time.monotonic() - hit[0] > self.ttl:
            return None
        return hit[1]

    def set(self, key: tuple, value: Any) -> None:
        self._data[key] = (time.monotonic(), value)

    def invalidate(self, dataset_id: str) -> None:
        for key in [k for k in self._data if k and k[0] == dataset_id]:
            del self._data[key]
