# Changelog

## Unreleased

- **Netherlands is back** as a country package (`nl`): CBS OData v4 with `cbs_search`, `cbs_describe`,
  `cbs_codes`, `cbs_data` and `cbs_releases`. It follows the same rules as `de`: the shared web client,
  a `source:` line on every data answer, a find_data map (one row per regular table, ~1,290, with
  dimension and measure titles as keywords, 34 headline tables) and a `country_guide("nl")` skill.
  No local index or background sync any more: the catalogue is cached for 12 hours and searched in memory.
- `cbs_data`: a measure title that repeats inside a table is prefixed with its group
  (`Werkloze beroepsbevolking: Seizoengecorrigeerd`). Before, four rows were all called
  `Seizoengecorrigeerd` with different values.
- OData errors are shortened to their message (`Could not find a property named 'Regio'`).
- `country_guide()` without an argument lists every country, its sources and what else is available.
  `find_data` puts the named country's own source first and says when only Eurostat covers a country
  (`# No national source for geo=SK yet ...`).
- `find_data` without a country in the question and matches from several countries adds
  `# No country named. Matches exist for: …` so the agent offers the countries (or an EU-wide
  comparison) before fetching. Option labels start with the country (`Netherlands · CBS 37230ned`).
- Every country skill starts with the same `## Profile` table (country, languages, APIs, access, licence,
  data types, geographic detail, tools); a test checks it and that the tools it names exist. New index skill
  `skill://overview/SKILL.md` (also `country_guide("overview")`): covered countries, how to pick one, the workflow.
- Dutch city and province names are ignored as query words, like country names.

## 0.4.2 (2026-11-05)

Fixes from a live test of all tools (2026-11-05). Data values were already correct; these are about
validation, search relevance and output shape.

**Could give confidently wrong answers**
- `eurostat_data`: checks time and size arguments before calling the API. An inverted range
  (`since` after `until`), `last_n` together with `since`/`until`, malformed periods (`2025-13`),
  and `limit`/`last_n` below 1 return a clear error. Before, an inverted range came back as a
  series with a silent gap. An empty result now says which period the dataset covers.
- `dataeu_search(sort="newest")`: takes the 100 most relevant matches and sorts those by date.
  Upstream's date sort matched any word and ignored relevance (EV charging stations → sewage plants).
- `find_data` ranking:
  - `capita` no longer matches `capital`.
  - Titles with a query word only in negated form (`non-household`) rank lower.
  - Price and "latest" questions prefer live sources (Agrifood weekly prices) over tables that
    ended more than a year ago.
  - Phrase synonyms (`air quality` → particulate matter, NO2…; `per capita` → per inhabitant),
    `GDP` → gross domestic product, and youth / rate words in French, Spanish, Italian, Dutch and
    German.
  - find_data eval: dev hit@3 99% (hit@1 81% → 82%), holdout hit@3 69% → 73% (hit@1 42% → 47%).

**Failures and extra parsing**
- `ep_query`: output budget (~12k characters) with an `offset` hint; `meetings` is one line per
  sitting day (56k → 3k characters for a year); `parliamentary-questions` shows date, author,
  answered and title.
- `agri_data`: checks parameter formats (`beginDate must be dd/mm/yyyy (got 2026-09-01)`) before
  the API turns them into a bare 500; prices get a numeric `value` and a `currency` column.
- `ep_votes`: rows in voting order, labels keep the amendment number (rapporteur names go first),
  same-label budget lines get their amendment number, and a `vote_id` column.
- `govdata_preview` / `dataeu_preview`: large CSVs also show their last rows, via a range request
  or, when the server ignores ranges, by reading through files up to 25 MB.

**Polish**
- `eurostat_data`: newest first for the DG agencies (TAXUD came oldest-first).
- `eurostat_describe`: labels that clipping would make identical are shown in full.
- `dataeu_dataset`: descriptions without HTML tags or entities.
- `dataeu_sparql`: syntax errors as one short line.
- `dataeu_use_cases`: a footer with the years the listed cases were published.
- `country_guide`: for countries without a guide, points to `dataeu_search(country=…)`.

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
