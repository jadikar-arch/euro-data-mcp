# Changelog

## 0.4.1 (2026-11-04)

- Published on PyPI: install with `uvx europa-mcp` (e.g. `claude mcp add europa -- uvx europa-mcp`).
- Short README focused on connecting Claude, ChatGPT, VS Code, Cursor and other MCP apps; technical
  details moved to `DEVELOPMENT.md`. Plainer wording ("open data", not "official data").
- Packaging: `mcp` declared as a dependency, `fastmcp` capped below 5, slimmer source distribution,
  Python 3.13/3.14 classifiers, absolute links so the PyPI page works.

## 0.4.0 (2026-10-31)

**The user chooses the dataset**
- `find_data` returns one ranked list across all sources: rank, match %, source, id, title,
  period, breakdowns (e.g. "age, sex, NUTS 2 regions") and the next call, plus a legend of the sources.
- In apps that support MCP elicitation, the ranked options open as a picker (plus "None of these")
  and the tool continues with the user's pick. Both protocol styles are handled: the 2026-07-28
  input-required round trip and the older in-call request. Elsewhere the list comes back with an
  instruction to show it to the user and wait for their choice. `ask_user=False` turns this off.
- Server instructions: no fetching before the user has chosen, unless they already named a dataset.
- Map: new `detail` column with each dataset's breakdowns (from the Eurostat metabase); older
  caches get the column and an immediate rebuild.

## 0.3.0 (2026-10-31)

**Search: map first, then the API, measured**
- `eurostat_search` now uses the same ranking as `find_data` (one search quality to measure).
- Eurostat entries carry their breakdowns from the metabase (age, sex, NUTS level, cities,
  industry, education…), so "… by region" questions reach regional datasets.
- Ranking: plural stemming, `R&D`, country names ignored, ENP and discontinued datasets last,
  Eurostat main tables preferred among equal matches; headline datasets win only when their own
  words answer the query. Broader everyday vocabulary (doctors → physicians, online shopping →
  internet purchases…) and more headline datasets.
- Evaluation: 178-question dev set (hit@3 77% → 99%) and a 45-question holdout never tuned on
  (56% → 69%); CI fails below 95% / 60%.
- Server instructions: start with `find_data`, pick by title/period/breakdowns, and check the title
  and `fixed:` line against the question before answering.

**Fixed**
- Map rows of removed sources (e.g. CBS after 0.2.0) are pruned on startup instead of lingering
  in existing caches and pointing to tools that no longer exist.

## 0.2.0 (2026-10-31)

**Breaking**
- Removed the Netherlands (CBS) package and its `cbs_*` tools, the `europa-mcp sync` command and
  the `CBS_*` environment variable fallbacks. Netherlands figures remain available through Eurostat.

**Added**
- `source:` line (official page + licence) at the end of every data answer: Eurostat and DG data
  browsers, agri-food API, European Parliament API, Destatis tables, previewed files.
- `dataeu_preview`: first rows of a CSV/JSON file of a data.europa.eu dataset; `dataeu_dataset`
  numbers its files.
- `dataeu_search`: `sort="newest"` and `language` for titles and descriptions.
- `find_data`: ~50 most-asked Eurostat datasets rank first ("unemployment rate" → `une_rt_m`, not
  the "unemployment trap" table); topic words in French, Spanish, Italian, Dutch and Polish.
- `eval/`: 53-question evaluation of `find_data` (hit@3 26% → 100%), run nightly in CI.
- Hosted mode: optional API keys (`EUROPA_API_KEYS`), per-client rate limiting, opt-in anonymous
  usage log (`EUROPA_USAGE_LOG`) and `europa-mcp usage` report of unanswered questions.
- EUPL-1.2 licence, "not affiliated with the EU" disclaimer in README and server instructions,
  GitHub Actions CI (unit tests on push, live tests + eval nightly, Docker build), non-root Docker user.

**Fixed**
- File previews: hostnames resolving to private addresses and redirects to them are refused
  (previously only literal private IPs were).
- `govdata_dataset`/`govdata_search` recognise Destatis tables listed under other publishers.

## 0.1.0

First version: CBS, Eurostat and DG APIs, agri-food, European Parliament, data.europa.eu, GovData
and Destatis.
