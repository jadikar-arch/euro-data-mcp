"""PxWeb v1: the statistics API used by Sweden, Finland, Estonia, Latvia and many other offices.

One `PxSource` describes a national database; `register(mcp, src)` adds its four tools
`<prefix>_search`, `_describe`, `_codes` and `_data`, and `map_entries(src)` gives its find_data rows.

How PxWeb works (probed 2026-11): GET `<base>/<folder>/…` lists folders (`type` l) and tables (`t`);
GET on a table gives its variables (code, text, values, valueTexts, `elimination`, `time`); POST
`{"query": [{"code", "selection": {"filter": "item|top|all", "values": [...]}}], "response": {"format":
"json"}}` returns `columns` (d/t = dimensions, c = measures) and `data` rows `{key, values}`.
A variable with `elimination` may be left out (the server then uses its default, normally the total);
any other variable must be selected. Servers limit calls per second (Statistics Sweden: 10 per 10 s),
so every request of a source goes through one throttle.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

from fastmcp import FastMCP

from .common import (
    READ_ONLY,
    STOPWORDS,
    UserError,
    as_list,
    cache_dir,
    cell,
    compact_table,
    fold,
    safe,
    source_line,
)
from .sourcemap import HEADLINE_END, HEADLINE_MARK, Entry
from .web import Memo, fetch_json

log = logging.getLogger("europa_mcp")

CATALOG_TTL = 24 * 3600
CATALOG = Memo(ttl=CATALOG_TTL)
META = Memo(ttl=6 * 3600)
CATALOG_WAIT = 45.0  # seconds a tool waits for a catalogue that is still being loaded
RATE_LIMIT_PAUSE = 61.0  # seconds every request of a source waits after the server answered 429
MAX_CELLS = 20_000  # refuse queries above this many values before asking the server
WALK_CONCURRENCY = 4
MAX_DEFAULT_MEASURES = 6  # a table with more measures than this needs a choice, not a dump of all of them
MISSING = {"", ".", "..", "...", "-", "--", ":", "x", "xx"}  # PxWeb symbols for 'no value' (compared in lower case)
PERIOD = re.compile(r"(\d{4}(?:[A-Za-z]\d{1,2})?)\s*[-–]\s*(\d{4}(?:[A-Za-z]\d{1,2})?)\s*\.?\s*$")
TRANSIENT = re.compile(r"error (?:429|5\d\d)|unreachable|timed out|limiting requests")


def never(_: str) -> bool:
    return False


def no_note(_: str) -> str:
    return ""


@dataclass(frozen=True)
class PxSource:
    prefix: str  # tool prefix: scb → scb_search, scb_data …
    name: str  # source name in find_data: "SCB"
    agency: str  # "Statistics Sweden"
    country: str  # "Sweden"
    local: str  # local language: "Swedish"
    base: str  # API root with language and database, no trailing slash
    licence: str  # as printed in the `source:` line
    page: Callable[[str], str]  # table id → the table's page on the agency's website
    synonyms: dict[str, tuple[str, ...]] = field(default_factory=dict)  # English → local terms
    aliases: dict[str, str] = field(default_factory=dict)  # place names whose labels differ ('gothenburg' → 'goteborg')
    min_interval: float = 0.2  # seconds between requests to this server
    per_minute: int = 0  # at most this many requests in any 60 seconds (0 = no cap)
    listing: bool = False  # GET <base>?query=*&filter=* lists every table in one request
    archive: Callable[[str], bool] = never  # table id → it sits in an archive of discontinued tables
    note: Callable[[str], str] = no_note  # table id → a caveat printed with its data (e.g. Sweden's CKM rounding)


# ---- requests ---------------------------------------------------------------------------


class Throttle:
    """Spaces the requests of one source: at least `interval` seconds apart, at most `per_minute` in any
    60 seconds, and none while a 429 pause is running."""

    def __init__(self, interval: float, per_minute: int = 0):
        self.interval = interval
        self.per_minute = per_minute
        self._lock = asyncio.Lock()
        self._next = 0.0
        self._blocked = 0.0
        self._sent: deque[float] = deque()

    def block(self, seconds: float) -> None:
        self._blocked = max(self._blocked, time.monotonic() + seconds)

    async def wait(self) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                while self._sent and now - self._sent[0] >= 60:
                    self._sent.popleft()
                delay = max(self._next - now, self._blocked - now)
                if self.per_minute and len(self._sent) >= self.per_minute:
                    delay = max(delay, self._sent[0] + 60 - now)
                if delay <= 0:
                    break
                await asyncio.sleep(delay)
            self._sent.append(now)
            self._next = now + self.interval


_throttles: dict[tuple[str, int], Throttle] = {}


async def call(src: PxSource, path: str = "", body: Any = None, params: Any = None, patient: bool = False) -> Any:
    """GET (or POST with a query body) one path of the source's API, throttled. A 429 pauses every request of
    the source; `patient` calls (the catalogue walk) then try again, interactive ones tell the user."""
    key = (src.prefix, id(asyncio.get_running_loop()))
    throttle = _throttles.setdefault(key, Throttle(src.min_interval, src.per_minute))
    url = src.base + ("/" + quote(path, safe="/.:_-") if path else "")
    for attempt in range(3 if patient else 1):
        await throttle.wait()
        try:
            return await fetch_json(url, params, json=body, timeout=90)
        except UserError as e:
            if "429" not in str(e):
                raise
            throttle.block(RATE_LIMIT_PAUSE)
            if attempt == (2 if patient else 0):
                raise UserError(f"{src.agency} is limiting requests (HTTP 429). Try again in a minute.") from None
    raise AssertionError("unreachable")


# ---- catalogue --------------------------------------------------------------------------


def finish(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Add the search text ('hay') and the shortest unambiguous table id ('short': the last path
    segment when no other table has it, else the full path)."""
    tails: dict[str, int] = {}
    for r in rows:
        tail = r["id"].lower().rsplit("/", 1)[-1]
        tails[tail] = tails.get(tail, 0) + 1
    for r in rows:
        tail = r["id"].rsplit("/", 1)[-1]
        r["short"] = tail if tails[tail.lower()] == 1 else r["id"]
        r["hay"] = fold(f"{r['title']} {r['path']} {r['id']}")
    return rows


