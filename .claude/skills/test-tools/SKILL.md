---
name: test-tools
description: Test every tool of the europa-mcp server (Eurostat-family, agri-food, European Parliament, data.europa.eu tools) — offline unit tests plus a live smoke test that launches the real server over stdio like VS Code does. Use when asked to test, verify, or smoke-test the MCP tools, or after changing src/europa_mcp.
---

# Test the europa-mcp tools

Optional argument: one or more tool names to test only those (e.g. `/test-tools eurostat_data`).

## 1. Offline unit tests (mocked APIs, fast)

```bash
uv run pytest -q
```

If a tool name was given, narrow with `-k <tool_name>`.

## 2. Live smoke test (real server, real APIs)

```bash
.venv/bin/python .claude/skills/test-tools/scripts/smoke.py [tool_name ...]
```

The script starts `.venv/bin/europa-mcp` as a stdio subprocess (same as `.vscode/mcp.json`),
checks the tool list, then calls each tool with happy-path and error cases:

| Tool | Cases |
|---|---|
| eurostat_* | search (Eurostat + DG TAXUD), describe (incl. DG EMPL id with `$`), geo code lookup, NL house price data (with source line), over-broad rejected |
| agri_* | endpoint list, NL pig prices, missing required param |
| ep_* | Dutch MEPs, roll-call votes on a sitting day, adopted-text search |
| find_data / country_guide | house prices, headline ranking (unemployment rate), French query, agri-food synonym, parliament; removed-country message |
| dataeu_* | search (incl. `sort=newest`), preview error, SPARQL (and write rejected), quality for NLD, use cases |
| govdata_* | English query translated, Destatis values column, bad theme, Destatis dataset/preview redirect, population by state, CPI, unknown table; de guide and German find_data |

Every response must also stay under ~2k tokens. The first run can take up to a minute or two
while the find_data map builds. Data answers must end with a `source:` line.

## 3. Report

Show a compact PASS/FAIL table per tool with timings. For any FAIL:
- Decide whether it's a code bug, a stale expectation (source data changed, e.g. a value range
  or dataset id), or a network problem (retry once).
- Point to the responsible code in `src/europa_mcp/countries/<cc>/` (e.g. `eu/eurostat.py`, `de/genesis.py`), or `server.py`/`sourcemap.py` for find_data and propose a fix; don't change code
  unless the user asks.

When adding a tool to the server, add cases for it to `CASES` in `scripts/smoke.py` and to
`EXPECTED_TOOLS`.
