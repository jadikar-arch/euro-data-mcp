---
name: eu
description: EU-level official data - Eurostat statistics (all EU/EEA countries), Commission DG data (labour market policy, postal, taxation), EU agri-food market prices, European Parliament (MEPs, votes, adopted texts) and the data.europa.eu open data catalogue. Read before using eurostat_*, agri_*, ep_* or dataeu_* tools.
---

# EU level

## Profile

| | |
|---|---|
| Country / code | European Union (`eu`): Eurostat covers every EU/EEA country, so this is also where cross-country questions go |
| Languages | Dataset titles and labels in English (Eurostat also has French and German); Parliament labels via `language`; data.europa.eu has titles in each portal's own language |
| APIs | Eurostat and DG statistics (SDMX/JSON-stat, `ec.europa.eu/eurostat/api/dissemination`, `webgate.ec.europa.eu/*/redisstat`), DG AGRI agri-food portal (`api.tech.ec.europa.eu/agrifood`), European Parliament open data (`data.europarl.europa.eu/api/v2`), data.europa.eu (search + SPARQL) |
| Access | Keyless, read-only. The Parliament API allows 500 requests per 5 minutes |
| Licence | Commission reuse policy, CC BY 4.0 (© European Union); Parliament: reuse with attribution |
| Data types | Statistics tables with time series (Eurostat, DGs), weekly/monthly market prices (agri-food), parliamentary records (MEPs, votes, texts), a metadata catalogue of 1.9M datasets with download links |
| Geographic detail | Country and EU aggregates; NUTS regions in `…_r_…` datasets. No municipalities |
| Tools | `eurostat_search/describe/codes/data`, `agri_endpoints/data`, `ep_meps/votes/query`, `dataeu_search/dataset/preview/facets/sparql/quality/use_cases` |
| Use instead | A national source (`country_guide()` lists them) when the user wants regional detail or national definitions |

| Need | Source | Tools |
|---|---|---|
| Compare countries; EU aggregates (EU27_2020, euro area) | Eurostat | `eurostat_*` |
| Labour market policy spending (DG EMPL), postal services (DG GROW), tax revenue and rates, VAT gap (DG TAXUD) | Commission DGs | `eurostat_*` with `agency=empl/grow/taxud` |
| Weekly/monthly farm-gate and market prices, production, agri trade, CAP indicators | DG AGRI agri-food | `agri_*` |
| MEPs, plenary votes, adopted texts, procedures, speeches, questions | European Parliament | `ep_*` |
| Find any dataset (incl. national/regional portals), download links, metadata quality | data.europa.eu | `dataeu_*` |

**Check before answering.** Compare the question with what came back: dataset title and the
`fixed:` line (unit, age, sex, geo). National figures when regions were asked, an index when a
level was asked, or a period years old: try the next candidate, or say what the data covers.

**Cite every figure.** Data answers end with `source: <url> · licence: <licence>`. Give the user
that link and licence with the numbers (and the dataset id), so they can check and reuse them.

## Eurostat and DGs

1. `find_data(topic)` returns a ranked list (rank, match %, title, period, breakdowns) and lets the
   **user** choose: a picker in apps that support it, otherwise show them the list and wait for
   their pick before fetching. `eurostat_search(query, agency="eurostat")` uses the same ranking. Ids such as
   `prc_hpi_q`; `tps…`/`tec…`/`tes…`/`sdg_…` ids are Eurostat's curated "main tables" (few
   breakdowns, quick answers); `…_r_…`/`tgs…` ids have regions. Several rows can be right: pick by
   title, period and breakdowns, not just the first row.
2. `eurostat_describe(id)`: dimensions with their codes and the period range.
3. `eurostat_codes(id, dimension, query)`: e.g. `geo` "Netherlands" → `NL`.
4. `eurostat_data(id, filters={dim: [codes]}, last_n=N | since/until)`: newest first.

- **geo:** ISO2 codes except `EL` = Greece and `UK`; aggregates `EU27_2020`, `EA20`. Regional
  datasets use NUTS codes (`NL32` = Noord-Holland).
