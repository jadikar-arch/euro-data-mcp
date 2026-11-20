"""europa-mcp: one MCP server for open data across Europe.

The core is country-agnostic: it loads every package in `countries/`, serves their usage guides
from `skills/` (as skill:// resources and via `country_guide`), and runs `find_data`, which
maps a topic to the best dataset or endpoint across all countries.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from importlib.resources import files
from pathlib import Path
from typing import Any

import mcp.types as mcp_types
from fastmcp import Context, FastMCP
from fastmcp.server.providers.skills import SkillsDirectoryProvider

from .common import READ_ONLY, UserError, cell, clip, countries_in, fold, safe, setting
from .countries import COUNTRIES
from .sourcemap import SourceMap, merge_synonyms

log = logging.getLogger("europa_mcp")

REFRESH_HOURS = float(setting("REFRESH_HOURS", "6"))
SKILLS_DIR = Path(str(files("europa_mcp").joinpath("skills")))

SOURCES: dict[str, str] = {}  # source name → one-line scope, from every country's hints.json
for _c in COUNTRIES:
    SOURCES.update(_c.HINTS["sources"])

INSTRUCTIONS = (
    "Open data from European countries and EU institutions.\n"
    "1. Start with find_data(topic) unless you already know the dataset id: it ranks the best "
    "datasets/endpoints across all sources, with the exact next call. The user chooses: in apps that "
    "support it they pick from the list themselves; otherwise show them the ranked list (rank, title, "
    "period, breakdowns) and wait for their choice before fetching data, unless they already named one. "
    "If the question names no country and the matches come from several, offer the countries as options "
    "(or an EU-wide comparison) and ask which one they want.\n"
    "2. Before using a country's tools the first time, read its guide: country_guide(code) "
    "(also served as resource skill://<code>/SKILL.md).\n"
    "3. Every data answer ends with a 'source:' line (link + licence); pass it on to the user.\n"
    "4. Before answering, check that the fetched data answers the question: the dataset title and the "
    "'fixed:' line (unit, age, sex, geo…). If it doesn't (wrong unit, national when regions were asked, "
    "an old period), try the next find_data candidate, or tell the user what the data does cover.\n"
    "5. When the user asks what is covered, or names a country, call country_guide() without an argument: "
    "it lists every country, its sources and what else is available through Eurostat.\n"
    "Countries: " + ", ".join(f"{c.CODE} = {c.NAME}" for c in COUNTRIES) + ".\n"
    "europa-mcp is an independent project, not affiliated with or endorsed by the EU or any "
    "statistics office; the data comes unchanged from their public APIs."
)

SOURCE_MAP: SourceMap | None = None
_map_task: asyncio.Task | None = None


def all_synonyms() -> dict[str, list[str]]:
    return merge_synonyms((getattr(c, "SYNONYMS", {}) for c in COUNTRIES), (c.HINTS["synonyms"] for c in COUNTRIES))


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


NONE_OF_THESE = "None of these"
PICK = "dataset"  # key of the input request that asks the user to pick
CLOSED = "closed"  # the user dismissed the picker
CLOSED_NOTE = "# The user closed the picker without choosing; ask them in the chat which dataset to use."
ASK_USER_NOTE = (
    "# Show the user these options (rank, title, period, breakdowns) and let them choose before "
    "fetching data, unless they already named a dataset."
)


def ranked_matches(query: str, sources: list[str] | None, per_source: int, limit: int) -> list[dict[str, Any]]:
    """Best map entries, best first: only rows nearly as relevant as the top one, at most
    `per_source` per source so one source can't crowd out the others."""
    smap = get_map()
    names = sorted({r[0] for r in smap.db.execute("SELECT DISTINCT source FROM entries")})
    wanted = None
    if sources:
        wanted = [n for n in names if any(fold(n).startswith(fold(s).strip()) for s in sources)]
        if not wanted:
            raise UserError(f"Unknown sources {sources}. Valid: {', '.join(names)}")
    ranked = smap.search(query, wanted)
    best = ranked[0]["coverage"] if ranked else 0
    picked, per = [], {}
    for r in ranked:
        if r["coverage"] < best - 0.34 or len(picked) >= limit:
            continue
        if per.get(r["source"], 0) < per_source:
            per[r["source"]] = per.get(r["source"], 0) + 1
            picked.append(r)
    return picked


def country_of(source: str) -> str:
    """The country package a source belongs to, as a name ('EU' for the EU-level sources)."""
    c = next((c for c in COUNTRIES if source in c.HINTS["sources"]), None)
    return "" if c is None else ("EU" if c.CODE == "eu" else c.NAME)


