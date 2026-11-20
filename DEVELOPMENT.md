# Developer guide

Technical details for running, hosting and extending Europa. For setup as a user, see the [README](README.md).

## Hosting it online

*Needed to use Europa from ChatGPT or Claude in the browser.*

```bash
docker build -t europa-mcp .        # a few minutes; includes the search indexes
docker run -p 8000:8000 europa-mcp  # MCP endpoint: http://<host>:8000/mcp
```

Put it behind HTTPS (any cloud host such as Cloud Run, Fly.io or Railway, or a reverse proxy) and
share `https://<host>/mcp`. Requests are rate-limited per client IP (`EUROPA_RATE_LIMIT_RPS`,
default 5 per second, burst 20).

- **Login (optional):** the data is public, so no login is needed by default. To limit who can use
  your server, set `EUROPA_API_KEYS=key1,key2`; clients then send `Authorization: Bearer key1`.
  Claude.ai custom connectors only support OAuth, so leave this off if you connect from claude.ai.
- **Usage insights (optional):** set `EUROPA_USAGE_LOG=/data/usage.jsonl` to log each tool call
  anonymously (tool, query, found/not found, duration; no IP addresses or conversation text). Then
  `europa-mcp usage --log /data/usage.jsonl` lists the most-asked topics and the questions no source
  could answer, which shows what data people are missing.
- **Quick test without deploying:** run `uv run europa-mcp --transport http` from a checkout and expose it with `cloudflared tunnel --url http://localhost:8000`.

---

## Architecture: one package and one skill per country

```
src/europa_mcp/
  server.py         core: loads every country, serves the skills, find_data, country_guide, CLI
  sourcemap.py      the find_data map (SQLite FTS5) and its ranking
  common.py, web.py shared errors, text tables, settings, source lines and HTTP client (retries, short errors)
  preview.py        first rows of publishers' CSV/JSON files (public hosts only, redirects re-checked)
  usage.py          opt-in anonymous usage log and the `europa-mcp usage` report
  countries/
    __init__.py     COUNTRIES registry and the country contract
    eu/             Eurostat + DGs, agri-food, European Parliament, data.europa.eu
    de/             GovData (CKAN catalogue) and Destatis GENESIS tables
    nl/             CBS OData v4 tables
  skills/
    eu/SKILL.md     guide for the assistant: when to use which source, workflow, codes, pitfalls
    de/SKILL.md
```

Each `countries/<cc>/` package exposes `CODE`, `NAME`, `HINTS` (its `hints.json`), `SYNONYMS`,
`register(mcp)`, `map_builders()`, `start()` and `stop()`. It also keeps its API findings in its
own `NOTES.md`. The server serves every `skills/<cc>/SKILL.md` as an MCP resource
(`skill://<cc>/SKILL.md`), and through the `country_guide` tool for apps that don't show
resources to the model.

**Adding a country:** use the `add-country` Claude Code skill in `.claude/skills/add-country`
(probe the API, copy the templates, write the skill, test). Tool names are
`<source>_<verb>` (e.g. `govdata_search`) so they stay unique as countries are added.

## Tools