KEYS = ("id", "title", "path", "updated", "archived")
INCOMPLETE: dict[str, int] = {}  # source prefix → folders that could not be listed (transient errors)


def read_cache(src: PxSource, max_age: float = CATALOG_TTL) -> list[dict[str, str]] | None:
    """The catalogue saved by an earlier run (so a restart does not list or walk everything again)."""
    path = cache_dir() / f"pxweb-{src.prefix}.json"
    try:
        if time.time() - path.stat().st_mtime > max_age:
            return None
        rows = json.loads(path.read_text("utf-8"))
        return finish([{k: r[k] for k in KEYS} for r in rows]) or None
    except (OSError, ValueError, KeyError, TypeError):
        return None


def write_cache(src: PxSource, rows: list[dict[str, str]]) -> None:
    try:
        path = cache_dir() / f"pxweb-{src.prefix}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps([{k: r[k] for k in KEYS} for r in rows], ensure_ascii=False), "utf-8")
        tmp.replace(path)
    except OSError as e:  # a read-only cache directory only costs a second load later
        log.info("%s: catalogue not cached: %s", src.name, e)


def row(src: PxSource, tid: str, title: str, path: str, updated: str) -> dict[str, str]:
    return {
        "id": tid,
        "title": title,
        "path": path,
        "updated": updated[:10],
        "archived": "1" if src.archive(tid) else "",
    }


async def list_all(src: PxSource) -> list[dict[str, str]] | None:
    """Every table from the server's search endpoint in one request (None when it does not offer one).
    It gives folder codes, not folder names, so rows have no topic path."""
    try:
        data = await call(src, "", params={"query": "*", "filter": "*"}, patient=True)
    except UserError as e:
        log.info("%s: no one-request listing (%s); walking the folders", src.name, e)
        return None
    if not isinstance(data, list) or len(data) < 20:
        return None
    rows = []
    for it in data:
        if isinstance(it, dict) and it.get("id") and it.get("title"):
            tid = f"{(it.get('path') or '').strip('/')}/{it['id']}".strip("/")
            rows.append(row(src, tid, str(it["title"]).strip(), "", str(it.get("published") or "")))
    return rows or None


