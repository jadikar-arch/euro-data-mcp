---
name: test-tools
description: Test every tool of the europa-mcp server (CBS, Eurostat-family, agri-food, European Parliament, data.europa.eu tools) — offline unit tests plus a live smoke test that launches the real server over stdio like VS Code does. Use when asked to test, verify, or smoke-test the MCP tools, or after changing src/europa_mcp.
---

# Test the CBS MCP tools

Optional argument: one or more tool names to test only those (e.g. `/test-tools cbs_codes`).

## 1. Offline unit tests (mocked CBS API, fast)

```bash
uv run pytest -q
```

If a tool name was given, narrow with `-k <tool_name>`.

## 2. Live smoke test (real server, real CBS API)

```bash
.venv/bin/python .claude/skills/test-tools/scripts/smoke.py [tool_name ...]
```

The script starts `.venv/bin/europa-mcp` as a stdio subprocess (same as `.vscode/mcp.json`),
checks the tool list, then calls each tool with happy-path and error cases:

| Tool | Cases |
|---|---|
| cbs_search | topic match, `limit` honored, no-match message |
| cbs_describe | known id, case-insensitive id, unknown id error |
| cbs_codes | municipality lookup, place alias (Den Haag), newest year, measures, bad dimension |
| cbs_data | Amsterdam latest population (plausible value), unknown measure, over-broad query rejected |
| cbs_releases | next 30 days, `limit` honored |
| eurostat_* | search (Eurostat + DG TAXUD), describe (incl. DG EMPL id with `$`), geo code lookup, NL house price data, over-broad rejected |
| agri_* | endpoint list, NL pig prices, missing required param |
| ep_* | Dutch MEPs, roll-call votes on a sitting day, adopted-text search |
| find_data / country_guide | house prices (EU + NL), Dutch query, agri-food synonym, parliament; nl guide |
| dataeu_* | search, SPARQL (and write rejected), quality for NLD, use cases |

Every response must also stay under ~2k tokens. The first run can take up to a minute or two
while the search index builds.

## 3. Report

Show a compact PASS/FAIL table per tool with timings. For any FAIL:
- Decide whether it's a code bug, a stale expectation (CBS data changed, e.g. population range
  or dataset id), or a network problem (retry once).
- Point to the responsible code in `src/europa_mcp/countries/<cc>/` (e.g. `nl/cbs.py`, `eu/eurostat.py`), or `server.py`/`sourcemap.py` for find_data and propose a fix; don't change code
  unless the user asks.

When adding a tool to the server, add cases for it to `CASES` in `scripts/smoke.py` and to
`EXPECTED_TOOLS`.
