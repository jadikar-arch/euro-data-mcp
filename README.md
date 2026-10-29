# Europa: ask a question, get real European data to analyse

**European open data is hard to find, even for data scientists. Europa lets you get it by asking
in plain language, so your AI assistant can analyse it and build dashboards on real numbers.**

Official data about Europe and its countries is public, but it is spread across hundreds of
portals, thousands of tables with cryptic codes, and APIs in different formats and languages.
Finding the right table and pulling the right slice can take hours. Ask ChatGPT or Claude
instead, and they can't fetch the data at all: they guess from old training knowledge.

Europa closes that gap. It connects AI assistants such as **Claude**, **ChatGPT**,
**VS Code Copilot** and **Cursor** to official sources: national statistics offices and the EU's
own sources (Eurostat, the European Commission, the European Parliament and the EU open data
portal). You ask a question; the assistant finds the right dataset, retrieves the **latest
official figures**, and tells you which table it used. From there it can analyse, compare,
chart, or build a dashboard on data you can trace back to the source.

### Countries and sources

| | Sources | Good for |
|---|---|---|
| 🇪🇺 **EU** | Eurostat, European Commission (labour market, tax, postal, agri-food markets), European Parliament, data.europa.eu | Comparing countries, EU totals, farm prices, how the Parliament voted, finding open datasets |
| 🇳🇱 **Netherlands** | CBS (Statistics Netherlands) | Dutch figures down to municipality and neighbourhood |
| 🇩🇪 **Germany** | Destatis (Federal Statistical Office) tables, GovData (168,000 open datasets) | German figures down to state and district; finding German open data files, maps and services |

