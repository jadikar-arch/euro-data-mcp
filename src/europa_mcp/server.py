"""europa-mcp: one MCP server for official open data across Europe.

The core is country-agnostic: it loads every package in `countries/`, serves their usage guides
from `skills/` (as skill:// resources and via `country_guide`), and runs `find_data`, which
maps a topic to the best dataset or endpoint across all countries.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from importlib.resources import files
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from fastmcp.server.providers.skills import SkillsDirectoryProvider

from .common import READ_ONLY, UserError, cell, clip, fold, safe, setting
from .countries import COUNTRIES
from .sourcemap import SourceMap, merge_synonyms

log = logging.getLogger("europa_mcp")

REFRESH_HOURS = float(setting("REFRESH_HOURS", "6", legacy="CBS_INDEX_REFRESH_HOURS"))
SKILLS_DIR = Path(str(files("europa_mcp").joinpath("skills")))

SOURCES: dict[str, str] = {}  # source name → one-line scope, from every country's hints.json
for _c in COUNTRIES:
    SOURCES.update(_c.HINTS["sources"])

INSTRUCTIONS = (
    "Official open data from European countries and EU institutions.\n"
    "1. Unsure which source fits? find_data(topic) maps a topic to the best datasets/endpoints "
    "across all sources and gives the exact next call.\n"
    "2. Before using a country's tools the first time, read its guide: country_guide(code) "
    "(also served as resource skill://<code>/SKILL.md).\n"
    "Countries: " + ", ".join(f"{c.CODE} = {c.NAME}" for c in COUNTRIES) + "."
)

SOURCE_MAP: SourceMap | None = None
_map_task: asyncio.Task | None = None


def all_synonyms() -> dict[str, list[str]]:
    return merge_synonyms(
        (getattr(c, "SYNONYMS", {}) for c in COUNTRIES), (c.HINTS["synonyms"] for c in COUNTRIES)
    )


def get_map() -> SourceMap:
    global SOURCE_MAP
    if SOURCE_MAP is None:
        SOURCE_MAP = SourceMap(
            synonyms=all_synonyms(),
            builders={name: fn for c in COUNTRIES for name, fn in c.map_builders().items()},
        )
    return SOURCE_MAP


async def _map_loop() -> None:
    interval = REFRESH_HOURS * 3600
    while True:
        smap = get_map()
        if smap.count() == 0 or smap.age() >= interval:
            await smap.build()  # per-builder failures are logged and keep the old rows
        await asyncio.sleep(max(600.0, interval - smap.age()))


def ensure_map_task() -> None:
    """Start the background map refresh once per process (safe to call repeatedly)."""
    global _map_task
    if _map_task is None or _map_task.done():
        _map_task = asyncio.get_running_loop().create_task(_map_loop())


@asynccontextmanager
async def lifespan(_server: FastMCP) -> AsyncIterator[None]:
    for c in COUNTRIES:
        await c.start()
    ensure_map_task()
    try:
        yield
    finally:
        for c in COUNTRIES:
            await c.stop()


mcp = FastMCP("europa", instructions=INSTRUCTIONS, lifespan=lifespan)
for _c in COUNTRIES:
    _c.register(mcp)
mcp.add_provider(SkillsDirectoryProvider(roots=SKILLS_DIR))


# ---- core tools ---------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY, output_schema=None)
@safe
async def find_data(
    query: str, sources: list[str] | None = None, per_source: int = 3, limit: int = 12
) -> str:
    """Start here when unsure which source answers a question: maps a topic (any language) to the
    best datasets/endpoints across all countries and EU sources, with the exact next call.
    query: the topic only (e.g. 'house prices', 'pork prices', 'MEP votes'); leave out places/years."""
    smap = get_map()
    await smap.ensure()
    names = sorted({r[0] for r in smap.db.execute("SELECT DISTINCT source FROM entries")})
    wanted = None
    if sources:
        wanted = [n for n in names if any(fold(n).startswith(fold(s).strip()) for s in sources)]
        if not wanted:
            raise UserError(f"Unknown sources {sources}. Valid: {', '.join(names)}")
    ranked = smap.search(query, wanted)
    per_source, limit = max(1, min(per_source, 10)), max(1, min(limit, 40))
    best = ranked[0]["coverage"] if ranked else 0
    picked: dict[str, list[dict[str, Any]]] = {}
    for r in ranked:
        if r["coverage"] < best - 0.34 or sum(map(len, picked.values())) >= limit:
            continue  # keep only rows nearly as relevant as the best one
        rows = picked.setdefault(r["source"], [])
        if len(rows) < per_source:
            rows.append(r)
    fallback = f'# not it? dataeu_search("{query}") searches 1.9M datasets from EU and national portals'
    if not picked:
        return f"No mapped source matches '{query}'.\n{fallback}"
    out = ["id|title|topic|period|next call"]
    for source, rows in picked.items():
        out.append(f"## {source}: {SOURCES.get(source, '')}")
        for r in rows:
            topic = r["path"] if r["path"] != SOURCES.get(source) else ""
            out.append("|".join(cell(x) for x in (
                r["id"], clip(r["title"], 90), clip(topic.split(" > ", 1)[-1], 60), r["period"], r["call"],
            )))
    out.append(fallback)
    return "\n".join(out)


@mcp.tool(annotations=READ_ONLY, output_schema=None)
@safe
async def country_guide(country: str) -> str:
    """How to use one country's (or 'eu') data tools: sources, workflow, codes and pitfalls.
    Read it before the first call to that country's tools."""
    key = fold(country).strip()
    match = next((c for c in COUNTRIES if key in (c.CODE, fold(c.NAME))), None)
    path = SKILLS_DIR / (match.CODE if match else key) / "SKILL.md"
    if match is None or not path.is_file():
        return "Unknown country. Available: " + ", ".join(f"{c.CODE} ({c.NAME})" for c in COUNTRIES)
    text = path.read_text("utf-8")
    return text.split("---", 2)[2].strip() if text.startswith("---") else text  # drop frontmatter


