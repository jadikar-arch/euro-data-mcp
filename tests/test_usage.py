"""The opt-in usage log and its report."""

import json

from fastmcp import Client

from europa_mcp import server
from europa_mcp.usage import UsageLog, outcome, report


def test_outcome_classifies_answers():
    assert outcome("Error: boom") == "error"
    assert outcome("No mapped source matches 'x'.") == "empty"
    assert outcome("id|title\n1|t") == "ok"


async def test_log_records_calls_without_identifying_callers(tmp_path, monkeypatch):
    path = tmp_path / "usage.jsonl"
    log = UsageLog(path)
    server.mcp.add_middleware(log)
    try:
        async with Client(server.mcp) as c:
            await c.call_tool("country_guide", {"country": "atlantis"}, raise_on_error=False)
            await c.call_tool("country_guide", {"country": "eu"}, raise_on_error=False)
    finally:
        server.mcp.middleware.remove(log)
    rows = [json.loads(x) for x in path.read_text().splitlines()]
    assert [(r["tool"], r["args"], r["outcome"]) for r in rows] == [
        ("country_guide", {"country": "atlantis"}, "empty"),
        ("country_guide", {"country": "eu"}, "ok"),
    ]
    assert set(rows[0]) == {"ts", "tool", "args", "outcome", "ms"}  # no IP, token or session id


def test_report_lists_unanswered_topics(tmp_path):
    path = tmp_path / "usage.jsonl"
    lines = [
        {"ts": "2026-10-30T10:00:00Z", "tool": "find_data", "args": {"query": "Ferry delays"}, "outcome": "empty", "ms": 40},
        {"ts": "2026-10-30T10:01:00Z", "tool": "find_data", "args": {"query": "ferry delays"}, "outcome": "empty", "ms": 50},
        {"ts": "2026-10-30T10:02:00Z", "tool": "find_data", "args": {"query": "inflation"}, "outcome": "ok", "ms": 30},
    ]
    path.write_text("\n".join(json.dumps(x) for x in lines) + "\nnot json\n")
    out = report(path)
    assert "find_data|3|2|0|40" in out
    assert out.split("Unanswered")[1].splitlines()[1] == "2|ferry delays"
