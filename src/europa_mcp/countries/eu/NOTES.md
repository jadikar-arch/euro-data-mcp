# EU APIs: probe findings (2026-10-11)
Deduplicated sources. The search URL was listed twice; `hub/repo/index.html` is the docs page of the repo API; W3C SPARQL, MQA methodology and the SHACL UI are docs or web pages, not APIs.
- **Eurostat-family** (`/sdmx/2.1`, `/statistics/1.0`): Eurostat `ec.europa.eu/eurostat/api/dissemination` (ESTAT). DG EMPL, GROW and TAXUD are at `webgate.ec.europa.eu/{empl,grow,taxation_customs}/redisstat/api/dissemination` (agency IDs EMPL, GROW, TAXUD).
  - Catalogue: Eurostat `catalogue/toc/txt?lang=en` (2 MB TSV, includes data start/end). It returns 404 on the DG sites, which have small SDMX `dataflow/all/all/latest` lists (74/18/8 flows). The full ESTAT dataflow list is 38 MB, so don't use it.
  - Structure: `dataflow/{AG}/{id}/latest?references=descendants&detail=referencepartial` returns only the codes used, plus OBS_COUNT and OBS_PERIOD_OVERALL_OLDEST/LATEST annotations (ESTAT only).
  - Data: `statistics/1.0/data/{id}?geo=NL&geo=DE&lastTimePeriod=N|sinceTimePeriod=|untilTimePeriod=&lang=en` returns JSON-stat 2.0 with a sparse `value` and `status`. Unknown dims give 400 `{"error":[{"label":..}]}`; an unfiltered query returns the whole dataset (MBs).
  - Never send `format=sdmx_2.1_structure` (406). IDs may contain `$`: EMPL uses `X$CC` for per-country copies, GROW uses `X$INDICATOR` views.
- **Agrifood** `api.tech.ec.europa.eu/agrifood/api/...`: OpenAPI at `/agrifood/v3/api-docs`. About 45 data endpoints (`beef/prices`, `cereal/production`, `cmefIndicators/values`…) and about 60 parameterless lookups (`cereal/products`…). Multi-values are comma-separated, dates `dd/mm/yyyy`, and a successful call returns a plain JSON array. No data gives 404 "No results found"; prices are strings ("€209.09", sometimes "€232,00").
- **European Parliament** `data.europarl.europa.eu/api/v2` (OpenAPI at the root; 500 requests per 5 min): needs `format=application/ld+json`, uses offset/limit, returns `{"data":[...], "meta":{"total"}}` and 204 when empty. Labels come in 24 languages. `text=` needs `search-language=` (else 500).
  - `meps/show-current?limit=1000` returns all 719 MEPs with country and group. `corporate-bodies?limit=10000` (550 KB) maps `org/NNNN` to labels.
  - `meetings/MTG-PL-YYYY-MM-DD/decisions` (about 2 MB) has roll-call counts and voter lists; `/vote-results` has item titles.
  - Files are at `https://data.europarl.europa.eu/` + `is_exemplified_by`.
- **data.europa.eu**:
  - Search `api/hub/search/search?q=&filter=dataset&facets={"country":["nl"],"format":["CSV"]}&includes=…&aggregation=false`; dataset detail at `/datasets/{id}`.
  - `includes=description.en` keeps one language (10 rows: 5 KB instead of 114 KB with all 25). Values in one facet list are ORed (`scoring: [excellentScoring, goodScoring]`); facets `categories` (AGRI…TRAN), `is_hvd` ("true"), `scoring`. `limit=0` with aggregation on returns counts only.
  - Paging stops at 10,000 hits (page×limit); beyond that only `/scroll`. So the find_data map holds the 213 catalogues (`filter=catalogue`, with `count`, description, country, homepage), not the datasets.
  - SPARQL `data.europa.eu/sparql`: 1.9M datasets, results capped at 50k rows; a `CONTAINS` scan over all titles gives a 504.
  - MQA `api/mqa/cache/{global,countries/NLD,catalogues/{id}}`: country IDs are ISO3; each metric is a score out of 7.5, and `coverage` is already a percentage. The reporter API only serves PDFs (`reporter/report/en?catalogueId=`), so link to it.
  - Use cases: `/en/export-use-cases` (CSV, 270 KB, dates dd/mm/yyyy). SHACL validation returns 503 (and is publisher tooling), so skip it. The repo API serves the same DCAT metadata as search but as slow RDF (60 s timeout), so skip it.
