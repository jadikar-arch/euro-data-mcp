"""Live smoke test: launch the real cbs-mcp server over stdio and exercise every tool.

Usage: .venv/bin/python .claude/skills/test-tools/scripts/smoke.py [tool_name ...]
Exit code 0 = all checks passed, 1 = at least one failed.
"""

from __future__ import annotations

import asyncio
import re
import sys
import time
from collections.abc import Callable
from pathlib import Path

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

ROOT = Path(__file__).resolve().parents[4]
SERVER = ROOT / ".venv" / "bin" / "cbs-mcp"
MAX_CHARS = 8000  # ~2k tokens; tool outputs should stay well under this
EXPECTED_TOOLS = {
    "search_datasets", "describe_dataset", "list_codes", "get_observations", "upcoming_releases",
}

Check = Callable[[str], str | None]  # returns an error message, or None when OK


def contains(*needles: str) -> Check:
    return lambda out: next((f"missing {n!r}" for n in needles if n not in out), None)


def starts(prefix: str) -> Check:
    return lambda out: None if out.startswith(prefix) else f"expected to start with {prefix!r}"


def no_error(out: str) -> str | None:
    return f"tool returned {out.splitlines()[0]!r}" if out.startswith("Error") else None


def max_rows(n: int) -> Check:
    def check(out: str) -> str | None:
        rows = [line for line in out.splitlines()[1:] if not line.startswith("#")]
        return None if len(rows) <= n else f"{len(rows)} rows > limit {n}"
    return check


def amsterdam_population(out: str) -> str | None:
    last = out.strip().splitlines()[-1]
    try:
        v = int(last.split("|")[-1])
    except ValueError:
        return f"last line is not a number: {last!r}"
    return None if 800_000 < v < 1_200_000 else f"implausible population {v}"


def latest_year(out: str) -> str | None:
    lines = out.splitlines()
    ok = len(lines) > 1 and re.fullmatch(r"\d{4}JJ00", lines[1].split("|")[0])
    return None if ok else f"expected a year code like 2025JJ00, got {lines[1:2]}"


def releases(out: str) -> str | None:
    if out.startswith("No releases scheduled") or out.startswith("date|id|title"):
        return None
    return "unexpected format"


# (tool, label, args, checks)
CASES: list[tuple[str, str, dict, list[Check]]] = [
    ("search_datasets", "population tables", {"query": "bevolking regio"},
     [no_error, starts("id|title|period|status|modified"), contains("37230ned")]),
    ("search_datasets", "limit respected", {"query": "bevolking", "limit": 3},
     [no_error, max_rows(3)]),
    ("search_datasets", "no match", {"query": "xyzzyqqq"},
     [starts("No datasets match")]),
    ("describe_dataset", "37230ned", {"dataset_id": "37230ned"},
     [no_error, starts("37230ned:"), contains("RegioS|", "Perioden|", "M000098")]),
    ("describe_dataset", "case-insensitive id", {"dataset_id": "37230NED"},
     [no_error, starts("37230ned:")]),
    ("describe_dataset", "unknown id", {"dataset_id": "nope0000"},
     [starts("Error: Unknown dataset")]),
    ("list_codes", "municipality", {"dataset_id": "37230ned", "dimension": "RegioS", "query": "Amsterdam"},
     [no_error, contains("GM0363|Amsterdam")]),
    ("list_codes", "alias Den Haag", {"dataset_id": "37230ned", "dimension": "RegioS", "query": "Den Haag"},
     [no_error, contains("GM0518")]),
    ("list_codes", "newest year", {"dataset_id": "37230ned", "dimension": "Perioden", "query": "JJ", "limit": 1},
     [no_error, latest_year]),
    ("list_codes", "measures", {"dataset_id": "37230ned", "dimension": "Measures", "query": "bevolking"},
     [no_error, contains("M000098")]),
    ("list_codes", "bad dimension", {"dataset_id": "37230ned", "dimension": "Nope"},
     [starts("Error: Unknown dimension")]),
    ("get_observations", "Amsterdam latest population",
     {"dataset_id": "37230ned", "measures": ["M000098"], "filters": {"RegioS": ["GM0363"]}, "latest": True},
     [no_error, amsterdam_population]),
    ("get_observations", "unknown measure",
     {"dataset_id": "37230ned", "measures": ["M999999"], "filters": {"RegioS": ["GM0363"]}},
     [starts("Error: Unknown measure")]),
    ("get_observations", "too broad rejected", {"dataset_id": "37230ned"},
     [starts("Error: query too broad")]),
    ("upcoming_releases", "next 30 days", {"days": 30, "limit": 10},
     [no_error, releases, max_rows(10)]),
]


async def main(only: set[str]) -> int:
    if not SERVER.exists():
        print(f"FAIL server binary not found: {SERVER} (run `uv sync`)")
        return 1
    transport = StdioTransport(command=str(SERVER), args=[], cwd=str(ROOT))
    failures = 0
    async with Client(transport, timeout=180) as c:
        tools = {t.name for t in await c.list_tools()}
        if not only:
            ok = tools == EXPECTED_TOOLS
            failures += not ok
            print(f"{'PASS' if ok else 'FAIL'}  list_tools: {sorted(tools)}")
        for tool, label, args, checks in CASES:
            if only and tool not in only:
                continue
            t0 = time.perf_counter()
            try:
                r = await c.call_tool(tool, args, raise_on_error=False)
                out = "".join(getattr(b, "text", "") for b in r.content)
                errs = [e for chk in checks if (e := chk(out))]
            except Exception as e:  # noqa: BLE001
                out, errs = "", [f"{type(e).__name__}: {e}"]
            if len(out) > MAX_CHARS:
                errs.append(f"response too large ({len(out)} chars)")
            dt = time.perf_counter() - t0
            status = "FAIL" if errs else "PASS"
            failures += bool(errs)
            print(f"{status}  {tool} / {label}  ({dt:.1f}s, ~{len(out) // 4} tok)")
            for e in errs:
                print(f"      - {e}")
            if errs and out:
                print("      output: " + out[:400].replace("\n", "\n              "))
    total = sum(1 for t, *_ in CASES if not only or t in only) + (0 if only else 1)
    print(f"\n{total - failures}/{total} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(set(sys.argv[1:]))))
