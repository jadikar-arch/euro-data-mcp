"""European Parliament open data API v2: MEPs, plenary votes and a generic endpoint reader."""

from __future__ import annotations

import asyncio
import re
from datetime import date
from typing import Any

from fastmcp import FastMCP

from ...common import READ_ONLY, NotFound, UserError, as_list, cell, clip, fold, safe, source_line
from ...web import Memo, fetch_json

BASE = "https://data.europarl.europa.eu/api/v2"
EP_LICENCE = "reuse authorised with attribution, © European Union (European Parliament)"
SITE = "https://data.europarl.europa.eu/"
FMT = {"format": "application/ld+json"}
LANGS = {
    "bg",
    "cs",
    "da",
    "de",
    "el",
    "en",
    "es",
    "et",
    "fi",
    "fr",
    "ga",
    "hr",
    "hu",
    "it",
    "lt",
    "lv",
    "mt",
    "nl",
    "pl",
    "pt",
    "ro",
    "sk",
    "sl",
    "sv",
    "mul",
}
# Noise in list/detail payloads: XML fragments, per-language duplicates, back-references.
DROP = {
    "@context",
    "structuredLabel",
    "decisionAboutId_XMLLiteral",
    "decisionAboutId_Lang",
    "searchResults",
    "inverse_consists_of",
    "sortLabel",
    "comment",
    "type",
    "is_about",
    "title_dcterms",
    "isAboutDirectoryCode",
    "isAboutSubjectMatter",
    "creator",
    "publisher",
    "identifierYear",
    "notation_codictPersonId",
    "upperFamilyName",
    "upperGivenName",
    "inverse_refers_to",
    "inverse_decided_on_a_realization_of",
}
MAX_LIST = 6
MAX_CHARS = 12_000  # ep_query output budget; the rest is reached with offset
QUESTION_DETAILS = 20  # parliamentary-questions: items whose title/author are fetched
# English/common names → the API's group labels (PPE, S&D, PfE, ECR, Renew, Verts/ALE, The Left, NI, ESN)
GROUP_ALIASES = {
    "epp": "ppe",
    "greens": "verts/ale",
    "greens/efa": "verts/ale",
    "efa": "verts/ale",
    "left": "the left",
    "gue/ngl": "the left",
    "non-attached": "ni",
    "nonattached": "ni",
    "patriots": "pfe",
    "socialists": "s&d",
    "sd": "s&d",
}

SPEC = Memo(ttl=24 * 3600)
MEPS = Memo(ttl=6 * 3600)
SITTINGS = Memo(ttl=6 * 3600)
ORGS = Memo(ttl=24 * 3600)


async def org_labels() -> dict[str, str]:
    """'org/7005' → 'DROI' for all ~4k EP bodies (committees, groups, delegations)."""

    async def load():
        data = await fetch_json(f"{BASE}/corporate-bodies", {**FMT, "offset": 0, "limit": 10000})
        return {o["id"]: o.get("label") or o["id"] for o in (data or {}).get("data", [])}

    return await ORGS.get("orgs", load)


def memberships(ms: list[dict], orgs: dict[str, str], today: str) -> list[str]:
    """Current memberships as 'role kind org (since start)', plus a count of past ones."""
    current, past = [], 0
    for m in ms:
        period = m.get("memberDuring") or {}
        end = period.get("endDate") or ""
        if end and end < today:
            past += 1
            continue
        kind = short(m.get("membershipClassification", "")).replace("entities/", "")
        role = short(m.get("role", "")).replace("roles/", "")
        org = orgs.get(m.get("organization", ""), short(m.get("organization", "")))
        current.append(" ".join(x for x in (role, kind, org) if x) + f" (since {period.get('startDate', '?')})")
    out = [f"current memberships: {'; '.join(current)}"] if current else []
    if past:
        out.append(f"past memberships: {past}")
    return out


async def paths() -> dict[str, set[str]]:
    """OpenAPI GET path template → accepted query param names."""

    async def load():
        spec = await fetch_json(f"{BASE}/")
        comps = spec.get("components", {}).get("parameters", {})
        out = {}
        for path, ops in spec.get("paths", {}).items():
            names = set()
            for p in (ops.get("get") or {}).get("parameters", []):
                if "$ref" in p:
                    p = comps.get(p["$ref"].rsplit("/", 1)[-1], {})
                if p.get("in") == "query":
                    names.add(p["name"])
            out[path.strip("/")] = names
        return out

    return await SPEC.get("spec", load)


