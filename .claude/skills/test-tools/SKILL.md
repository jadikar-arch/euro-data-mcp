---
name: test-tools
description: Test every tool of the CBS MCP server (search_datasets, describe_dataset, list_codes, get_observations, upcoming_releases) — offline unit tests plus a live smoke test that launches the real server over stdio like VS Code does. Use when asked to test, verify, or smoke-test the MCP tools, or after changing src/cbs_mcp.
---

# Test the CBS MCP tools

Optional argument: one or more tool names to test only those (e.g. `/test-tools list_codes`).

## 1. Offline unit tests (mocked CBS API, fast)

```bash
uv run pytest -q
```

If a tool name was given, narrow with `-k <tool_name>`.

## 2. Live smoke test (real server, real CBS API)

```bash
.venv/bin/python .claude/skills/test-tools/scripts/smoke.py [tool_name ...]
```

The script starts `.venv/bin/cbs-mcp` as a stdio subprocess (same as `.vscode/mcp.json`),
checks the tool list, then calls each tool with happy-path and error cases:

| Tool | Cases |
|---|---|
| search_datasets | topic match, `limit` honored, no-match message |
| describe_dataset | known id, case-insensitive id, unknown id error |
| list_codes | municipality lookup, place alias (Den Haag), newest year, measures, bad dimension |
| get_observations | Amsterdam latest population (plausible value), unknown measure, over-broad query rejected |
| upcoming_releases | next 30 days, `limit` honored |

Every response must also stay under ~2k tokens. The first run can take up to a minute or two
while the search index builds.

## 3. Report

Show a compact PASS/FAIL table per tool with timings. For any FAIL:
- Decide whether it's a code bug, a stale expectation (CBS data changed, e.g. population range
  or dataset id), or a network problem (retry once).
- Point to the responsible code in `src/cbs_mcp/server.py` and propose a fix; don't change code
  unless the user asks.

When adding a tool to the server, add cases for it to `CASES` in `scripts/smoke.py` and to
`EXPECTED_TOOLS`.