- **Time:** `2024`, `2024-Q1`, `2024-03`, `2024-S1`.
- **Flags:** `p` provisional, `e` estimated, `b` break in series, `c` confidential, `u` low reliability.
- **Filters:** always filter `unit` (and `geo`), otherwise mixed units (index vs % change) appear
  side by side. Over-broad queries are refused before download.
- **DG datasets:** EMPL per-country copies are `ID$CC` (e.g. `LMP_EXPME$HR`); prefer the parent
  with a `geo` filter.

## Agri-food (DG AGRI)

1. `agri_endpoints(query)`: endpoints per sector (`pigmeat/prices`, `cereal/production`, …) and
   their params; parameterless "code lookups" list valid product/market codes.
2. `agri_data(endpoint, params)`: e.g. `{"memberStateCodes": "NL,DE", "beginDate": "01/09/2026"}`.

- Dates are `dd/mm/yyyy`; lists are comma-separated. Marketing years follow the sector:
  cereals `2025/2026` (starting July), olive oil `2025/26`.
- Prices come as text ("€209.09", "€233,59") plus a numeric `value` and a `currency` column; check
  the `unit` (per "100 KG", per "TONNES") and compare like with like. Some sectors (rice, olive oil, wine) only cover producing countries; "No data" usually
  means the member state doesn't report that product.

## European Parliament

- `ep_meps(name, country, group)`: current MEPs (country ISO2). The API's group labels are `PPE`
  (= EPP), `S&D`, `PfE`, `ECR`, `Renew`, `Verts/ALE` (= Greens/EFA), `The Left`, `ESN`, `NI`
  (non-attached); the English names work too.
- `ep_votes(date, query, roll_call_only, mep_id)`: plenary votes on a **sitting day**
  (YYYY-MM-DD), in voting order, with a `vote_id` per row. Find sitting days with
  `ep_query("meetings", {"year": 2026})` (one line per day). `mep_id` shows that MEP's vote on
  roll-call votes.
- `ep_query(endpoint, params)`: any other endpoint, e.g. `adopted-texts` {"text": "housing"},
  `procedures/2024-2526`, `meps/{id}` (current memberships with committees), `speeches`,
  `parliamentary-questions` {"year": 2026} (title, author, answered). Labels come in `language`
  (default en). Long results stop at a size budget; continue with `offset`.
- Limit: 500 requests per 5 minutes, so don't loop over many days.

## data.europa.eu

- `dataeu_search(query, country="nl", format="CSV")`: 1.9M datasets from EU and national portals.
  Use it when no statistics table fits, or the user wants files or APIs to download.
  Filters: `category` (EU theme: HEAL, ECON, TRAN, ENVI, AGRI…), `hvd=True` (High-Value
  Datasets only), `min_quality="good"` (metadata scoring), `sort="newest"` (the 100 most
  relevant matches, recently updated first, for "latest"/"current" questions), `language="fr"`
  (titles/descriptions in that language).
  Each row has a short `about` text. `dataeu_dataset(id)` gives numbered files with format,
  licence and URL; `dataeu_preview(id, file=n)` shows the columns and first rows of a CSV/JSON
  file (and, for large CSVs, the last rows, to see how current it is), so check a file before telling the user it has what they need. Many publisher links are
  dead or are web pages: if a preview fails, try the next CSV/JSON file or dataset.
- `dataeu_facets(query, country, by="catalogue,format,category")`: counts only, no datasets.
  Call it first on broad topics: results are noisy (Germany's 850k are mostly `gdi-de` zoning
  plans), so pick a `catalogue`, `format` or `category` from it before `dataeu_search`.
- `find_data` knows the ~200 portals (catalogues) by description; its `catalogue="…"` hint
  routes a topic to the right national portal.
- `dataeu_sparql(query)`: read-only DCAT queries (counts by publisher, format…). Don't use it
  for text search; full-text `CONTAINS` over all titles times out.
- `dataeu_quality(scope="country", id="NLD")`: country ids are **ISO3** here.
- `dataeu_use_cases(query, country)`: apps built on open data.