| Tool | Purpose |
|---|---|
| `find_data(query, sources=None, per_source=4, limit=10, ask_user=True)` | **Start here.** Ranks the best datasets/endpoints across all sources (rank, match %, source, id, title, period, breakdowns, next call) and **lets the user choose**: in apps that support MCP elicitation a picker opens with the ranked options; elsewhere the assistant shows the list and asks. |
| `country_guide(country)` | The country's skill text: sources, workflow, codes, pitfalls. |
| `eurostat_search(query, agency="eurostat", limit=10)` | Find Eurostat datasets (English). `agency`: `eurostat`, `empl`, `grow` or `taxud` (DG dissemination APIs). |
| `eurostat_describe(dataset_id, agency)` | Dimensions with the codes in use (SDMX `referencepartial`), period range, observation count. |
| `eurostat_codes(dataset_id, dimension, query=None, agency, limit=50)` | Code lookup, e.g. geo `Netherlands → NL`. |
| `eurostat_data(dataset_id, filters, agency, last_n, since, until, limit=500)` | JSON-stat values, newest first, with status flags. Over-broad queries are rejected before download. |
| `agri_endpoints(query=None)` | DG AGRI agri-food endpoints (prices, production, trade, CMEF indicators) and their params, read from the OpenAPI spec. |
| `agri_data(endpoint, params, limit=200)` | Rows from one endpoint; params are validated against the spec. |
| `ep_meps(name, country, group, limit=50)` | Current MEPs. |
| `ep_votes(date, query, roll_call_only, mep_id, language="en", limit=40)` | Plenary votes on a sitting day with counts, and optionally one MEP's vote. |
| `ep_query(endpoint, params, language="en", limit=10, offset=0)` | Any European Parliament API v2 GET endpoint, with labels in one language and nested data compacted. |
| `dataeu_search(query, country, format, catalogue, category, hvd, min_quality, sort="relevance", language="en", page, limit=10)` | Search data.europa.eu (1.9M datasets) with a short description per row. `sort="newest"` puts recently updated datasets first; `language` picks the title/description language. |
| `dataeu_facets(query, by, country, format, catalogue, category, hvd, min_quality, top=10)` | Dataset counts per catalogue, format, category, country, publisher, licence or quality, for picking filters. |
| `dataeu_dataset(dataset_id, language="en", max_files=15)` | Description, publisher, licence and numbered download URLs. |
| `dataeu_preview(dataset_id, file=1, limit=20)` | First rows of a CSV or JSON file of a dataset (reads at most 2 MB), with its licence. |
| `dataeu_sparql(query, limit=100)` | Read-only SPARQL SELECT/ASK on the portal's DCAT graph. |
| `dataeu_quality(scope, id)` | Metadata quality (MQA) score and coverage per metric: global, country (ISO3) or catalogue. |
| `dataeu_use_cases(query, country, sector, limit=10)` | Apps and projects built on EU open data. |
| `govdata_search(query, theme, publisher, format, level, page=0, limit=10)` | Search GovData, Germany's open data catalogue (168k datasets, German titles; English terms are translated). Filters: DCAT theme (`envi`, `soci`…), publisher, file format, level (federal/state/district/municipality). |
| `govdata_dataset(dataset_id, max_files=15)` | Description, publisher, licence, level and numbered files. |
| `govdata_preview(dataset_id, file=1, limit=20)` | First rows of a CSV or JSON file (reads at most 2 MB). |
| `govdata_table(table_id, query, last_n, limit=100)` | Values of a Destatis GENESIS table (e.g. `12411-0010`), newest first, filtered by label words. |
| `cbs_search(query, include_discontinued, limit=10)` | Find CBS tables by Dutch topic keywords (English terms are translated); the catalogue is cached and searched in memory. |
| `cbs_describe(dataset_id)` | A CBS table's dimensions (code counts, latest period) and measures. |
| `cbs_codes(dataset_id, dimension, query, limit=50)` | Look up region, period or measure codes by title (`Amsterdam` → `GM0363`). |
| `cbs_data(dataset_id, measures, filters, latest, limit=500)` | Values of a CBS table; refuses queries above ~100k rows. |
| `cbs_releases(days=14, limit=30)` | CBS tables getting new data soon. |

## Source map (`find_data`)

The APIs publish little "what is this about" metadata, so the server builds one searchable **map
table** (SQLite FTS5, `sourcemap.db` in the cache directory) with one row per dataset or endpoint:
`source | id | title | topic_path | period | updated | next_call | keywords`. Each source is
enriched from the best signal it has:

| Source | Rows | Enrichment |
|---|---|---|
| Eurostat | ~7,500 datasets | Theme path from the table-of-contents tree (e.g. *Economy and finance > Prices*); extra theme locations as keywords; ~50 most-asked datasets (unemployment, inflation, GDP…) marked as headline with everyday words |
| DG EMPL / GROW / TAXUD | ~40 | Dataflow names; per-country copies (`LMP_EXPME$HR`) collapsed into their parent |
| Agri-food | ~40 data endpoints | OpenAPI tag and summary, plus the values of the sector's code lookups (e.g. *Durum wheat*, *Feed barley* for `cereal/*`) |
| European Parliament | ~20 list endpoints + `ep_meps`/`ep_votes` | OpenAPI tag and description |
| data.europa.eu | its 4 tools | Hand-written |
| Destatis | ~3,000 GENESIS tables | Theme from GovData groups, keywords from the dataset tags (regions, statistic, measures) |
| CBS | ~1,290 regular tables | Dimension and measure titles and the description as keywords; 34 most-asked tables marked as headline (hints.json); English terms via `nl.SYNONYMS` |
| GovData | 13 themes + ~200 theme × publisher slices | 168k datasets are too many for one row each, so each row says what kind of data a publisher has on a theme (*Environment data from Land Schleswig-Holstein: 4,210 datasets*), with its top tags and formats and a ready `govdata_search` call |

Hand-written metadata lives in each country's `hints.json`: source descriptions, extra keywords,
synonyms (e.g. *pork → pigmeat*, *chômage → unemployment*) and, for the EU, a `headline` list of
the most-asked Eurostat datasets. Search also expands English ↔ local-language terms through each
country's `SYNONYMS` (for DE, a German list in `countries/de/__init__.py`), so German queries find
Eurostat datasets and English queries find Destatis tables. Ranking: share of query words matched,
then headline datasets (only when every word matched), then matches on the user's own words over
synonym matches, then BM25.

**How a question becomes data.** The map answers *which dataset?*; the live APIs answer *what
exactly is in it?* (`*_describe`, `*_codes`) and return the values (`*_data`), rejecting unknown
codes instead of guessing. `find_data` and `eurostat_search` share one ranking:

1. share of the query words matched (title, theme path, keywords, breakdowns, synonyms; plurals
   stemmed, `R&D` kept, country names ignored since they are filters, not topics);
2. headline datasets, but only when their own everyday words answer the query (*unemployment
   rate* → `une_rt_m`; *Part-time employment rate* is not the answer to *employment rate*);
3. EU-neighbourhood (ENP) copies and discontinued datasets (no data for 3+ years) last;
4. the user's own words over synonyms, title matches, then Eurostat's curated main tables, then BM25.

Breakdowns come from Eurostat's metabase (one file listing every dataset's dimensions), so
*"… by region"*, *"… by age"* or *"… in cities"* reach datasets that actually have those breakdowns.

**Search quality is measured**, with two question sets in `eval/` (several datasets can be
correct for one question; accepted ids come from catalogue titles):

| Set | Questions | hit@3 | hit@1 | Purpose |
|---|---|---|---|---|
| `find_data_cases.json` (dev) | 178 | 176 (99%) | 144 (81%) | tuned on: headline words, synonyms; CI fails below 95% |
| `find_data_holdout.json` | 45 | 31 (69%) | 19 (42%) | **never tuned on**: the honest estimate for new questions; CI fails below 60% |

Before this work the same holdout scored 25/45 (56%) and the dev set 137/178 (77%). The holdout
is the number to quote. To improve it without fooling yourself, add real questions from
`europa-mcp usage` to the dev set, fix them there, and occasionally write a fresh holdout.

```bash
uv run python eval/run_eval.py [--fresh] [--set holdout] [--min-hit3 0.95]
```

**End-to-end golden set:** [`eval/golden/`](eval/golden/README.md) has 20 questions with expected
answers fetched from the official APIs (Eurostat, regional, city, Destatis, agri-food, Parliament,
DG TAXUD, data.europa.eu, a Spanish question and a no-data trap), a score sheet and a scorer, for
comparing how different models and apps use the server.

The map is rebuilt in the background every `EUROPA_REFRESH_HOURS` (default 6).
If one source fails, its previous rows are kept. To build it by hand or export it as a CSV for review:

```bash
uv run europa-mcp map --export source_map.csv
```

EU sources used (one entry per API; probe findings in `countries/eu/NOTES.md`):