# ---- CLI ------------------------------------------------------------------------


def main() -> None:
    logging.basicConfig(
        stream=sys.stderr, level=setting("LOG_LEVEL", "INFO", legacy="CBS_LOG_LEVEL"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    p = argparse.ArgumentParser(prog="europa-mcp", description="Official European open data MCP server")
    p.add_argument("command", nargs="?", default="serve", choices=["serve", "sync", "map"],
                   help="serve (default); sync: build the CBS index; map: build the find_data map")
    p.add_argument("--transport", default="stdio", choices=["stdio", "http"])
    p.add_argument("--host", default=setting("HOST", "127.0.0.1", legacy="CBS_HOST"))
    p.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    p.add_argument("--full", action="store_true", help="sync: rebuild the whole index")
    p.add_argument("--no-details", action="store_true", help="sync: skip measure/dimension titles")
    p.add_argument("--export", metavar="CSV", help="map: also write the source map to a CSV file")
    args = p.parse_args()

    if args.command in ("sync", "map"):
        from .countries.nl import cbs

        async def run() -> None:
            try:
                idx = cbs.get_index()
                if args.command == "sync" or not idx.count():
                    stats = await idx.sync(full=args.full, details=not args.no_details)
                    log.info("CBS index: %s (%s)", stats, idx.path)
                if args.command == "map":
                    log.info("source map: %s", await get_map().build())
                    if args.export:
                        log.info("exported %d entries to %s", get_map().export(Path(args.export)), args.export)
            finally:
                for c in COUNTRIES:
                    with suppress(Exception):
                        await c.stop()

        asyncio.run(run())
        return

    if args.transport == "http":
        from fastmcp.server.middleware.rate_limiting import RateLimitingMiddleware

        rps = float(setting("RATE_LIMIT_RPS", "5", legacy="CBS_RATE_LIMIT_RPS"))
        mcp.add_middleware(RateLimitingMiddleware(max_requests_per_second=rps, burst_capacity=20))
        mcp.run(
            transport="http", host=args.host, port=args.port, show_banner=False,
            uvicorn_config={"log_config": None},  # use our stderr logging, not stdout
        )
    else:
        mcp.run(transport="stdio", show_banner=False)


if __name__ == "__main__":
    main()
