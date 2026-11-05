"""Shared async HTTP for the EU APIs: absolute URLs, retry on 429/5xx, short error messages."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlsplit

import httpx

from .common import NotFound, UserError

RETRY_STATUS = {429, 500, 502, 503, 504}
ATTEMPTS = 3

_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=15.0),
            headers={"User-Agent": "europa-mcp"},
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
    """GET with retry; raises NotFound on 404 and UserError on other failures."""
    host = urlsplit(url).netloc
    client = get_client()
    kwargs: dict[str, Any] = {"params": params, "headers": headers}
    if timeout:
        kwargs["timeout"] = timeout
    for attempt in range(ATTEMPTS):
        try:
            resp = await client.get(url, **kwargs)
        except httpx.TimeoutException:
            raise UserError(f"{host} timed out; narrow the request.") from None
        except httpx.TransportError as e:
            if attempt == ATTEMPTS - 1:
                raise UserError(f"{host} unreachable: {type(e).__name__}") from None
        else:
            if resp.status_code == 404:
                raise NotFound(_message(resp))
            if resp.status_code < 400:
                return resp
            if resp.status_code not in RETRY_STATUS:
                raise UserError(f"{host} error {resp.status_code}: {_message(resp)}")
            if attempt == ATTEMPTS - 1:
                raise UserError(f"{host} error {resp.status_code} after {ATTEMPTS} attempts")
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
        raise UserError(f"{urlsplit(url).netloc} returned non-JSON ({resp.headers.get('content-type')})") from None


MAX_REDIRECTS = 5


async def fetch_prefix(
    url: str,
    max_bytes: int,
    check: Callable[[str], Awaitable[None]] | None = None,
) -> tuple[bytes, bool, str]:
    """The first `max_bytes` of a file (no retries): (body, truncated, content type).
    `check(url)` vets the URL and every redirect target before it is requested."""
    body, truncated, ctype, _ = await _stream(url, max_bytes, check)
    return body, truncated, ctype


TAIL_SCAN_MAX = 25_000_000  # servers without range support: read at most this much to reach the end


async def fetch_tail(
    url: str,
    max_bytes: int,
    check: Callable[[str], Awaitable[None]] | None = None,
) -> bytes | None:
    """The last `max_bytes` of a file: an HTTP range request, or (when the server ignores ranges)
    reading through files up to TAIL_SCAN_MAX. None when that fails or the file is bigger."""
    try:
        body, too_big, _, _ = await _stream(url, max_bytes, check, {"Range": f"bytes=-{max_bytes}"}, tail=True)
    except UserError:
        return None
    return None if too_big else body


async def _stream(
    url: str,
    max_bytes: int,
    check: Callable[[str], Awaitable[None]] | None,
    headers: dict[str, str] | None = None,
    tail: bool = False,
) -> tuple[bytes, bool, str, int]:
    """GET with vetted redirects. Head mode: the first max_bytes and whether there was more.
    Tail mode: the last max_bytes and whether the file exceeded TAIL_SCAN_MAX."""
    host = urlsplit(url).netloc
    try:
        for _ in range(MAX_REDIRECTS + 1):
            if check:
                await check(url)
            req = get_client().build_request("GET", url, headers=headers)
            resp = await get_client().send(req, stream=True, follow_redirects=False)
            if not resp.is_redirect:
                break
            await resp.aclose()
            url = str(resp.next_request.url) if resp.next_request else url
            host = urlsplit(url).netloc
        else:
            raise UserError(f"{host}: too many redirects")
        try:
            if resp.status_code == 404:
                raise NotFound(f"{host}: file not found")
            if resp.status_code >= 400:
                raise UserError(f"{host} error {resp.status_code}")
            ctype = resp.headers.get("content-type", "")
            body, seen = b"", 0
            async for chunk in resp.aiter_bytes():
                if tail:
                    seen += len(chunk)
                    if seen > TAIL_SCAN_MAX:
                        return b"", True, ctype, resp.status_code
                    body = (body + chunk)[-max_bytes:]
                    continue
                body += chunk
                if len(body) > max_bytes:
                    return body[:max_bytes], True, ctype, resp.status_code
            return body, False, ctype, resp.status_code
        finally:
            await resp.aclose()
    except httpx.TimeoutException:
        raise UserError(f"{host} timed out.") from None
    except httpx.TransportError as e:
        raise UserError(f"{host} unreachable: {type(e).__name__}") from None


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
