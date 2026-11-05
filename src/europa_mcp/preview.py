"""First rows of a publisher's CSV/JSON file, for the *_preview tools (GovData, data.europa.eu).

The file URLs come from third-party catalogue metadata and the server may run hosted, so every
URL (and every redirect hop) must point at a public internet address.
"""

from __future__ import annotations

import asyncio
import csv
import io
import ipaddress
import json
import socket
from typing import Any
from urllib.parse import urlsplit

from .common import UserError, cell, clip
from .web import fetch_prefix, fetch_tail

PREVIEW_BYTES = 2_000_000
TAIL_BYTES = 64_000  # large CSVs: the end of the file too, to show the latest rows
TAIL_ROWS = 3
PREVIEWABLE = ("CSV", "TXT", "TSV", "JSON", "GEOJSON")


async def resolve(host: str) -> list[str]:
    """All IP addresses a hostname resolves to (replaced in offline tests)."""
    infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    return [i[4][0] for i in infos]


async def check_url(url: str) -> None:
    """Allow only http(s) URLs whose host resolves exclusively to public IP addresses."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https") or not host or host == "localhost":
        raise UserError(f"Can't preview '{url}'.")
    try:
        addrs = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            addrs = [ipaddress.ip_address(a) for a in await resolve(host)]
        except OSError:
            raise UserError(f"Can't reach '{host}'.") from None
    if not addrs or not all(a.is_global for a in addrs):
        raise UserError(f"Can't preview '{url}'.")


def decode(body: bytes) -> str:
    try:
        return body.decode("utf-8-sig")
    except UnicodeDecodeError:
        return body.decode("latin-1")


def sniff(text: str) -> str:
    sample = text[:20000]
    try:
        return csv.Sniffer().sniff(sample, delimiters=";,\t|").delimiter
    except csv.Error:
        return ";" if sample.count(";") > sample.count(",") else ","


def csv_rows(text: str, truncated: bool, delim: str | None = None) -> list[list[str]]:
    if truncated:
        text = text.rsplit("\n", 1)[0]  # drop the partial last line
    delim = delim or sniff(text)
    return [r for r in csv.reader(io.StringIO(text), delimiter=delim) if any(c.strip() for c in r)]


async def tail_rows(url: str, delim: str, width: int) -> list[list[str]]:
    """The last rows of a large CSV (skipping the partial first line of the fetched range)."""
    body = await fetch_tail(url, TAIL_BYTES, check=check_url)
    if not body or b"\n" not in body:
        return []
    text = decode(body).split("\n", 1)[1]
    rows = [r for r in csv_rows(text, False, delim) if len(r) >= width]
    return rows[-TAIL_ROWS:]


def json_rows(data: Any) -> list[list[str]]:
    if isinstance(data, dict):
        if isinstance(data.get("features"), list):  # GeoJSON
            data = [f.get("properties") or {} for f in data["features"] if isinstance(f, dict)]
        else:
            data = next((v for v in data.values() if isinstance(v, list)), [data])
    items = [x for x in data if isinstance(x, dict)] if isinstance(data, list) else []
    if not items:
        raise UserError("JSON has no list of records to preview.")
    keys = list(dict.fromkeys(k for x in items[:50] for k in x))
    flat = lambda v: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else ("" if v is None else str(v))  # noqa: E731
    return [keys] + [[flat(x.get(k)) for k in keys] for x in items]


def file_kind(fmt: str, url: str) -> str:
    """'CSV', 'JSON', … from the catalogue format, else from the URL's extension."""
    fmt = fmt.strip().upper()
    return fmt if fmt in PREVIEWABLE else urlsplit(url).path.rsplit(".", 1)[-1].upper()


async def preview(label: str, url: str, fmt: str, limit: int) -> list[str]:
    """Header + first rows of a CSV/JSON file as compact lines (raises UserError otherwise)."""
    kind = file_kind(fmt, url)
    if kind not in PREVIEWABLE:
        raise UserError(f"{label} is {fmt or 'an unknown format'}; only CSV/JSON can be previewed. Download: {url}")
    body, truncated, ctype = await fetch_prefix(url, PREVIEW_BYTES, check=check_url)
    if "html" in ctype and not body.lstrip().startswith((b"{", b"[")):
        raise UserError(f"{label} is a web page, not data. Open: {url}")
    text = decode(body)
    if kind in ("JSON", "GEOJSON"):
        if truncated:
            raise UserError(f"JSON file is larger than {PREVIEW_BYTES // 1_000_000} MB; download it: {url}")
        try:
            rows = json_rows(json.loads(text))
        except ValueError:
            raise UserError("File is not valid JSON.") from None
    else:
        rows = csv_rows(text, truncated, delim := sniff(text))
    if len(rows) < 2:
        raise UserError(f"{label} has no rows to preview. Download: {url}")
    limit = max(1, min(limit, 50))
    header, data = rows[0], rows[1:]
    width = min(len(header), 15)
    out = [f"{label}: {kind}, {len(header)} columns" + (f" (first {width} shown)" if width < len(header) else "")]
    out.append("|".join(cell(clip(h, 40)) for h in header[:width]))
    out += ["|".join(cell(clip(c, 40)) for c in row[:width]) for row in data[:limit]]
    more = "first part of a large file" if truncated else f"{len(data)} rows"
    out.append(f"# showing {min(limit, len(data))} of {more}")
    if truncated and kind not in ("JSON", "GEOJSON"):
        if last := await tail_rows(url, delim, len(header)):
            out.append("# last rows of the file:")
            out += ["|".join(cell(clip(c, 40)) for c in row[:width]) for row in last]
    return out