async def walk_folders(src: PxSource) -> list[dict[str, str]]:
    """Every table by walking the folder tree. A folder the server refuses for good (HTTP 400) is skipped;
    folders that failed for transient reasons (rate limit, timeout) are tried again, and when some still fail
    the catalogue is marked incomplete (and not saved)."""
    tables: dict[str, dict[str, str]] = {}
    failed: dict[str, tuple[list[str], str]] = {}
    sem = asyncio.Semaphore(WALK_CONCURRENCY)

    async def walk(path: str, trail: list[str]) -> None:
        async with sem:
            try:
                nodes = await call(src, path, patient=True)
            except UserError as e:
                failed[path] = (trail, str(e))
                return
        subs = []
        for n in nodes if isinstance(nodes, list) else []:
            if not n.get("id"):
                continue
            nid, text = f"{path}/{n['id']}" if path else n["id"], (n.get("text") or n["id"]).strip()
            if n.get("type") == "t":
                tables[nid] = row(src, nid, text, " > ".join(trail), n.get("updated") or "")
            elif n.get("type") == "l":
                subs.append((nid, [*trail, text]))
        await asyncio.gather(*(walk(p, t) for p, t in subs))

    await walk("", [])
    for path, (trail, _) in [(p, v) for p, v in failed.items() if TRANSIENT.search(v[1])]:  # one more try
        del failed[path]
        await walk(path, trail)
    transient = [p for p, (_, msg) in failed.items() if TRANSIENT.search(msg)]
    INCOMPLETE[src.prefix] = len(transient)
    if failed:
        log.info(
            "%s: %d folders skipped: %s", src.name, len(failed), [f"{p}: {m}" for p, (_, m) in list(failed.items())[:3]]
        )
    return list(tables.values())


async def walk_catalog(src: PxSource) -> list[dict[str, str]]:
    """Every table as {id, title, path, updated, archived, short, hay}: from the saved copy of an earlier run,
    else the server's one-request listing, else a walk of its folders."""

    async def load():
        if (saved := read_cache(src)) is not None:
            return saved
        rows = (await list_all(src)) if src.listing else None
        complete = rows is not None
        if rows is None:
            rows = await walk_folders(src)
            complete = not INCOMPLETE.get(src.prefix)
        if not rows:
            if (stale := read_cache(src, max_age=float("inf"))) is not None:
                log.warning("%s: no catalogue from the server, using the saved one", src.name)
                return stale
            raise UserError(f"{src.agency} catalogue returned no tables; try again later.")
        rows = finish(sorted(rows, key=lambda t: t["id"]))
        if complete:  # a catalogue that lost folders is used now but never saved for a day
            write_cache(src, rows)
        return rows

    return await CATALOG.get(src.prefix, load)


_loading: dict[tuple[str, int], asyncio.Task] = {}


async def catalog(src: PxSource, wait: float | None = CATALOG_WAIT) -> list[dict[str, str]]:
    """The catalogue, loading it in the background when needed. Tools wait `wait` seconds and then say it
    is still loading (the first walk of a slow office takes minutes); the map builder waits for as long as it takes."""
    key = (src.prefix, id(asyncio.get_running_loop()))
    task = _loading.get(key)
    # A tool call must not wait minutes because yesterday's copy expired: answer from the saved copy
    # (table lists change slowly) while the refresh runs in the background.
    stale = None
    if wait is not None and not CATALOG.fresh(src.prefix) and read_cache(src) is None:
        stale = read_cache(src, max_age=float("inf"))
    if task is None:
        task = asyncio.ensure_future(walk_catalog(src))
        _loading[key] = task

        def done(t: asyncio.Task) -> None:
            _loading.pop(key, None)
            if not t.cancelled():
                t.exception()  # mark retrieved: callers that gave up must not leave a warning behind

        task.add_done_callback(done)
    if stale is not None:
        return stale
    try:
        return await asyncio.wait_for(asyncio.shield(task), wait)
    except TimeoutError:
        raise UserError(
            f"{src.agency}'s table list is still loading (the first start takes a few minutes). Try again in a minute."
        ) from None