def match_path(endpoint: str, templates: dict[str, set[str]]) -> tuple[str, set[str]]:
    ep = endpoint.strip().strip("/").removeprefix("api/v2/")
    parts = ep.split("/")
    best = None
    for tpl, params in templates.items():
        tparts = tpl.split("/")
        if len(tparts) != len(parts):
            continue
        if all(t == p or (t.startswith("{") and t.endswith("}")) for t, p in zip(tparts, parts, strict=True)):
            literal = sum(not t.startswith("{") for t in tparts)
            if best is None or literal > best[0]:  # prefer meps/show-current over meps/{id}
                best = (literal, params)
    if best is None:
        roots = sorted({t.split("/")[0] for t in templates})
        raise UserError(f"Unknown endpoint '{endpoint}'. Roots: {', '.join(roots)}")
    return ep, best[1]


def pick_lang(v: Any, lang: str) -> Any:
    """Collapse {'en': 'x', 'nl': 'y', ...} to one string."""
    if isinstance(v, dict) and v and set(v) <= LANGS:
        return v.get(lang) or v.get("en") or v.get("mul") or next(iter(v.values()))
    return v


def short(v: Any) -> str:
    s = str(v)
    for prefix in ("http://publications.europa.eu/resource/authority/", "def/ep-", "eli/dl/"):
        s = s.replace(prefix, "")
    return s


def files(realized: list[dict], lang: str) -> list[str]:
    """Download links for one language from an `is_realized_by` expression list."""
    pick = [e for e in realized if str(e.get("id", "")).endswith("/" + lang)] or [
        e for e in realized if str(e.get("id", "")).endswith("/en")
    ]
    out = []
    for e in pick[:1]:
        for m in e.get("is_embodied_by") or []:
            if m.get("is_exemplified_by"):
                out.append(SITE + m["is_exemplified_by"])
    return out


def flatten(item: dict[str, Any], lang: str, orgs: dict[str, str] | None = None) -> list[str]:
    """One `key: value` per line; nested objects reduced to their label/id; long lists counted."""
    lines = []
    for k, v in item.items():
        if k in DROP or v in (None, "", [], {}):
            continue
        if k == "hasMembership" and isinstance(v, list) and orgs is not None:
            lines += memberships([m for m in v if isinstance(m, dict)], orgs, date.today().isoformat())
            continue
        if k == "is_realized_by" and isinstance(v, list):
            title = next(
                (
                    pick_lang(e.get("title"), lang)
                    for e in v
                    if str(e.get("id", "")).endswith("/" + lang) and e.get("title")
                ),
                None,
            )
            if title:
                lines.append(f"title: {clip(title, 300)}")
            if urls := files(v, lang):
                lines.append("files: " + ", ".join(urls))
            continue
        v = pick_lang(v, lang)
        if isinstance(v, dict):
            v = pick_lang(v.get("label") or v.get("title"), lang) or v.get("id") or ""
            if isinstance(v, dict):
                v = v.get("id", "")
        if isinstance(v, list):
            vals = [pick_lang(x, lang) for x in v]
            vals = [
                (pick_lang(x.get("label") or x.get("title"), lang) or x.get("id")) if isinstance(x, dict) else x
                for x in vals
            ]
            vals = [short(x) for x in vals if x not in (None, "")]
            more = f" … (+{len(vals) - MAX_LIST})" if len(vals) > MAX_LIST else ""
            v = ", ".join(str(x) for x in vals[:MAX_LIST]) + more
        lines.append(f"{k}: {clip(short(v), 300)}")
    return lines


# ---- MEPs ---------------------------------------------------------------------------


async def current_meps() -> list[dict[str, str]]:
    async def load():
        data = await fetch_json(f"{BASE}/meps/show-current", {**FMT, "offset": 0, "limit": 1000})
        return [
            {
                "id": m.get("identifier", ""),
                "name": m.get("label", ""),
                "country": m.get("api:country-of-representation", ""),
                "group": m.get("api:political-group", ""),
            }
            for m in (data or {}).get("data", [])
        ]

    return await MEPS.get("current", load)


@safe
async def ep_meps(
    name: str | None = None, country: str | None = None, group: str | None = None, limit: int = 50
) -> str:
    """List current Members of the European Parliament; filter by name, country (ISO2, e.g. NL)
    or political group (e.g. EPP, S&D, Renew, Greens). Details: ep_query('meps/{id}')."""
    meps = await current_meps()
    if name:
        words = fold(name).split()
        meps = [m for m in meps if all(w in fold(m["name"]) for w in words)]
    if country:
        meps = [m for m in meps if m["country"].upper() == country.strip().upper()]
    if group:
        g = fold(group).strip()
        g = GROUP_ALIASES.get(g, g).replace(" ", "")
        meps = [m for m in meps if g in fold(m["group"]).replace(" ", "")]
    if not meps:
        return "No current MEPs match. For former MEPs use ep_query('meps', {'parliamentary-term': 9})."
    limit = max(1, min(limit, 750))
    lines = ["id|name|country|group"] + [
        "|".join(cell(m[k]) for k in ("id", "name", "country", "group")) for m in meps[:limit]
    ]
    if len(meps) > limit:
        lines.append(f"# {limit} of {len(meps)}; filter by country/group or raise limit")
    lines.append(source_line(f"{BASE}/meps/show-current", EP_LICENCE))
    return "\n".join(lines)


