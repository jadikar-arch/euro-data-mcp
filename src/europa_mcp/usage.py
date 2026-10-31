"""Opt-in, anonymous usage log for hosted deployments, and a report over it.

Set EUROPA_USAGE_LOG=/path/usage.jsonl to record one line per tool call: time, tool, the text
arguments (queries, dataset ids, filters), outcome (ok / empty / error) and duration. Nothing
identifies the caller: no IP addresses, tokens or conversation text. `europa-mcp usage` then
shows what people ask and, more usefully, what they ask that no source could answer.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

from fastmcp.server.middleware import Middleware

MAX_ARG = 200
EMPTY_PREFIXES = ("No ", "Unknown ")


def outcome(text: str) -> str:
    if text.startswith("Error:"):
        return "error"
    if text.startswith(EMPTY_PREFIXES):
        return "empty"
    return "ok"


def _short(v: Any) -> Any:
    if isinstance(v, str):
        return v[:MAX_ARG]
    if isinstance(v, (int, float, bool)) or v is None:
        return v
    return json.dumps(v, ensure_ascii=False)[:MAX_ARG]


class UsageLog(Middleware):
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    async def on_call_tool(self, context, call_next):
        start = time.monotonic()
        msg = context.message
        result = await call_next(context)
        text = "".join(getattr(b, "text", "") for b in getattr(result, "content", None) or [])
        line = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "tool": msg.name,
            "args": {k: _short(v) for k, v in (msg.arguments or {}).items()},
            "outcome": outcome(text),
            "ms": round((time.monotonic() - start) * 1000),
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
        return result


def report(path: Path, top: int = 15) -> str:
    rows = []
    for raw in path.read_text("utf-8").splitlines():
        try:
            rows.append(json.loads(raw))
        except ValueError:
            continue
    if not rows:
        return f"No usage recorded in {path}."
    tools = Counter(r["tool"] for r in rows)
    outcomes = Counter((r["tool"], r["outcome"]) for r in rows)
    out = [f"{len(rows):,} tool calls, {rows[0]['ts']} to {rows[-1]['ts']}", "", "tool|calls|empty|errors|median ms"]
    for tool, n in tools.most_common():
        ms = sorted(r["ms"] for r in rows if r["tool"] == tool)
        out.append(f"{tool}|{n}|{outcomes[tool, 'empty']}|{outcomes[tool, 'error']}|{ms[len(ms) // 2]}")

    def queries(want: set[str]) -> list[str]:
        c = Counter(
            str(r["args"]["query"]).strip().lower() for r in rows if r["outcome"] in want and r["args"].get("query")
        )
        return [f"{n}|{q}" for q, n in c.most_common(top)]

    out += ["", "Most asked topics (calls|query):", *queries({"ok", "empty", "error"})]
    out += ["", "Unanswered: no source matched (calls|query):", *(queries({"empty"}) or ["none"])]
    return "\n".join(out)