def period_of(title: str) -> str:
    """'Population 1968 - 2024' → '1968–2024' (best effort; '' when the title has no range)."""
    m = PERIOD.search(title)
    return f"{m.group(1)}–{m.group(2)}" if m else ""


async def map_entries(src: PxSource, headline: dict[str, str] | None = None) -> list[Entry]:
    """find_data rows: one per current table (archives of discontinued tables stay out); `headline`
    marks the most-asked ones."""
    headline = headline or {}
    return [
        {
            "source": src.name,
            "id": t["id"],
            "title": t["title"],
            "path": f"{src.name} > {t['path']}" if t["path"] else src.name,
            "keywords": f"{HEADLINE_MARK} {words} {HEADLINE_END}"
            if (words := headline.get(t["id"]) or headline.get(t["short"]))
            else "",
            "period": period_of(t["title"]),
            "updated": t["updated"],
            "call": f'{src.prefix}_describe("{t["id"]}")',
        }
        for t in await catalog(src, wait=None)
        if not t["archived"]
    ]


def stem(path: str) -> str:
    """'rahvastik/…/RV0240.PX' → 'rv0240' (last segment, lower case, no .px extension)."""
    return re.sub(r"\.px$", "", path.rsplit("/", 1)[-1].lower())


async def resolve(src: PxSource, table_id: str) -> dict[str, str]:
    """The catalogue row of a table id: the full path, or its last segment alone when that is
    unambiguous; case and a trailing '.px' do not matter."""
    tid = (table_id or "").strip().strip("/")
    if not tid:
        raise UserError(f"table_id is required. Use {src.prefix}_search or find_data to find one.")
    rows = await catalog(src)
    hit = next((r for r in rows if r["id"].lower() == tid.lower()), None)
    if hit is None:
        same = [
            r
            for r in rows
            if stem(r["id"]) == stem(tid) and ("/" not in tid or r["id"].lower().startswith(tid.lower()))
        ]
        if len(same) > 1:
            raise UserError(
                f"'{table_id}' is in several folders: " + ", ".join(r["id"] for r in same[:4]) + ". Use the full path."
            )
        hit = same[0] if same else None
    if hit is None:  # the walk skips folders the server refuses: try the table itself
        try:
            data = await call(src, tid)
        except UserError:
            data = None
        if isinstance(data, dict) and data.get("variables"):
            return {
                "id": tid,
                "short": tid,
                "title": data.get("title") or tid,
                "path": "",
                "updated": "",
                "archived": "",
            }
        raise UserError(f"Unknown {src.name} table '{table_id}'. Use {src.prefix}_search or find_data to find one.")
    return hit


# ---- table metadata ---------------------------------------------------------------------


async def table_meta(src: PxSource, tid: str) -> dict[str, Any]:
    """{'title', 'vars': [{code, text, values, texts, elim, time, contents}]}; cached."""

    async def load():
        data = await call(src, tid)
        if not isinstance(data, dict) or "variables" not in data:
            raise UserError(f"{src.name} returned no table for '{tid}'.")
        out = []
        for v in data["variables"]:
            values = [str(x) for x in v.get("values", [])]
            texts = [str(x) for x in v.get("valueTexts") or values]
            out.append(
                {
                    "code": v["code"],
                    "text": (v.get("text") or v["code"]).strip(),
                    "values": values,
                    "texts": texts if len(texts) == len(values) else values,
                    "elim": bool(v.get("elimination")),
                    "time": bool(v.get("time")),
                    "contents": v["code"].lower() == "contentscode",
                }
            )
        return {"title": (data.get("title") or tid).strip(), "vars": out}

    return await META.get((src.prefix, tid), load)