# ---- votes --------------------------------------------------------------------------


async def sitting(date: str) -> tuple[list[dict], dict[str, str]]:
    """Plenary decisions of a sitting day plus vote-item id → title."""

    async def load():
        sid = f"MTG-PL-{date}"
        decisions, items = await asyncio.gather(
            fetch_json(f"{BASE}/meetings/{sid}/decisions", {**FMT, "offset": 0, "limit": 2000}),
            fetch_json(f"{BASE}/meetings/{sid}/vote-results", {**FMT, "offset": 0, "limit": 500}),
        )
        titles = {it["id"]: pick_lang(it.get("activity_label"), "en") or "" for it in (items or {}).get("data", [])}
        return (decisions or {}).get("data", []), titles

    return await SITTINGS.get(date, load)


def vote_label(label: str, n: int = 70) -> str:
    """Shorten a vote label without losing its tail: 'A10-0272/2026 – <rapporteurs> – § 3 – Am 70'
    drops the rapporteur names first, then clips the middle, so amendment numbers stay visible."""
    if len(label) <= n:
        return label
    parts = label.split(" – ")
    if len(parts) >= 3:
        label = " – ".join([parts[0], *parts[2:]])
    if len(label) <= n:
        return label
    head = n // 3
    return label[:head].rstrip() + "…" + label[-(n - head - 1) :].lstrip()


def voting_order(decisions: list[dict]) -> list[dict]:
    """Agenda items in the order they were voted (first roll-call timestamp), votes within an
    item by their order number. Show-of-hands votes carry no timestamp, only the order."""
    first: dict[str, str] = {}
    for d in decisions:
        parent, ts = (d.get("inverse_consists_of") or [""])[0], d.get("activity_start_date") or ""
        if ts and (parent not in first or ts < first[parent]):
            first[parent] = ts
    return sorted(
        decisions,
        key=lambda d: (
            first.get((d.get("inverse_consists_of") or [""])[0], "~"),
            float(d.get("activity_order") or 0),
        ),
    )


@safe
async def ep_votes(
    date: str,
    query: str | None = None,
    roll_call_only: bool = False,
    mep_id: str | None = None,
    language: str = "en",
    limit: int = 40,
) -> str:
    """Plenary votes on a sitting day (YYYY-MM-DD): item, outcome and for/against/abstain counts.
    query filters by topic text; mep_id adds how that MEP voted (roll-call votes only)."""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date.strip()):
        raise UserError("date must be YYYY-MM-DD (a plenary sitting day).")
    try:
        decisions, titles = await sitting(date.strip())
    except NotFound:
        decisions, titles = [], {}
    if not decisions:
        return f"No plenary votes on {date}. Sitting days: ep_query('meetings', {{'year': {date[:4]}}})."
    person = f"person/{mep_id.strip()}" if mep_id else None
    rows = []
    for d in voting_order(decisions):
        rc = "ROLLCALL" in str(d.get("decision_method", ""))
        if (roll_call_only or person) and not rc:
            continue
        parent = (d.get("inverse_consists_of") or [""])[0]
        topic = titles.get(parent, "")
        label = " ".join(str(pick_lang(d.get("activity_label"), language) or "").split())
        about = str(d.get("decisionAboutId") or "")
        if (
            about[:1].isdigit() and label and not re.search(r"\bAm\b", label)
        ):  # budget lines: same label, other amendment
            label += f" – Am {about}"
        if query:
            hay = fold(f"{topic} {label} {pick_lang(d.get('headingLabel'), language) or ''}")
            if not all(w in hay for w in fold(query).split()):
                continue
        row = [
            clip(topic, 90),
            vote_label(label),
            short(d.get("decision_outcome", "")).replace("statuses/", ""),
            short(d.get("decision_method", "")).replace("decision-methods/VOTE_", ""),
            str(d.get("number_of_votes_favor", "")),
            str(d.get("number_of_votes_against", "")),
            str(d.get("number_of_votes_abstention", "")),
            str(d.get("notation_votingId", "")),
        ]
        if person:
            how = next(
                (
                    k.removeprefix("had_voter_")
                    for k in ("had_voter_favor", "had_voter_against", "had_voter_abstention")
                    if person in (d.get(k) or [])
                ),
                "absent/no vote",
            )
            row.append(how)
        rows.append(row)
    if not rows:
        return f"No votes on {date} match these filters ({len(decisions)} decisions that day)."
    limit = max(1, min(limit, 500))
    head = "topic|item|outcome|method|for|against|abstain|vote_id" + ("|mep_vote" if person else "")
    lines = [head] + ["|".join(cell(x) for x in r) for r in rows[:limit]]
    if len(rows) > limit:
        lines.append(f"# {limit} of {len(rows)}; narrow query or raise limit")
    lines.append(source_line(f"{BASE}/meetings/MTG-PL-{date}/decisions", EP_LICENCE))
    return "\n".join(lines)


