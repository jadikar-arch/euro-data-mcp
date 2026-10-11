---
name: eu
description: EU-level official data - Eurostat statistics (all EU/EEA countries), Commission DG data (labour market policy, postal, taxation), EU agri-food market prices, European Parliament (MEPs, votes, adopted texts) and the data.europa.eu open data catalogue. Read before using eurostat_*, agri_*, ep_* or dataeu_* tools.
---

# EU level

| Need | Source | Tools |
|---|---|---|
| Compare countries; EU aggregates (EU27_2020, euro area) | Eurostat | `eurostat_*` |
| Labour market policy spending (DG EMPL), postal services (DG GROW), tax revenue and rates, VAT gap (DG TAXUD) | Commission DGs | `eurostat_*` with `agency=empl/grow/taxud` |
| Weekly/monthly farm-gate and market prices, production, agri trade, CAP indicators | DG AGRI agri-food | `agri_*` |
| MEPs, plenary votes, adopted texts, procedures, speeches, questions | European Parliament | `ep_*` |
| Find any dataset (incl. national/regional portals), download links, metadata quality | data.europa.eu | `dataeu_*` |

## Eurostat and DGs

1. `eurostat_search(query, agency="eurostat")`: **English** keywords. Dataset ids such as
   `prc_hpi_q`; `tps…`/`tag…`/`tec…` ids are small "main tables".
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
- Prices are text with currency and unit columns ("€209.09", per "100 KG"), so compare like with
  like. Some sectors (rice, olive oil, wine) only cover producing countries; "No data" usually
  means the member state doesn't report that product.

## European Parliament

- `ep_meps(name, country, group)`: current MEPs (country ISO2). The API's group labels are `PPE`
  (= EPP), `S&D`, `PfE`, `ECR`, `Renew`, `Verts/ALE` (= Greens/EFA), `The Left`, `ESN`, `NI`
  (non-attached); the English names work too.
- `ep_votes(date, query, roll_call_only, mep_id)`: plenary votes on a **sitting day**
  (YYYY-MM-DD). Find sitting days with `ep_query("meetings", {"year": 2026})`. `mep_id` shows that
  MEP's vote on roll-call votes.
- `ep_query(endpoint, params)`: any other endpoint, e.g. `adopted-texts` {"text": "housing"},
  `procedures/2024-2526`, `meps/{id}` (current memberships with committees), `speeches`,
  `parliamentary-questions` {"year": 2026}. Labels come in `language` (default en).
- Limit: 500 requests per 5 minutes, so don't loop over many days.

## data.europa.eu

- `dataeu_search(query, country="nl", format="CSV")`: 1.9M datasets from EU and national portals.
  Use it when no statistics table fits, or the user wants files or APIs to download.
  `dataeu_dataset(id)` gives download URLs and licence.
- `dataeu_sparql(query)`: read-only DCAT queries (counts by publisher, format…). Don't use it
  for text search; full-text `CONTAINS` over all titles times out.
- `dataeu_quality(scope="country", id="NLD")`: country ids are **ISO3** here.
- `dataeu_use_cases(query, country)`: apps built on open data.