def pick_var(vars_: list[dict[str, Any]], name: str) -> dict[str, Any]:
    key = fold(str(name)).strip()
    for v in vars_:
        if fold(v["code"]) == key or fold(v["text"]) == key:
            return v
    valid = ", ".join(f"{v['code']} ({v['text']})" if fold(v["code"]) != fold(v["text"]) else v["code"] for v in vars_)
    raise UserError(f"Unknown variable '{name}'. Valid: {valid}")


def plain(label: str) -> str:
    """A value label for matching: folded, without the hierarchy dots some offices put before it."""
    return fold(label).lstrip(". ").strip()


def pick_values(src: PxSource, var: dict[str, Any], wanted: list[str]) -> list[str]:
    """Value codes for what the caller asked: a code, a unique label, or '*' for all."""
    if "*" in wanted:
        return list(var["values"])
    by_code = {c.lower(): c for c in var["values"]}
    by_text: dict[str, list[str]] = {}
    for c, t in zip(var["values"], var["texts"], strict=True):
        by_text.setdefault(plain(t), []).append(c)
    out = []
    for w in wanted:
        w = str(w).strip()
        if w.lower() in by_code:
            out.append(by_code[w.lower()])
        elif len(same := by_text.get(plain(w), [])) == 1:
            out.append(same[0])
        elif len(same) > 1:
            raise UserError(
                f"'{w}' is the label of several codes in {var['code']} ({', '.join(same[:5])}"
                f"{'…' if len(same) > 5 else ''}). Pick one: {src.prefix}_codes(table_id, '{var['code']}', '{w}')."
            )
        else:
            raise UserError(
                f"Unknown value '{w}' for {var['code']}. Look it up with "
                f"{src.prefix}_codes(table_id, '{var['code']}', '<words>'); '*' means all values."
            )
    return list(dict.fromkeys(out))


def span(var: dict[str, Any]) -> str:
    vals = var["values"]
    return f"{vals[0]}…{vals[-1]}" if len(vals) > 3 else ", ".join(vals)


def examples(var: dict[str, Any], n: int = 3) -> str:
    pairs = [f"{c}={t}" if c != t else c for c, t in zip(var["values"][:n], var["texts"][:n], strict=True)]
    return ", ".join(pairs) + ("…" if len(var["values"]) > n else "")


# ---- search -----------------------------------------------------------------------------


# Words people use for what the tables call something else (all four offices publish English titles).
COMMON: dict[str, tuple[str, ...]] = {
    "cpi": ("consumer price",),
    "hicp": ("harmonised", "harmonized"),
    "inflation": ("consumer price", "price index"),
    "gdp": ("gross domestic product",),
    "salary": ("wages",),
    "salaries": ("wages",),
    "pay": ("wages",),
    "earnings": ("wages",),
    "unemployed": ("unemployment",),
    "jobless": ("unemployment",),
    "jobs": ("employment",),
    "house": ("dwelling", "housing"),
    "houses": ("dwellings",),
    "homes": ("dwellings", "housing"),
    "tourists": ("tourism", "accommodation"),
    "people": ("population",),
    "inhabitants": ("population",),
    "residents": ("population",),
    "women": ("sex", "female"),
    "woman": ("sex", "female"),
    "men": ("sex", "male"),
    "man": ("sex", "male"),
    "gender": ("sex",),
    "youth": ("young", "age group"),
}


def query_groups(src: PxSource, query: str) -> list[list[str]]:
    """Free-text query → OR-groups of folded terms: the word, its stem and its translations,
    looked up English → local and local → English."""
    reverse: dict[str, list[str]] = {}
    for en, locals_ in src.synonyms.items():
        for loc in locals_:
            reverse.setdefault(fold(loc), []).append(en)
    groups = []
    for tok in re.findall(r"\w+", fold(query)):
        if len(tok) < 2 or tok in STOPWORDS:
            continue
        alts = [tok] + ([tok[:-1]] if tok.endswith("s") and len(tok) > 4 else [])
        for form in dict.fromkeys((tok, tok[:-1] if tok.endswith("s") else "", tok + "s")):
            if form:
                alts += [fold(x) for x in (*src.synonyms.get(form, ()), *COMMON.get(form, ()))] + reverse.get(form, [])
        groups.append(list(dict.fromkeys(a for a in alts if a)))
    return groups