More countries are being added. Each country is a self-contained package with its own guide for the
assistant (see [For developers](#for-developers)).

---

## What can I ask?

Write the way you'd ask a colleague. You can ask in any language. If you don't know which source
has the answer, just ask; the assistant first looks up which source fits best.

| You ask | The assistant finds |
|---|---|
| *"How many people live in Amsterdam?"* | **944,322** (August 2026), from the CBS table *Bevolkingsontwikkeling; regio per maand* |
| *"What did an average house cost in Utrecht last year?"* | **€549,113** (2025), from CBS *Bestaande koopwoningen; gemiddelde verkoopprijzen* |
| *"Compare house price growth in the Netherlands and Germany"* | Eurostat's house price index, quarter by quarter |
| *"What is the implicit tax rate on labour in the Netherlands?"* | **31.87%** (2024), from the European Commission's tax data |
| *"What do Dutch farmers get for their pigs this month?"* | Weekly EU pig prices per country |
| *"Which Dutch MEPs are in Renew, and how did Parliament vote on 8 July?"* | MEP list and vote results from the European Parliament |
| *"Find open datasets about air quality in the Netherlands"* | Datasets and download links from data.europa.eu |
| *"How many people live in Bavaria?"* | **13,245,503** (31 Dec 2025), from Destatis table *12411-0010 Bevölkerung: Bundesländer* |
| *"What was German inflation last month?"* | **+3.3%** (September 2026), from Destatis *61111-0002 Verbraucherpreisindex* |
| *"What open data does Hamburg publish about cycling?"* | Datasets, files and map services from GovData |

> **Good to know:** national sources often publish in their own language (CBS in Dutch). Your
> assistant translates, so you can ask and get answers in English or any other language.

---

## How to set it up

Choose the app you use. Each setup takes about 5 minutes and only has to be done once.

### Step 1: install the helper program "uv" (needed for options A–C)

This small program downloads and runs the tool for you. You need it for Claude Desktop, VS Code and
Cursor. If you use **ChatGPT or Claude in the browser**, skip to [Option D](#option-d-chatgpt-or-claude-in-your-web-browser).

**Mac:** open the **Terminal** app (press `⌘ + Space`, type *Terminal*, press Enter), paste this
line and press Enter:

```
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows:** open **PowerShell** (Start menu → type *PowerShell*), paste this line and press Enter:

```
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

When it says it's done, **close the window**.

> The commands below download the tool straight from GitHub (it isn't on PyPI yet). While the
> repository is private, only people with access to it can install it this way.

### Option A: Claude Desktop app

1. Open Claude Desktop and go to **Settings → Developer → Edit Config**.
   This opens a file called `claude_desktop_config.json`.
2. Replace everything in the file with the text below (if the file already has other servers in
   it, add only the `"europa"` part):

   ```json
   {
     "mcpServers": {
       "europa": {
         "command": "uvx",
         "args": ["--from", "git+https://github.com/jadikar-arch/cbs-fastmcp-server", "europa-mcp"]
       }
     }
   }
   ```

3. Save the file and **quit Claude completely**, then reopen it. On a Mac, use Claude → Quit;
   closing the window isn't enough.
4. Start a new chat and ask: *"How many people live in Amsterdam? Use the europa tools."*

The first time, Claude asks for permission to use the europa tools. Click **Allow**.

### Option B: VS Code (with GitHub Copilot)

1. Open your project folder in VS Code.
2. Create a folder named `.vscode` (if it doesn't exist) with a file named `mcp.json` inside it.
3. Paste this into the file and save:

   ```json
   {
     "servers": {
       "europa": { "type": "stdio", "command": "uvx", "args": ["--from", "git+https://github.com/jadikar-arch/cbs-fastmcp-server", "europa-mcp"] }
     }
   }
   ```

4. A small **Start** button appears above the `"europa"` line. Click it.
5. Open Copilot Chat, switch it to **Agent** mode, and ask your question.

### Option C: Cursor

1. Go to **Cursor Settings → MCP → Add new MCP server**. Or create a file
   `~/.cursor/mcp.json` (for all projects) or `.cursor/mcp.json` (for this project only).
2. Paste this and save:

   ```json
   {
     "mcpServers": {
       "europa": { "type": "stdio", "command": "uvx", "args": ["--from", "git+https://github.com/jadikar-arch/cbs-fastmcp-server", "europa-mcp"] }
     }
   }
   ```

3. Check that **europa** shows a green dot in the MCP settings, then ask your question in the chat.

### Option D: ChatGPT or Claude in your web browser

Websites can't start programs on your computer, so for this option the tool has to run on a
**server on the internet**. Someone technical (a colleague or your IT team) does that once; see
[Hosting it online](#hosting-it-online). They give you a web address that ends in `/mcp`, for
example `https://europa.example.com/mcp`.

**Claude (claude.ai):**
1. Go to **Customize → Connectors**, click **+**, and choose **Add custom connector**.
2. Give it a name (*Europa*), paste the web address, and click **Add**.
3. In a chat, click **+** → **Connectors** and switch **Europa** on.

**ChatGPT:**
1. Go to **Settings → Apps → Advanced settings** and turn on **Developer mode**.
2. Click **Create** to add a connector. Name it *Europa*, paste the web address, and set
   authentication to **None**.
3. In a chat, enable the Europa connector and ask your question.

> OpenAI moves these menus around from time to time, and custom connectors aren't available on
> every ChatGPT plan. If you can't find the option, search the OpenAI help center for
> *"developer mode connectors"*.

<details>
<summary><b>Other apps (Claude Code, OpenCode, …)</b></summary>

**Claude Code** (terminal):

```
claude mcp add --transport stdio europa -- uvx --from git+https://github.com/jadikar-arch/cbs-fastmcp-server europa-mcp
```

**OpenCode**: add to `opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "europa": { "type": "local", "command": ["uvx", "--from", "git+https://github.com/jadikar-arch/cbs-fastmcp-server", "europa-mcp"], "enabled": true }
  }
}
```

**Any app that supports MCP:** run the command `uvx --from git+https://github.com/jadikar-arch/cbs-fastmcp-server europa-mcp` (local), or connect to the web
address `https://<your-server>/mcp` (online).

</details>

---

## Tips for better answers

- **Mention the place and the time:** *"in Eindhoven"*, *"in Germany and France"*, *"in 2024"*,
  *"the latest figures"*.
- **Ask for the source** if you want to check it: *"Which table did you use?"* You can look it up
  on the source's website (e.g. [opendata.cbs.nl](https://opendata.cbs.nl) or
  [ec.europa.eu/eurostat](https://ec.europa.eu/eurostat/databrowser)).
- **Compare like with like.** For comparisons between countries, ask for Eurostat figures: they use
  the same definitions everywhere. National offices often have more detail for their own country.
- **Mind the definitions.** *"Population on 1 January"* differs from *"average population over the
  year"*. Ask the assistant to explain the definition if it matters.

## Common questions

**The very first question is a bit slow.**
The first time, the tool downloads the lists of available tables (about 4,900 from CBS, 8,000
from Eurostat and 3,000 from Destatis) so it can search them. This takes up to a minute. Later questions are fast.

**The assistant says it can't find the tools.**
- Restart the app completely after changing the settings.
- Make sure Step 1 finished. On a Mac, open Terminal and type `uvx --version`; it should print a
  version number.
- **Mac:** if it still doesn't work, the app may not find `uvx`. In Terminal, type `which uvx` and
  copy the result (something like `/Users/yourname/.local/bin/uvx`). Paste that full path in the
  settings file instead of just `"uvx"`.

**The assistant gives an answer, but not from these sources.**
Add *"use the europa tools"* to your question.

**Are new figures included?**
Yes. The tool always fetches figures directly from the source. Its lists of tables update
themselves every 6 hours, so brand-new tables become searchable the same day.

**Does this cost anything? Is my data shared?**
The tool is free, and the data is public. The tool sends only data requests to the sources. Your
conversation stays between you and your AI app, as usual.

**What can't it do?**
It only knows what the connected sources publish (see [Countries and sources](#countries-and-sources)).
Figures are as recent as the sources have published them, usually a few weeks to months behind.

---

## Hosting it online

*For the technical person setting up Option D.*

```bash
docker build -t europa-mcp .        # a few minutes; includes the search indexes
docker run -p 8000:8000 europa-mcp  # MCP endpoint: http://<host>:8000/mcp
```

Put it behind HTTPS (any cloud host such as Cloud Run, Fly.io or Railway, or a reverse proxy) and
share `https://<host>/mcp`. No login is needed because the data is public. Requests are rate-limited
(`EUROPA_RATE_LIMIT_RPS`, default 5 per second). To try it quickly without deploying, run
`uv run europa-mcp --transport http` from a checkout and expose it with `cloudflared tunnel --url http://localhost:8000`.

---

## For developers

<details>
<summary><b>Architecture, tools and configuration</b></summary>

### Architecture: one package and one skill per country

```
src/europa_mcp/
  server.py         core: loads every country, serves the skills, find_data, country_guide, CLI
  sourcemap.py      the find_data map (SQLite FTS5) and its ranking
  common.py, web.py shared errors, text tables, settings and HTTP client (retries, short errors)
  countries/
    __init__.py     COUNTRIES registry and the country contract
    eu/             Eurostat + DGs, agri-food, European Parliament, data.europa.eu
    nl/             CBS (OData client, local search index, tools)
    de/             GovData (CKAN catalogue) and Destatis GENESIS tables
  skills/
    eu/SKILL.md     guide for the assistant: when to use which source, workflow, codes, pitfalls
    nl/SKILL.md
    de/SKILL.md
```

Each `countries/<cc>/` package exposes `CODE`, `NAME`, `HINTS` (its `hints.json`), `SYNONYMS`,
`register(mcp)`, `map_builders()`, `start()` and `stop()`. It also keeps its API findings in its
own `NOTES.md`. The server serves every `skills/<cc>/SKILL.md` as an MCP resource
(`skill://<cc>/SKILL.md`), and through the `country_guide` tool for apps that don't show
resources to the model.

**Adding a country:** use the `add-country` Claude Code skill in `.claude/skills/add-country`
(probe the API, copy the templates, write the skill, test). Tool names are
`<source>_<verb>` (e.g. `cbs_search`) so they stay unique as countries are added.

### Tools

| Tool | Purpose |
|---|---|
| `find_data(query, sources=None, per_source=3, limit=12)` | **Start here when unsure which source fits.** Searches the source map (below) and returns the best datasets/endpoints per source, each with the exact next call. |
| `country_guide(country)` | The country's skill text: sources, workflow, codes, pitfalls. |
| `cbs_search(query, catalog="CBS", include_discontinued=False, limit=10)` | Find CBS tables by topic. Dutch keywords work best, and common English terms are translated. |
| `cbs_describe(dataset_id)` | A table's measures and dimensions, with code counts and the latest period. |
| `cbs_codes(dataset_id, dimension, query=None, limit=50)` | Code lookup, e.g. `Amsterdam → GM0363`. Use `"Measures"` for measure codes. |
| `cbs_data(dataset_id, measures, filters, latest=False, limit=500)` | Values. `latest=true` returns the newest period with data. |
| `cbs_releases(days=14, limit=30)` | The CBS release calendar. |
| `eurostat_search(query, agency="eurostat", limit=10)` | Find Eurostat datasets (English). `agency`: `eurostat`, `empl`, `grow` or `taxud` (DG dissemination APIs). |
| `eurostat_describe(dataset_id, agency)` | Dimensions with the codes in use (SDMX `referencepartial`), period range, observation count. |
| `eurostat_codes(dataset_id, dimension, query=None, agency, limit=50)` | Code lookup, e.g. geo `Netherlands → NL`. |
| `eurostat_data(dataset_id, filters, agency, last_n, since, until, limit=500)` | JSON-stat values, newest first, with status flags. Over-broad queries are rejected before download. |
| `agri_endpoints(query=None)` | DG AGRI agri-food endpoints (prices, production, trade, CMEF indicators) and their params, read from the OpenAPI spec. |
| `agri_data(endpoint, params, limit=200)` | Rows from one endpoint; params are validated against the spec. |
| `ep_meps(name, country, group, limit=50)` | Current MEPs. |
| `ep_votes(date, query, roll_call_only, mep_id, language="en", limit=40)` | Plenary votes on a sitting day with counts, and optionally one MEP's vote. |
| `ep_query(endpoint, params, language="en", limit=10, offset=0)` | Any European Parliament API v2 GET endpoint, with labels in one language and nested data compacted. |
| `dataeu_search(query, country, format, catalogue, category, hvd, min_quality, page, limit=10)` | Search data.europa.eu (1.9M datasets) with a short description per row. |
| `dataeu_facets(query, by, country, format, catalogue, category, hvd, min_quality, top=10)` | Dataset counts per catalogue, format, category, country, publisher, licence or quality, for picking filters. |
| `dataeu_dataset(dataset_id, language="en", max_files=15)` | Description, publisher, licence and download URLs. |
| `dataeu_sparql(query, limit=100)` | Read-only SPARQL SELECT/ASK on the portal's DCAT graph. |
| `dataeu_quality(scope, id)` | Metadata quality (MQA) score and coverage per metric: global, country (ISO3) or catalogue. |
| `dataeu_use_cases(query, country, sector, limit=10)` | Apps and projects built on EU open data. |
| `govdata_search(query, theme, publisher, format, level, page=0, limit=10)` | Search GovData, Germany's open data catalogue (168k datasets, German titles; English terms are translated). Filters: DCAT theme (`envi`, `soci`…), publisher, file format, level (federal/state/district/municipality). |
| `govdata_dataset(dataset_id, max_files=15)` | Description, publisher, licence, level and numbered files. |
| `govdata_preview(dataset_id, file=1, limit=20)` | First rows of a CSV or JSON file (reads at most 1 MB). |
| `govdata_table(table_id, query, last_n, limit=100)` | Values of a Destatis GENESIS table (e.g. `12411-0010`), newest first, filtered by label words. |

### Source map (`find_data`)

The APIs publish little "what is this about" metadata, so the server builds one searchable **map
table** (SQLite FTS5, `sourcemap.db` in the cache directory) with one row per dataset or endpoint:
`source | id | title | topic_path | period | updated | next_call | keywords`. Each source is
enriched from the best signal it has:

| Source | Rows | Enrichment |
|---|---|---|
| CBS | ~1,300 active tables | Measure and dimension titles from the CBS index |
| Eurostat | ~7,500 datasets | Theme path from the table-of-contents tree (e.g. *Economy and finance > Prices*); extra theme locations as keywords |
| DG EMPL / GROW / TAXUD | ~40 | Dataflow names; per-country copies (`LMP_EXPME$HR`) collapsed into their parent |
| Agri-food | ~40 data endpoints | OpenAPI tag and summary, plus the values of the sector's code lookups (e.g. *Durum wheat*, *Feed barley* for `cereal/*`) |
| European Parliament | ~20 list endpoints + `ep_meps`/`ep_votes` | OpenAPI tag and description |
| data.europa.eu | its 4 tools | Hand-written |
| Destatis | ~3,000 GENESIS tables | Theme from GovData groups, keywords from the dataset tags (regions, statistic, measures) |
| GovData | 13 themes + ~200 theme × publisher slices | 168k datasets are too many for one row each, so each row says what kind of data a publisher has on a theme (*Environment data from Land Schleswig-Holstein: 4,210 datasets*), with its top tags and formats and a ready `govdata_search` call |

Hand-written metadata lives in each country's `hints.json`: source descriptions, extra keywords,
and synonyms (e.g. *pork → pigmeat*, *huizenprijzen → house prices*). Search also expands
English ↔ local-language terms through each country's `SYNONYMS` (for NL, the CBS synonym list; for DE, a German list in `countries/de/__init__.py`), so Dutch queries find Eurostat datasets and English
queries find CBS tables. Matches on the user's own words rank above synonym matches.

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
| Destatis GENESIS table downloads (keyless CSV) | `https://genesis.destatis.de/genesisWS/downloads/00/tables/<id>_00.csv` |

Not wrapped: the data.europa.eu registry (`/api/hub/repo`) serves the same metadata as search, but as slow RDF. The MQA reporter only serves PDFs, so `dataeu_quality` links to it instead. SHACL validation is publisher tooling and currently returns 503.

The output is compact text with `|` separators, and values that are the same in every row are
printed once under `fixed:`. A typical answer takes 3–4 calls of under 400 tokens each:

```
cbs_search("bevolking regio")                         → 37230ned Bevolkingsontwikkeling; regio per maand
cbs_codes("37230ned", "RegioS", "Amsterdam")          → GM0363|Amsterdam|Gemeenten per provincie
cbs_data("37230ned", ["M000098"], {"RegioS": ["GM0363"]}, latest=true)
```

### CBS search index

The CBS OData API (`https://datasets.cbs.nl/odata/v1`) has no ranked search: `$search` is ignored,
and the catalog is Dutch-only. The server therefore keeps a **SQLite FTS5 index** of titles,
descriptions, and the measure and dimension names of active tables. Results are ranked by title
matches, then BM25, then status and recency.

- **First run:** search works after ~3 s, once the catalog is in. Measure and dimension names are
  indexed in the background (~45 s).
- **Sync every 6 h:** the server diffs each table's `Version` with CBS and refetches only the
  changes (~1 s when nothing changed). It removes deleted tables, invalidates cached metadata, and
  won't delete more than 20% of the catalog in one sync.
- **Manual sync:** `europa-mcp sync [--full] [--no-details]`.

### Configuration

| Env var | Default | |
|---|---|---|
| `EUROPA_CACHE_DIR` | user cache dir (`europa-mcp`) | Where the CBS index (`nl-cbs.db`) and the source map (`sourcemap.db`) are stored |
| `EUROPA_REFRESH_HOURS` | `6` | Refresh interval of the indexes and the map |
| `EUROPA_RATE_LIMIT_RPS` | `5` | HTTP mode: sustained requests per second (burst 20) |
| `EUROPA_HOST` / `PORT` | `127.0.0.1` / `8000` | HTTP bind address |
| `EUROPA_LOG_LEVEL` | `INFO` | Logs go to stderr only |
| `CBS_BASE_URL`, `CBS_INDEX_PATH` | CBS OData v1, cache dir | CBS-specific overrides |

The pre-rename names (`CBS_INDEX_REFRESH_HOURS`, `CBS_RATE_LIMIT_RPS`, `CBS_HOST`, `CBS_LOG_LEVEL`)
still work as fallbacks.

### Development

```bash
uv sync
uv run pytest            # mocked HTTP (respx)
uv run pytest -m live    # end-to-end smoke test against the real API
npx @modelcontextprotocol/inspector uv run europa-mcp
```

Put the server command first. The Inspector parses flags such as `uvx --from .` as its own options.
API findings are in each `countries/<cc>/NOTES.md`; core notes in [NOTES.md](NOTES.md).

The package is not on PyPI yet, so the setup commands above install straight from GitHub
(`uvx --from git+https://github.com/jadikar-arch/cbs-fastmcp-server europa-mcp`). To run your own
checkout instead, use `uvx --from /path/to/checkout europa-mcp`. Once it is published, the shorter
`uvx europa-mcp` will work.

</details>

---

*Data: [CBS Statistics Netherlands](https://www.cbs.nl) (CC BY 4.0); [Destatis](https://www.destatis.de) and [GovData](https://www.govdata.de) (Datenlizenz Deutschland or the licence given per dataset); [Eurostat](https://ec.europa.eu/eurostat),
the European Commission, the [European Parliament](https://data.europarl.europa.eu) and
[data.europa.eu](https://data.europa.eu) (reuse authorised under the Commission's reuse policy /
CC BY 4.0). This project is not affiliated with any of these organisations.*