| Source | Base URL |
|---|---|
| Eurostat | `https://ec.europa.eu/eurostat/api/dissemination` |
| DG EMPL / GROW / TAXUD | `https://webgate.ec.europa.eu/{empl,grow,taxation_customs}/redisstat/api/dissemination` |
| Agri-food (DG AGRI) | `https://api.tech.ec.europa.eu/agrifood/api` |
| European Parliament | `https://data.europarl.europa.eu/api/v2` |
| data.europa.eu search, SPARQL, MQA, use cases | `https://data.europa.eu/api/hub/search`, `/sparql`, `/api/mqa/cache`, `/en/export-use-cases` |

German sources (probe findings in `countries/de/NOTES.md`):

| Source | Base URL |
|---|---|
| GovData (CKAN action API) | `https://ckan.govdata.de/api/3/action` |
| CBS OData v4 (keyless JSON) | `https://datasets.cbs.nl/odata/v1` |
| Destatis GENESIS table downloads (keyless CSV) | `https://genesis.destatis.de/genesisWS/downloads/00/tables/<id>_00.csv` |

Not wrapped: the data.europa.eu registry (`/api/hub/repo`) serves the same metadata as search, but as slow RDF. The MQA reporter only serves PDFs, so `dataeu_quality` links to it instead. SHACL validation is publisher tooling and currently returns 503.

The output is compact text with `|` separators, and values that are the same in every row are
printed once under `fixed:`. Every data answer ends with a `source:` line (official page + licence).
A typical answer takes 3–4 calls of under 400 tokens each:

```
find_data("unemployment rate")                        → une_rt_m Unemployment by sex and age - monthly data
eurostat_codes("une_rt_m", "geo", "Germany")          → DE|Germany
eurostat_data("une_rt_m", {"geo": ["DE"], "sex": ["T"], "age": ["TOTAL"], "unit": ["PC_ACT"], "s_adj": ["SA"]}, last_n=1)
                                                      → 2026-09|4.1
                                                        source: https://ec.europa.eu/eurostat/databrowser/view/une_rt_m/… · licence: CC BY 4.0
```

## Configuration

| Env var | Default | |
|---|---|---|
| `EUROPA_CACHE_DIR` | user cache dir (`europa-mcp`) | Where the source map (`sourcemap.db`) is stored |
| `EUROPA_REFRESH_HOURS` | `6` | Refresh interval of the map |
| `EUROPA_RATE_LIMIT_RPS` | `5` | HTTP mode: sustained requests per second per client IP (burst 20) |
| `EUROPA_API_KEYS` | unset | HTTP mode: comma-separated bearer tokens; when set, every request needs one |
| `EUROPA_USAGE_LOG` | unset | Path of the anonymous JSONL usage log (see [Hosting it online](#hosting-it-online)) |
| `EUROPA_HOST` / `PORT` | `127.0.0.1` / `8000` | HTTP bind address |
| `EUROPA_LOG_LEVEL` | `INFO` | Logs go to stderr only |

## Development

```bash
uv sync
uv run prek install      # git hook: ruff lint + format, file checks, unit tests on every commit
uv run prek run --all-files
uv run pytest            # mocked HTTP (respx)
uv run pytest -m live    # end-to-end smoke tests against the real APIs
uv run python eval/run_eval.py   # find_data search quality (hit@1 / hit@3)
npx @modelcontextprotocol/inspector uv run europa-mcp
```

Put the server command first. The Inspector parses flags such as `uvx --from .` as its own options.
API findings are in each `countries/<cc>/NOTES.md`; core notes in [NOTES.md](NOTES.md).

The package is on PyPI as [`europa-mcp`](https://pypi.org/project/europa-mcp/), so users run
`uvx europa-mcp`. To run your own checkout instead, use `uvx --from /path/to/checkout europa-mcp`;
for the latest unreleased code, `uvx --from git+https://github.com/jadikar-arch/euro-data-mcp europa-mcp`.

## Releasing to PyPI

1. Raise `version` in `pyproject.toml` and add a section to `CHANGELOG.md`.
2. `rm -rf dist && uv build`
3. `uv publish` (token in `UV_PUBLISH_TOKEN`; never commit it).

A version number can be published only once.
