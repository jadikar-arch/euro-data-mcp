"""Shared async HTTP for the EU APIs: absolute URLs, retry on 429/5xx, short error messages."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlsplit

import httpx

from .client import ATTEMPTS, RETRY_STATUS, CBSError, NotFound

_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=15.0),
            headers={"User-Agent": "cbs-mcp"},
            follow_redirects=True,
        )
    return _client


async def aclose() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def _message(resp: httpx.Response) -> str:
    try:
        body = resp.json()
    except Exception:
        return " ".join(resp.text[:200].split()) or resp.reason_phrase
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, list) and err and isinstance(err[0], dict):
            return str(err[0].get("label") or err[0])[:300]
        for key in ("message", "description", "label", "error"):
            if isinstance(body.get(key), str):
                return body[key][:300]
    return str(body)[:200]


async def fetch(
    url: str,
    params: Any = None,
    *,
    headers: dict[str, str] | None = None,
    timeout: float | None = None,
) -> httpx.Response:
    """GET with retry; raises NotFound on 404 and CBSError on other failures."""
    host = urlsplit(url).netloc
    client = get_client()
    kwargs: dict[str, Any] = {"params": params, "headers": headers}
    if timeout:
        kwargs["timeout"] = timeout
    for attempt in range(ATTEMPTS):
        try:
            resp = await client.get(url, **kwargs)
        except httpx.TimeoutException:
            raise CBSError(f"{host} timed out; narrow the request.") from None
        except httpx.TransportError as e:
            if attempt == ATTEMPTS - 1:
                raise CBSError(f"{host} unreachable: {type(e).__name__}") from None
        else:
            if resp.status_code == 404:
                raise NotFound(_message(resp))
            if resp.status_code < 400:
                return resp
            if resp.status_code not in RETRY_STATUS:
                raise CBSError(f"{host} error {resp.status_code}: {_message(resp)}")
            if attempt == ATTEMPTS - 1:
                raise CBSError(f"{host} error {resp.status_code} after {ATTEMPTS} attempts")
            retry_after = resp.headers.get("Retry-After", "")
            if retry_after.isdigit():
                await asyncio.sleep(min(int(retry_after), 10))
                continue
        await asyncio.sleep(0.5 * 2**attempt)
    raise AssertionError("unreachable")


async def fetch_json(url: str, params: Any = None, **kw) -> Any:
    """JSON body, or None for 204 No Content."""
    resp = await fetch(url, params, **kw)
    if resp.status_code == 204 or not resp.content:
        return None
    try:
        return resp.json()
    except ValueError:
        raise CBSError(f"{urlsplit(url).netloc} returned non-JSON ({resp.headers.get('content-type')})") from None


class Memo:
    """Async TTL memo with per-key locks so concurrent callers share one download."""

    def __init__(self, ttl: float):
        self.ttl = ttl
        self._data: dict[Any, tuple[float, Any]] = {}
        self._locks: dict[Any, asyncio.Lock] = {}

    async def get(self, key: Any, load: Callable[[], Awaitable[Any]]) -> Any:
        hit = self._data.get(key)
        if hit and time.monotonic() - hit[0] < self.ttl:
            return hit[1]
        async with self._locks.setdefault(key, asyncio.Lock()):
            hit = self._data.get(key)
            if hit and time.monotonic() - hit[0] < self.ttl:
                return hit[1]
            value = await load()
            self._data[key] = (time.monotonic(), value)
            return value

    def clear(self) -> None:
        self._data.clear()
