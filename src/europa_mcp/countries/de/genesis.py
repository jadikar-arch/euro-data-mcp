"""Destatis GENESIS tables via their keyless CSV downloads (linked from GovData's Destatis datasets).

The CSVs are laid out for print: title and meta lines, 1-3 header rows (first cell empty), data rows
(row labels, then values), then a `__________`/© footer with quoted footnotes. We turn that into
long rows (labels, column, value) so the model can filter and read them compactly.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field

from fastmcp import FastMCP

from ...common import NotFound, READ_ONLY, UserError, clip, compact_table, fold, safe
from ...web import Memo, fetch

DOWNLOAD = "https://genesis.destatis.de/genesisWS/downloads/00/tables/{}_00.csv"
TABLES = Memo(ttl=6 * 3600)
ID_RE = re.compile(r"^\d{5}-\d{4}[A-Za-z]?$")
BASE_YEAR = re.compile(r"\b\d{4}\s*=\s*100\b")  # index base ('2020=100') is not a period
MONTHS = "januar februar marz april mai juni juli august september oktober november dezember".split()
TIME_RE = re.compile(r"\b(1[89]|20)\d\d\b|quartal|halbjahr|^(" + "|".join(MONTHS) + ")$")
NOT_YET = "..."
SYMBOLS = {"-": "- = nothing (0)", ".": ". = secret", "x": "x = not applicable", "/": "/ = too uncertain"}


@dataclass
class Table:
    id: str
    title: str
    meta: list[str] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)  # one name per value column
    rows: list[tuple[tuple[str, ...], list[str]]] = field(default_factory=list)  # (labels, values)
    notes: str = ""
    stand: str = ""


def parse(table_id: str, text: str) -> Table:
    lines = [[c.strip() for c in r] for r in csv.reader(io.StringIO(text), delimiter=";")]
    lines = [r[: max((i + 1 for i, c in enumerate(r) if c), default=0)] for r in lines]  # trim trailing ;;;
    t = Table(table_id, lines[1][0] if len(lines) > 1 and lines[1] else table_id)
    headers: list[list[str]] = []
    notes: list[str] = []
    prev: tuple[str, ...] = ()
    done = False
    for r in lines[2:]:
        if not r:
            continue
        first = r[0]
        if first.startswith("__") or first.startswith("©"):
            done = True
        elif first.startswith("Stand:"):
            t.stand = first.removeprefix("Stand:").split("/")[0].strip()
        elif done or (len(r) == 1 and t.rows):
            notes.append(first)
        elif len(r) == 1 and not t.meta and (t.title[-1:] in ":,-/" or first[:1].islower() or first[:1] == "("):
            t.title += first if t.title.endswith("/") else f" {first}"  # long titles wrap onto the next lines
        elif len(r) == 1:
            t.meta.append(first)
        elif not first and not t.rows:
            headers.append(r)
        else:
            k = label_count(headers)
            labels = tuple(c or (prev[i] if i < len(prev) else "") for i, c in enumerate(r[:k]))  # fill down
            prev = labels
            t.rows.append((labels, r[k:]))
    k = label_count(headers)
    width = max((len(v) for _, v in t.rows), default=0)
    for j in range(width):
        parts = [h[k + j] for h in headers if len(h) > k + j and h[k + j]]
        t.columns.append(" ".join(dict.fromkeys(parts)) or f"col{j + 1}")
    t.notes = " ".join(" ".join(notes).split())
    return t


def label_count(headers: list[list[str]]) -> int:
    """Row-label columns = the empty cells that lead every header row (at least one)."""
    lead = [next((i for i, c in enumerate(h) if c), len(h)) for h in headers]
    return max(1, min(lead, default=1))


async def load(table_id: str) -> Table:
    async def get():
        try:
            resp = await fetch(DOWNLOAD.format(table_id))
        except NotFound:
            raise UserError(f"Unknown Destatis table '{table_id}'. Find tables with find_data or govdata_search.") from None
        body = resp.content
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError:
            text = body.decode("latin-1")
        if not text.startswith("Tabelle"):
            raise UserError(f"Destatis returned no table for '{table_id}'.")
        return parse(table_id, text)

    return await TABLES.get(table_id, get)


def is_time(values: list[str]) -> bool:
    vals = [BASE_YEAR.sub("", fold(v)) for v in values if v]
    return bool(vals) and sum(bool(TIME_RE.search(v)) for v in vals) >= 0.8 * len(vals)


def number(v: str) -> str:
    """German decimals: '120,3' → '120.3', '+2,3' → '+2.3'; symbols and integers unchanged."""
    return v.replace(".", "").replace(",", ".") if re.fullmatch(r"[+-]?[\d.]*\d,\d+", v) else v


@safe
async def govdata_table(table_id: str, query: str | None = None, last_n: int | None = None, limit: int = 100) -> str:
    """Values of a Destatis GENESIS table (e.g. '12411-0010' population by state), newest first.
    query: words that must appear in the row labels/column (e.g. 'Bayern'); last_n: newest N periods."""
    tid = table_id.strip().removesuffix("_00")
    if not ID_RE.match(tid):
        raise UserError(f"'{table_id}' is not a GENESIS table id like '12411-0001'.")
    t = await load(tid)
    if not t.rows:
        return f"{tid}: {t.title}\nNo values in this table."
    k = len(t.rows[0][0])
    # Where is time? In the column headers (e.g. 'Stichtag 31.12.2024') or in some label columns.
    time_cols = is_time(t.columns)
    time_labels = [] if time_cols else [i for i in range(k) if is_time([lab[i] for lab, _ in t.rows])]
    live = [j for j in range(len(t.columns)) if any(j < len(v) and v[j] not in ("", NOT_YET) for _, v in t.rows)]

    rows = [r for r in t.rows if any(v not in ("", NOT_YET) for v in r[1])]  # e.g. future months
    cols = live[::-1] if time_cols else live  # newest first
    if last_n and time_cols:
        cols = cols[: max(1, last_n)]
    if time_labels:
        key = lambda r: tuple(r[0][i] for i in time_labels)  # noqa: E731
        keys = list(dict.fromkeys(map(key, rows)))
        keep = set(keys[-max(1, last_n):]) if last_n else set(keys)
        rank = {k: i for i, k in enumerate(keys)}
        rows = sorted((r for r in rows if key(r) in keep), key=lambda r: -rank[key(r)])  # newest first, stable

    words = fold(query or "").split()
    names = [(f"period{time_labels.index(i) + 1}".removesuffix("1") if i in time_labels else f"label{i + 1}")
             for i in range(k)]
    names = [n if n != "label1" or k > 1 or time_labels else "label" for n in names]
    out_rows, pending, used = [], 0, set()
    for labels, values in rows:
        for j in cols:
            v = values[j] if j < len(values) else ""
            if v in ("", NOT_YET):
                continue
            if words:
                text = fold(" ".join(labels) + " " + t.columns[j])
                if not all(w in text for w in words):
                    continue
            if len(out_rows) >= max(1, min(limit, 500)):
                pending += 1
                continue
            used.update(c for c in SYMBOLS if v == c)
            out_rows.append([*labels, t.columns[j], number(v)])

    out = [f"{tid}: {t.title}"]
    if t.meta:
        out.append("about: " + "; ".join(t.meta))
    if t.stand:
        out.append(f"as of: {t.stand}")
    if not out_rows:
        out.append(f"No values match query '{query}'." if words else "No values yet.")
        out.append("# rows: " + clip(", ".join(dict.fromkeys(lab[0] for lab, _ in t.rows)), 300))
        return "\n".join(out)
    out += compact_table([*names, "period" if time_cols else "column", "value"], out_rows)
    if pending:
        first = list(dict.fromkeys(lab[0] for lab, _ in t.rows))
        out.append(f"# truncated: {len(out_rows)} of {len(out_rows) + pending} values; add query= or last_n=")
        if not words and len(first) > 1:
            out.append("# first-column labels: " + clip(", ".join(first), 300))
    if used:
        out.append("# symbols: " + "; ".join(SYMBOLS[s] for s in sorted(used)))
    if t.notes:
        out.append("notes: " + clip(t.notes, 300))
    return "\n".join(out)


def register(mcp: FastMCP) -> None:
    mcp.tool(annotations=READ_ONLY, output_schema=None)(govdata_table)