def country_choice_note(query: str, rows: list[dict[str, Any]]) -> list[str]:
    """No country in the question but matches from several countries: tell the agent to offer the choice."""
    if countries_in(query):
        return []
    found: dict[str, list[str]] = {}
    for r in rows:
        found.setdefault(country_of(r["source"]), [])
        if r["source"] not in found[country_of(r["source"])]:
            found[country_of(r["source"])].append(r["source"])
    found.pop("", None)
    if len(found) < 2:
        return []
    parts = [
        f"{'EU/EEA, comparable across countries' if name == 'EU' else name} ({', '.join(srcs)})"
        for name, srcs in found.items()
    ]
    return [
        "# No country named. Matches exist for: " + "; ".join(parts) + ". Offer the user these options "
        "(a country, or an EU-wide comparison) and ask which they want before fetching data."
    ]


def national_codes() -> dict[str, Any]:
    """Eurostat geo code → country package, for the countries that have a national source."""
    return {c.CODE.upper(): c for c in COUNTRIES if c.CODE != "eu"}


def national_first(rows: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    """When the question names a country with its own source, that country's rows come first
    (stable, so the order inside each group is unchanged)."""
    own = national_codes()
    mine = {s for g in countries_in(query) if g in own for s in own[g].HINTS["sources"]}
    return sorted(rows, key=lambda r: r["source"] not in mine) if mine else rows


def coverage_notes(query: str) -> list[str]:
    """Tell the user what covers a country they named: its national source, or only Eurostat."""
    own = national_codes()
    out = []
    for geo in countries_in(query):
        if geo in own:
            c = own[geo]
            out.append(f"# {c.NAME}: national source {', '.join(c.HINTS['sources'])}; guide: country_guide('{c.CODE}')")
        else:
            have = ", ".join(f"{c.NAME} ({c.CODE})" for c in own.values())
            out.append(
                f"# No national source for geo={geo} yet (national sources: {have}). Eurostat covers it: "
                f"eurostat_data(<dataset>, filters={{'geo': ['{geo}']}}); country portals: dataeu_search(query, country='{geo}'). "
                "country_guide() lists coverage."
            )
    return out


def match_table(query: str, rows: list[dict[str, Any]]) -> list[str]:
    out = [
        f"Ranked matches for '{query}' (best first; match = share of the question's words found).",
        "rank|match|source|id|title|period|breakdowns|next call",
    ]
    for n, r in enumerate(rows, 1):
        out.append(
            "|".join(
                cell(x)
                for x in (
                    n,
                    f"{round(r['coverage'] * 100)}%",
                    r["source"],
                    r["id"],
                    clip(r["title"], 90),
                    r["period"],
                    clip(r.get("detail") or "", 60),
                    r["call"],
                )
            )
        )
    shown = dict.fromkeys(r["source"] for r in rows)
    out.append("# sources: " + "; ".join(f"{s} = {SOURCES[s]}" for s in shown if SOURCES.get(s)))
    return out


def option_label(n: int, r: dict[str, Any]) -> str:
    facts = "; ".join(
        x
        for x in (
            f"{country_of(r['source'])} · {r['source']} {r['id']}".removeprefix(" · "),
            r["period"],
            f"by {r['detail']}" if r.get("detail") else "",
        )
        if x
    )
    return f"{n}. {clip(r['title'], 90)} ({facts})"


def modern_protocol(ctx: Context) -> bool:
    """2026-07-28 connections: no asking mid-call; the tool returns input_required instead."""
    try:
        return bool(ctx._is_modern_protocol())  # FastMCP has no public accessor yet
    except Exception:  # noqa: BLE001
        return False


def can_elicit(ctx: Context | None) -> bool:
    """Does the connected app support elicitation (asking the user from the server)?"""
    try:
        caps = ctx.session.client_params.capabilities if ctx else None
    except Exception:  # noqa: BLE001 - no session (e.g. called outside a request)
        return False
    return getattr(caps, "elicitation", None) is not None


def chosen(choice: str, query: str, rows: list[dict[str, Any]]) -> str | None:
    """The user's pick as the tool answer (None when the choice can't be read)."""
    if choice == NONE_OF_THESE:
        return (
            f"The user said none of the {len(rows)} matches for '{query}' fit. Ask what they need, "
            f'or search more widely: dataeu_search("{query}").'
        )
    head = choice.split(".", 1)[0]
    n = int(head) if head.isdigit() else 0
    if not 1 <= n <= len(rows):
        return None
    r = rows[n - 1]
    facts = "; ".join(x for x in (r.get("period"), f"breakdowns: {r['detail']}" if r.get("detail") else "") if x)
    return (
        f'The user chose rank {n} of {len(rows)}: {r["source"]} {r["id"]} "{r["title"]}"'
        + (f" ({facts})" if facts else "")
        + f".\nNext call: {r['call']}"
    )


def pick_question(query: str) -> str:
    return f"Which dataset should be used for '{query}'? Best matches first."


async def ask_user_to_choose(ctx: Context, query: str, rows: list[dict[str, Any]]) -> str | None:
    """Older protocol: ask in the middle of the call. None: the user didn't answer."""
    options = [option_label(n, r) for n, r in enumerate(rows, 1)] + [NONE_OF_THESE]
    try:
        res = await ctx.elicit(pick_question(query), options, response_title="Dataset")
    except Exception as e:  # noqa: BLE001 - the client refused or failed; fall back to the list
        log.info("elicitation failed: %s", e)
        return None
    if getattr(res, "action", "") != "accept":
        return None
    return chosen(str(getattr(res, "data", "")), query, rows)


def input_required(query: str, rows: list[dict[str, Any]]) -> mcp_types.InputRequiredResult:
    """2026-07-28 protocol: end this call with a question; the app asks the user and calls again."""
    options = [option_label(n, r) for n, r in enumerate(rows, 1)] + [NONE_OF_THESE]
    schema = {
        "type": "object",
        "required": ["value"],
        "properties": {"value": {"type": "string", "title": "Dataset", "enum": options}},
    }
    keep = ("source", "id", "title", "period", "detail", "call")
    return mcp_types.InputRequiredResult(
        input_requests={
            PICK: mcp_types.ElicitRequest(
                params=mcp_types.ElicitRequestFormParams(message=pick_question(query), requested_schema=schema)
            )
        },
        request_state=json.dumps([{k: r.get(k) or "" for k in keep} for r in rows]),
    )


def answered(ctx: Context | None, query: str) -> str | None:
    """2026-07-28 protocol, second round: the user's answer to input_required, if there is one."""
    try:
        responses = ctx.input_responses if ctx else None
    except Exception:  # noqa: BLE001
        return None
    if not responses or PICK not in responses:
        return None
    rows = json.loads(ctx.request_state or "[]")
    res = responses[PICK]
    if getattr(res, "action", "") != "accept" or not rows:
        return CLOSED
    return chosen(str((getattr(res, "content", None) or {}).get("value", "")), query, rows)


@mcp.tool(annotations=READ_ONLY, output_schema=None)
@safe
async def find_data(
    query: str,
    sources: list[str] | None = None,
    per_source: int = 4,
    limit: int = 10,
    ask_user: bool = True,
    ctx: Context | None = None,
) -> str:
    """Start here: ranks the best datasets/endpoints for a topic (any language) across all sources, with the
    next call. ask_user: let the user pick in the app when it supports it; else show the ranked list and ask.
    query: the topic only (e.g. 'house prices', 'pork prices', 'MEP votes'); leave out places/years."""
    reply = answered(ctx, query) if ask_user else None
    if reply is not None and reply != CLOSED:
        return reply
    await get_map().ensure()
    rows = ranked_matches(query, sources, max(1, min(per_source, 10)), max(1, min(limit, 20)))
    rows = national_first(rows, query)
    notes = [*coverage_notes(query), *country_choice_note(query, rows)]
    fallback = f'# not it? dataeu_search("{query}") searches 1.9M datasets from EU and national portals'
    if not rows:
        return "\n".join([f"No mapped source matches '{query}'.", *notes, fallback])
    if reply == CLOSED:
        return "\n".join([*match_table(query, rows), *notes, CLOSED_NOTE, fallback])
    if ask_user and len(rows) > 1 and can_elicit(ctx):
        if modern_protocol(ctx):
            return input_required(query, rows)
        if (pick := await ask_user_to_choose(ctx, query, rows)) is not None:
            return pick
    return "\n".join([*match_table(query, rows), *notes, *([ASK_USER_NOTE] if len(rows) > 1 else []), fallback])


def coverage_overview() -> str:
    smap = get_map()
    out = ["code|country|sources (rows in the find_data map)|guide"]
    for c in COUNTRIES:
        sources = "; ".join(f"{n} = {d} ({smap.count(n)})" for n, d in c.HINTS["sources"].items())
        out.append("|".join(cell(x) for x in (c.CODE, c.NAME, sources, f"country_guide('{c.CODE}')")))
    out.append(
        "# Every other EU/EEA country: harmonised Eurostat data (eu, filter geo=<code>) and the datasets of "
        "national portals through dataeu_search(query, country='<iso2>'). New national sources are added over time."
    )
    return "\n".join(out)


@mcp.tool(annotations=READ_ONLY, output_schema=None)
@safe
async def country_guide(country: str = "") -> str:
    """How to use one country's (or 'eu') data tools: sources, workflow, codes and pitfalls.
    Read it before the first call to that country's tools. No argument: list what is covered; 'overview': start here."""
    key = fold(country).strip()
    if not key:
        return coverage_overview()
    match = next((c for c in COUNTRIES if key in (c.CODE, fold(c.NAME))), None)
    path = SKILLS_DIR / (match.CODE if match else key) / "SKILL.md"
    if key == "overview":  # the index skill, for clients that cannot read skill:// resources
        path, match = SKILLS_DIR / "overview" / "SKILL.md", True
    if match is None or not path.is_file():
        return (
            "No guide for that country yet. Available: "
            + ", ".join(f"{c.CODE} ({c.NAME})" for c in COUNTRIES)
            + ". Eurostat (eu) covers every EU country; national portals' datasets are in "
            'dataeu_search(query, country="<iso2>").'
        )
    text = path.read_text("utf-8")
    return text.split("---", 2)[2].strip() if text.startswith("---") else text  # drop frontmatter


# ---- CLI ------------------------------------------------------------------------


def client_id(context: Any) -> str:
    """Rate-limit key for HTTP: the caller's IP (first X-Forwarded-For hop behind a proxy)."""
    try:
        from fastmcp.server.dependencies import get_http_request

        req = get_http_request()
    except Exception:  # noqa: BLE001 - not an HTTP request
        return "local"
    fwd = req.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() or (req.client.host if req.client else "unknown")


def main() -> None:
    logging.basicConfig(
        stream=sys.stderr,
        level=setting("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    p = argparse.ArgumentParser(prog="europa-mcp", description="European open data MCP server")
    p.add_argument(
        "command",
        nargs="?",
        default="serve",
        choices=["serve", "map", "usage"],
        help="serve (default); map: build the find_data map; usage: summarise the usage log",
    )
    p.add_argument("--transport", default="stdio", choices=["stdio", "http"])
    p.add_argument("--host", default=setting("HOST", "127.0.0.1"))
    p.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    p.add_argument("--export", metavar="CSV", help="map: also write the source map to a CSV file")
    p.add_argument("--log", metavar="JSONL", help="usage: log file (default: $EUROPA_USAGE_LOG)")
    args = p.parse_args()

    if args.command == "usage":
        from .usage import report

        path = args.log or setting("USAGE_LOG")
        if not path:
            p.error("usage: pass --log FILE or set EUROPA_USAGE_LOG")
        print(report(Path(path)))
        return

    if args.command == "map":

        async def run() -> None:
            try:
                log.info("source map: %s", await get_map().build())
                if args.export:
                    log.info("exported %d entries to %s", get_map().export(Path(args.export)), args.export)
            finally:
                for c in COUNTRIES:
                    with suppress(Exception):
                        await c.stop()

        asyncio.run(run())
        return

    if usage_log := setting("USAGE_LOG"):
        from .usage import UsageLog

        mcp.add_middleware(UsageLog(Path(usage_log)))
        log.info("usage log: %s", usage_log)

    if args.transport == "http":
        from fastmcp.server.middleware.rate_limiting import RateLimitingMiddleware

        rps = float(setting("RATE_LIMIT_RPS", "5"))
        mcp.add_middleware(
            RateLimitingMiddleware(
                max_requests_per_second=rps,
                burst_capacity=20,
                get_client_id=client_id,
            )
        )
        if keys := [k.strip() for k in setting("API_KEYS").split(",") if k.strip()]:
            from fastmcp.server.auth.providers.jwt import StaticTokenVerifier

            mcp.auth = StaticTokenVerifier({k: {"client_id": f"key{i}", "scopes": []} for i, k in enumerate(keys)})
            log.info("API key required (%d keys configured)", len(keys))
        mcp.run(
            transport="http",
            host=args.host,
            port=args.port,
            show_banner=False,
            uvicorn_config={"log_config": None},  # use our stderr logging, not stdout
        )
    else:
        mcp.run(transport="stdio", show_banner=False)


if __name__ == "__main__":
    main()
