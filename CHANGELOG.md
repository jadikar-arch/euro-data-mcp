# Changelog

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