def patterns(groups: list[list[str]]) -> list[re.Pattern[str]]:
    """One regex per term group: a whole word (or phrase), plural or past tense allowed. 'house' must
    not match 'household', or a search for house prices returns gas prices for household consumers."""
    return [re.compile(r"\b(?:" + "|".join(re.escape(a) for a in alts) + r")(?:s|es|ed|d)?\b") for alts in groups]


CODE_PREFIX = re.compile(r"^[^\s:]+\s*(?:--|:)\s*")  # '11rb -- ' or 'RV0240: ' before the real title


def rank(rows: list[dict[str, str]], groups: list[list[str]]) -> tuple[list[dict[str, str]], bool]:
    """(tables, partial). Best first: groups found in the title, then in the folder trail (the topic),
    then anywhere (title, trail, id), then titles that start with the words ('Population by…' before
    '…whole population'), then most recently updated. When any table matches every word, only those are
    returned; otherwise the tables matching some words, with partial=True."""
    pats = patterns(groups)

    def hits(text: str) -> int:
        return sum(bool(p.search(text)) for p in pats)

    def late(title: str) -> int:
        """Words before the first query word in the title (0 = it starts with it)."""
        bare = CODE_PREFIX.sub("", title)
        first = min((m.start() for p in pats if (m := p.search(bare))), default=len(bare))
        return len(bare[:first].split())

    scored = []
    for r in sorted(rows, key=lambda r: r["updated"], reverse=True):  # newest first; the sort below is stable
        anywhere = hits(r["hay"])
        if anywhere:
            title = fold(r["title"])
            scored.append((-hits(title), -hits(fold(r["path"])), -anywhere, late(title), r))
    full = [t for t in scored if -t[2] == len(pats)]
    chosen = full or scored
    chosen.sort(key=lambda t: t[:4])
    return [t[-1] for t in chosen], not full and bool(scored)


# ---- tools ------------------------------------------------------------------------------


