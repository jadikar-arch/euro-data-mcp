---
name: test-country
description: Test one country package of the europa-mcp server (eu, de, nl, or a newly added one) end to end - offline tests, live smoke cases, find_data ranking and a quality checklist for its tools, map, hints and skill guide. Local development only (not shipped). Use when asked to test, verify or review a single country, after changing src/europa_mcp/countries/<cc>/, or right after the add-country skill.
---

# Test one country

This skill is for testing on your own machine. It lives in `.claude/`, which the wheel, sdist and
Docker image all leave out, and the model-facing guides served to users are in `src/europa_mcp/skills/`.

Argument: the country code (`eu`, `de`, `nl`, ...). With none, test every country in turn.
To test all tools at once instead, use `test-tools`.

## 1. Offline tests (mocked APIs)

```bash
uv run pytest tests/test_<cc>.py tests/test_server.py tests/test_sourcemap.py -q
```

`eu` has its tests in `tests/test_eu.py`. Expect all to pass with no network. Then lint:
`uvx ruff check src tests && uvx ruff format --check src tests`.

## 2. Live smoke cases for the country

```bash
.venv/bin/python .claude/skills/test-tools/scripts/smoke.py --country <cc>
uv run pytest -m live tests/test_live.py -k <source>     # e.g. -k cbs
```

`--country` checks that the country's tools are registered, then runs its cases: the tools
named by its prefix (`COUNTRY_TOOLS` in `smoke.py`) plus its `find_data` / `country_guide`
cases (`COUNTRY_LABELS`). A new country needs an entry in both dicts and in `EXPECTED_TOOLS`.
Each response must stay under ~2k tokens; data answers end with a `source:` line.

An upstream 5xx (e.g. `api.tech.ec.europa.eu error 500`) is a network problem, not a code bug:
retry once, then report it as upstream.

## 3. find_data ranking

Build only the country's rows, then check the questions people would ask, in English and in the
local language:

```bash
EUROPA_CACHE_DIR=$TMPDIR/cc uv run python eval/run_eval.py --fresh   # full map; slow once
```

Look for: the headline table first for everyday questions (unemployment, inflation, population,
house prices, GDP), local-language and English wording both finding the same table, no rows
with empty `keywords`, no discontinued or duplicate tables flooding the top 3. Add the
questions to `eval/find_data_cases.json` (`ok` = ids that count as correct). Cases that name no
country can legitimately be won by Eurostat; make country-specific cases local-language or
name the source.

## 4. Quality checklist (read the code and one real answer per tool)

- Tool names are `<source>_<verb>`, unique server-wide; docstrings at most 3 lines.
- Answers are compact `|` tables, constant columns under `fixed:`, truncation says so.
- Over-broad queries are refused before downloading; errors are short `Error: ...` strings.
- Measure and column labels are unambiguous (no two rows with the same label and different values).
- `hints.json` has `sources` for every map builder; `SYNONYMS` cover the common topics.
- `skills/<cc>/SKILL.md` has the `## Profile` table, is under ~100 lines, and every code in it is verified against the live API; the country is in the table of `skills/overview/SKILL.md`.
- `country_guide("<cc>")` returns the guide; `tests/test_server.py` lists the country and its tools.
- README and DEVELOPMENT.md list the country; CHANGELOG has an entry.

## 5. Report

One table per country: step, PASS/FAIL, evidence (counts, timings, the failing output line).
For each FAIL say whether it is a code bug, a stale expectation (dataset id or value range
changed) or upstream, and point to the file in `src/europa_mcp/countries/<cc>/`. Do not change
code unless asked.
