---
name: add-country
description: Add a European country's official open data API(s) to the europa-mcp server - probe the API, create countries/<cc>/ (tools, find_data map builder, hints.json, NOTES.md), write its model-facing skill in skills/<cc>/SKILL.md, and test it. Use when asked to add, connect or integrate a country, national statistics office or national open data portal.
---

# Add a country to europa-mcp

Argument: the country (name or ISO 3166-1 alpha-2 code) and, if known, the API URLs.

Layout of one country (copy from `templates/`; `de` is the reference implementation):

```
src/europa_mcp/countries/<cc>/__init__.py   contract: CODE, NAME, HINTS, SYNONYMS, register, map_builders, start, stop
src/europa_mcp/countries/<cc>/<source>.py   one module per API (tools + client code)
src/europa_mcp/countries/<cc>/mapping.py    find_data map builder(s)
src/europa_mcp/countries/<cc>/hints.json    hand-written source blurb, synonyms, keywords
src/europa_mcp/countries/<cc>/NOTES.md      probe findings (≤ 20 lines per API)
src/europa_mcp/skills/<cc>/SKILL.md         usage guide for the model (served as skill://<cc>/SKILL.md)
```

## 0. Is it a PxWeb office?

Many statistics offices (Sweden, Finland, Estonia, Latvia, Norway, Iceland, Slovenia, Croatia…) run PxWeb. For those
do not write tool code: copy `countries/lv/` (a `source.py` with one `PxSource`, `__init__.py` with the term list,
`mapping.py`, `hints.json`), set the base URL, licence, page-URL builder, rate limit (`min_interval`, `per_minute`),
`listing=True` when `<base>?query=*&filter=*` lists all tables, and an `archive` rule for discontinued-table
folders. Probe the rate limit (a 429 with `Retry-After` means a cap) and the licence on the office's own page, then
continue at step 3. Everything else (search, describe, codes, data, map rows, size and measure checks) is in
`europa_mcp/pxweb.py`.

## 1. Find and probe the APIs (no code yet)

- Typical sources: the national statistics office (often PxWeb, SDMX or OData), the national open
  data portal (often CKAN or DCAT-AP; many are already searchable via `dataeu_search`), the
  central bank, and the parliament. Prefer official, keyless, read-only APIs, and note any
  API key requirement.
- Check `src/europa_mcp/countries/eu/NOTES.md` first: if the country's portal is only a catalogue
  that data.europa.eu already harvests, a separate connector adds little.
- Probe with `curl -s URL | head -c 1500`; never dump full responses. For each API find: the
  catalogue endpoint (list tables with titles and periods), metadata (dimensions, codes),
  the data query syntax, paging and size limits, error shapes, the rate limit, and the languages
  the titles come in (is English available?).
- Reuse protocol code when the API family already exists here: SDMX 2.1 / JSON-stat →
  `countries/eu/eurostat.py` (`parse_structure`, `jsonstat_rows`); plain REST/JSON → `countries/de/genesis.py`.
- Write `NOTES.md`, then **stop and propose the tool list** to the user.

## 2. Implement

Copy `templates/country/*` to `src/europa_mcp/countries/<cc>/`, replace the `<…>` placeholders,
then add the module to `COUNTRIES` in `src/europa_mcp/countries/__init__.py`.

- **Tool names** are `<source>_<verb>` and must be unique server-wide: `<source>_search`,
  `_describe`, `_codes`, `_data` (e.g. `ssb_search` for Statistics Norway, `destatis_data`).
  Docstrings: at most 3 lines, saying *when* to use the tool.
- **Token rules** (same as every tool here): compact `|` tables via `common.compact_table`; strip
  envelopes and nulls; cap every result with `limit` and say when it is truncated; reject
  over-broad data queries before downloading; errors are `UserError("short hint")` via `@safe`;
  cache metadata (`web.Memo`).
- **HTTP:** use `web.fetch` / `web.fetch_json` (shared client, retries, short errors). Never
  print to stdout.
- **find_data map:** `mapping.py` returns one entry per table/endpoint:
  `{"source", "id", "title", "path" (topic path), "keywords", "period", "updated", "call"}`
  where `call` is the exact next tool call. Enrich `keywords` from whatever the API offers
  (theme tree, dimension names, code lists). Local-language titles need `SYNONYMS`
  (English → local terms, applied both ways) so English queries find them.
- **hints.json:** `sources` (one-line scope per source, shown by find_data), `synonyms`,
  `keywords` (`"<source>:<id prefix>": "extra words"`), `entries` (curated map rows, e.g. for
  tools without a catalogue).

## 3. Write the model-facing skill

Copy `templates/skill/SKILL.md` to `src/europa_mcp/skills/<cc>/SKILL.md`. The `## Profile` table (country, languages, APIs, access, licence, data types, geographic detail, tools, use instead) is required and tested. Add the country to the table in `skills/overview/SKILL.md`. Keep it under about 100
lines: when to use this country vs Eurostat, the workflow with real tool calls, a code table
(regions, periods, measures), and pitfalls you hit while testing. Verify every code and label
you write against the live API.

## 4. Test

- Offline: `tests/test_<cc>.py` with respx mocks (see `tests/test_eu.py`) for each tool's happy
  path, truncation and errors, plus the map builder.
- Add the tool names to `tests/test_server.py` and to `EXPECTED_TOOLS` and `CASES` in
  `.claude/skills/test-tools/scripts/smoke.py`, plus a `find_data` case in the local language.
- Add the country to `COUNTRY_TOOLS` / `COUNTRY_LABELS` in the smoke script, then run the `test-country` skill for it (offline tests, `smoke.py --country <cc>`, find_data ranking, quality checklist).
- Run `uv run pytest -q`, `uv run pytest -m live`, then the smoke script. Each response must stay
  under about 2k tokens.
- `uv run europa-mcp map --export /tmp/map.csv`, then check the new rows and that
  `find_data("<typical topic>")` ranks them sensibly.

## 5. Document

Add the country to the README (the "What can I ask?" examples and the sources table) and to the
`INSTRUCTIONS` country list (generated automatically from `COUNTRIES`).