def register(mcp: FastMCP, src: PxSource) -> None:
    """Add `<prefix>_search / _describe / _codes / _data` for one PxWeb source."""
    p = src.prefix

    async def search(query: str, include_discontinued: bool = False, limit: int = 10) -> str:
        limit = max(1, min(limit, 50))
        groups = query_groups(src, query)
        if not groups:
            raise UserError("Give topic keywords, e.g. 'population' or 'unemployment'.")
        rows = [r for r in await catalog(src) if include_discontinued or not r["archived"]]
        hits, partial = rank(rows, groups)
        if not hits:
            hint = "" if include_discontinued else " or include_discontinued=true"
            return f"No tables match '{query}'. Try other keywords{hint}."
        lines = ["id|title|updated"] + [
            "|".join(
                cell(x) for x in (r["short"], r["title"] + (" [discontinued]" if r["archived"] else ""), r["updated"])
            )
            for r in hits[:limit]
        ]
        if partial:
            lines.append("# no table matches all the words; these match only some of them")
        if len(hits) > limit:
            lines.append(f"# {limit} of {len(hits)} matches; refine the query for others")
        if INCOMPLETE.get(p):
            lines.append(f"# {INCOMPLETE[p]} folders of the table list could not be read; the list may be incomplete")
        return "\n".join(lines)

    async def describe(table_id: str) -> str:
        t = await resolve(src, table_id)
        m = await table_meta(src, t["id"])
        out = [f"{t['short']}: {m['title']}"]
        if t["archived"]:
            out.append("status: discontinued (archive folder); prefer a current table")
        if t["updated"]:
            out.append(f"updated: {t['updated']}")
        if caveat := src.note(t["id"]):
            out.append(f"note: {caveat}")
        if t["path"]:
            out.append(f"topic: {t['path']}")
        out.append("variables (code|name|values|use):")
        for v in m["vars"]:
            if v["time"]:
                use, shown = "time: newest period by default, last_n=N for more", span(v)
            elif v["contents"]:
                use, shown = (
                    ("measures: all by default", f"{len(v['values'])}")
                    if len(v["values"]) <= MAX_DEFAULT_MEASURES
                    else (
                        f"measures: required, choose some (more than {MAX_DEFAULT_MEASURES}; '*' = all)",
                        f"{len(v['values'])}",
                    )
                )
            elif v["elim"]:
                use, shown = (
                    "optional: omitted = server default (normally the total)",
                    f"{len(v['values'])} ({examples(v)})",
                )
            else:
                use, shown = "required: choose values (or '*' for all)", f"{len(v['values'])} ({examples(v)})"
            out.append(f"{v['code']}|{cell(v['text'])}|{shown}|{use}")
        for v in m["vars"]:
            if v["contents"]:
                out.append("measures (code|text):")
                out += [f"{c}|{cell(x)}" for c, x in zip(v["values"], v["texts"], strict=True)][:40]
                if len(v["values"]) > 40:
                    out.append(f"# {len(v['values']) - 40} more: {p}_codes(id, '{v['code']}', query)")
        return "\n".join(out)

    async def codes(table_id: str, variable: str, query: str | None = None, limit: int = 50) -> str:
        limit = max(1, min(limit, 500))
        t = await resolve(src, table_id)
        var = pick_var((await table_meta(src, t["id"]))["vars"], variable)
        items = list(zip(var["values"], var["texts"], strict=True))
        if var["time"]:
            items.sort(reverse=True)  # newest first
        if query:
            q = src.aliases.get(fold(query).strip(), query)
            words = plain(q).split()
            items = [i for i in items if all(w in plain(i[1]) or w in fold(i[0]) for w in words)]
            key = plain(q)
            items.sort(key=lambda i: (plain(i[1]) != key and fold(i[0]) != key, not plain(i[1]).startswith(key)))
        if not items:
            return f"No codes match '{query}' in {var['code']}."
        lines = ["code|text"] + [f"{cell(c)}|{cell(x)}" for c, x in items[:limit]]
        if len(items) > limit:
            lines.append(f"# {limit} of {len(items)}; add/narrow query")
        return "\n".join(lines)

    async def data(
        table_id: str,
        filters: dict[str, list[str]] | None = None,
        last_n: int | None = None,
        limit: int = 500,
    ) -> str:
        limit = max(1, min(limit, 5000))
        t = await resolve(src, table_id)
        m = await table_meta(src, t["id"])
        vars_ = m["vars"]
        chosen: dict[str, list[str]] = {}
        for name, vals in (filters or {}).items():
            var = pick_var(vars_, name)
            if wanted := as_list(vals):
                chosen[var["code"]] = pick_values(src, var, wanted)
        time_var = next((v for v in vars_ if v["time"]), None)
        if last_n is not None and time_var and time_var["code"] in chosen:
            raise UserError(f"Use either last_n or a filter on {time_var['code']}, not both.")

        query, omitted, missing, cells = [], [], [], 1
        for v in vars_:
            if v["code"] in chosen:
                sel, n = {"filter": "item", "values": chosen[v["code"]]}, len(chosen[v["code"]])
            elif v["time"]:
                n = max(1, min(last_n or 1, len(v["values"])))
                sel = {"filter": "top", "values": [str(n)]}
            elif len(v["values"]) == 1 or (v["contents"] and len(v["values"]) <= MAX_DEFAULT_MEASURES):
                sel, n = {"filter": "item", "values": list(v["values"])}, len(v["values"])
            elif v["elim"]:
                omitted.append(v)
                continue
            else:
                missing.append(v)
                continue
            query.append({"code": v["code"], "selection": sel})
            cells *= n
        if missing:
            raise UserError(
                "Choose values for: "
                + "; ".join(
                    f"{v['code']} ({v['text']}, {len(v['values'])} {'measures' if v['contents'] else 'values'})"
                    for v in missing
                )
                + f". Look codes up with {p}_codes; '*' means all values."
            )
        if cells > MAX_CELLS:
            raise UserError(
                f"query too broad (~{cells:,} values, max {MAX_CELLS:,}). Narrow the filters"
                + (", or use fewer measures" if any(v["contents"] and len(v["values"]) > 3 for v in vars_) else "")
                + f"; find codes with {p}_codes."
            )

        res = await call(src, t["id"], {"query": query, "response": {"format": "json"}})
        cols, rows = res.get("columns") or [], res.get("data") or []
        dims = [c for c in cols if c.get("type") != "c"]
        measures = [c for c in cols if c.get("type") == "c"]
        by_var = {v["code"]: dict(zip(v["values"], v["texts"], strict=True)) for v in vars_}
        contents_var = next((v for v in vars_ if v["contents"]), None)
        labels = [c.get("text") or c.get("code") or "value" for c in measures]
        if contents_var:
            sent = next(q for q in query if q["code"] == contents_var["code"])["selection"]["values"]
            names = by_var[contents_var["code"]]
            if all(c.get("code") in names for c in measures):
                labels = [names[c["code"]] for c in measures]
            elif len(sent) == len(measures):  # servers that name the column after the table, not the measure
                labels = [names[c] for c in sent]
        show_measure = contents_var is not None or len(measures) > 1
        time_at = next((i for i, c in enumerate(dims) if c.get("type") == "t"), None)

        table, empty = [], {}
        for rec in sorted(rows, key=lambda r: r["key"][time_at] if time_at is not None else "", reverse=True):
            head = [by_var.get(c.get("code"), {}).get(k, k) for c, k in zip(dims, rec["key"], strict=False)]
            for label, v in zip(labels, rec["values"], strict=False):
                if v is None or str(v).strip().lower() in MISSING:
                    empty[str(v or "empty")] = empty.get(str(v or "empty"), 0) + 1
                    continue
                table.append([*head, *([label] if show_measure else []), str(v)])
        names_ = [c.get("text") or c.get("code") for c in dims]
        out = [f"{t['short']}: {m['title']}"]
        if t["updated"]:
            out.append(f"updated: {t['updated']}")
        if not table:
            out.append("No values for these filters." + (f" Empty cells: {empty}" if empty else ""))
            return "\n".join(out)
        shown = table[:limit]
        out += compact_table([*names_, *(["measure"] if show_measure else []), "value"], shown)
        if len(table) > limit:
            out.append(f"# truncated: {limit} of {len(table)} values; narrow filters or raise limit")
        if empty:
            out.append(f"# omitted empty cells: {empty}")
        if omitted:
            out.append(
                "# omitted variables use the server default (normally the total): "
                + ", ".join(v["text"] for v in omitted)
            )
        if caveat := src.note(t["id"]):
            out.append(f"# note: {caveat}")
        out.append(source_line(src.page(t["id"]), src.licence))
        return "\n".join(out)

    c, a, loc = src.country, src.agency, src.local
    docs = {
        "search": (
            search,
            f"Find {src.name} ({a}) tables by topic, in English or {loc}. Start here for {c} statistics.\n"
            f"Leave places and years out of the query: they are codes picked later with {p}_codes.",
        ),
        "describe": (
            describe,
            f"Show a {src.name} table's variables (value counts) and measures before querying it.\n"
            f"Use the variable codes with {p}_codes and {p}_data.",
        ),
        "codes": (
            codes,
            f"Look up the codes of a {src.name} variable by name (a region, sex, measure...); periods newest first.\n"
            "variable: its code or name from describe; query: words of the label.",
        ),
        "data": (
            data,
            f"Fetch {src.name} values. filters = {{variable: [codes]}}; '*' = all values; time defaults to the latest\n"
            "period (last_n=N for more); omitted optional variables are totals. Constant columns are shown once.",
        ),
    }
    for verb, (fn, doc) in docs.items():
        fn.__name__, fn.__doc__ = f"{p}_{verb}", doc
        mcp.tool(name=f"{p}_{verb}", annotations=READ_ONLY, output_schema=None)(safe(fn))