# ---- generic ------------------------------------------------------------------------


def meeting_rows(items: list[dict], lang: str) -> list[str]:
    """Sitting days as one line each (the full records are ~1 KB): what ep_votes needs."""
    rows = ["date|id|label|agenda_items"]
    for it in items:
        label = pick_lang(it.get("activity_label"), lang) or ""
        rows.append(
            "|".join(
                cell(x)
                for x in (
                    str(it.get("activity_date") or it.get("activity_start_date") or "")[:10],
                    it.get("activity_id", ""),
                    clip(label, 80),
                    len(it.get("consists_of") or []),
                )
            )
        )
    return rows


async def question_rows(items: list[dict], lang: str) -> list[str]:
    """The questions list has ids only; fetch each question for its date, author and title."""

    async def detail(it: dict) -> dict:
        try:
            data = await fetch_json(f"{BASE}/parliamentary-questions/{it.get('identifier', '')}", FMT)
        except UserError:
            return it
        return ((data or {}).get("data") or [it])[0]

    full = await asyncio.gather(*(detail(it) for it in items[:QUESTION_DETAILS]))
    names = {f"person/{m['id']}": m["name"] for m in await current_meps()}
    rows = ["id|date|type|author|answered|title"]
    for q in [*full, *items[QUESTION_DETAILS:]]:
        authors = [names.get(p, short(p)) for p in q.get("creator") or []]
        rows.append(
            "|".join(
                cell(x)
                for x in (
                    q.get("identifier", ""),
                    q.get("document_date", ""),
                    short(q.get("work_type", "")).replace("document-types/QUESTION_", "").lower(),
                    clip(", ".join(authors), 60),
                    "yes" if q.get("inverse_answers_to") else "no" if "document_date" in q else "",
                    clip(pick_lang(q.get("title_dcterms"), lang) or "", 120),
                )
            )
        )
    return rows


@safe
async def ep_query(
    endpoint: str,
    params: dict[str, Any] | None = None,
    language: str = "en",
    limit: int = 10,
    offset: int = 0,
) -> str:
    """Read any EP Open Data endpoint, e.g. 'adopted-texts' {'text':'housing','year':2026},
    'procedures/2024-2526', 'meetings' {'year':2026}, 'speeches', 'documents/{id}'.
    Labels are shown in `language`; long lists are counted."""
    templates = await paths()
    ep, allowed = match_path(endpoint, templates)
    query: dict[str, Any] = dict(FMT)
    for k, v in (params or {}).items():
        if k not in allowed:
            raise UserError(f"Unknown param '{k}' for {ep}. Valid: {', '.join(sorted(allowed))}")
        vals = as_list(v)
        if vals:
            query[k] = vals if len(vals) > 1 else vals[0]
    if "text" in query or "title" in query:
        query.setdefault("search-language", language)
    limit = max(1, min(limit, 100))
    if "limit" in allowed:
        query.update(limit=limit, offset=max(0, offset))
    if "language" in allowed:
        query.setdefault("language", language)
    try:
        data = await fetch_json(f"{BASE}/{ep}", query)
    except NotFound as e:
        return f"Not found: {ep} ({e})"
    if not data or not data.get("data"):
        return f"No results for {ep}."
    items = data["data"][:limit]
    total = (data.get("meta") or {}).get("total")
    if ep == "meetings":
        out = meeting_rows(items, language)
    elif ep == "parliamentary-questions":
        out = await question_rows(items, language)
    else:
        orgs = await org_labels() if any("hasMembership" in it for it in items) else None
        out, size = [], 0
        for n, it in enumerate(items):
            block = "- " + "\n  ".join(flatten(it, language, orgs))
            if out and size + len(block) > MAX_CHARS:
                items = items[:n]  # output budget reached: the rest via offset
                break
            out.append(block)
            size += len(block)
    shown = len(items)
    if (total and total > offset + shown) or shown < len(data["data"][:limit]):
        of = f" of {total}" if total else ""
        out.append(f"# {shown}{of}; use offset={offset + shown} or narrow params")
    out.append(source_line(f"{BASE}/{ep}", EP_LICENCE))
    return "\n".join(out)


def register(mcp: FastMCP) -> None:
    for fn in (ep_meps, ep_votes, ep_query):
        mcp.tool(annotations=READ_ONLY, output_schema=None)(fn)
