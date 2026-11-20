---
name: de
description: Germany official data - Destatis statistics tables (population, labour market, prices, GDP, housing, tourism for Germany, states and districts) and the GovData catalogue of 168k open datasets from federal, state and municipal publishers (environment, maps, transport, city data). Read before using the govdata_* tools.
---

# Germany: Destatis and GovData

## Profile

| | |
|---|---|
| Country / code | Germany (`de`) |
| Languages | German titles, labels and codes. English query words are translated (`population` → `bevölkerung`); answer in the user's language and name the table |
| APIs | GovData CKAN catalogue (`ckan.govdata.de/api/3/action`) and Destatis GENESIS table downloads (`genesis.destatis.de/genesisWS/downloads/00/tables/<id>_00.csv`) |
| Access | Keyless, read-only |
| Licence | Destatis: Datenlizenz Deutschland, Namensnennung 2.0 (dl-de/by-2-0); GovData: per-dataset licence, shown by `govdata_dataset` |
| Data types | Official statistics tables (Destatis, ~3,000: time series by state and district); an open data catalogue of 168k datasets, mostly files, maps (WMS/WFS) and APIs from federal, state and municipal publishers |
| Geographic detail | Germany, 16 states, districts (5-digit AGS), municipalities in some GovData datasets |
| Tools | `govdata_search`, `govdata_dataset`, `govdata_preview`, `govdata_table` |
| Use instead | Eurostat for comparisons with other countries |

**Use for** German figures (Destatis, down to state and district) and for finding German open data
files and services (GovData). For comparisons between EU countries use Eurostat
(`country_guide("eu")`).

| Need | Tool |
|---|---|
| An official figure (population, unemployment, CPI, GDP, house prices…) | `govdata_table` (Destatis) |
| Which kinds of data exist on a topic, and who publishes them | `find_data`, then `govdata_search` with filters |
| Files, maps (WMS/WFS) or APIs from states and cities | `govdata_search` → `govdata_dataset` → `govdata_preview` |

## Workflow

1. `find_data("unemployment")` returns Destatis tables (`govdata_table("13211-0008")`) and GovData
   slices such as *Environment data from Land Schleswig-Holstein: 4,210 datasets* with a ready
   `govdata_search(…, theme=, publisher=)` call.
2. `govdata_table(table_id, query="Bayern", last_n=3)`: values, newest first. `query` words must
   all appear in the row labels or column header (a state, district, measure or age group).
   Without filters a big table is truncated; the output then lists the first-column labels.
3. `govdata_search(query, theme, publisher, format, level)`: **German keywords** work best
   ("bevölkerung", "grundwasser", "radverkehr"); common English words are translated. Leave places
   out of the query when a `publisher` or `level` filter fits.
4. `govdata_dataset(id)`: description, publisher, licence, level and its files, numbered.
   `govdata_preview(id, file=n)` shows the first rows of a CSV or JSON file.

## Codes

| | Values |
|---|---|
| Destatis tables | `12411-0001` population Germany, `12411-0010` by state, `12411-0015` by district; `13211-0002` unemployment Germany (monthly), `13211-0008` by state; `61111-0002` CPI monthly, `61111-0011` CPI by state; `61262-0002` house price index (quarterly); `81000-0002` GDP quarterly, `82111-0010` GDP by state; `45412-0025` tourism nights by state |
| theme | `envi` Environment, `regi` Regions and cities, `gove` Government, `econ` Economy and finance, `tech` Science, `soci` Population and society, `agri` Agriculture and food, `educ` Education and culture, `tran` Transport, `ener` Energy, `heal` Health, `just` Justice, `intr` International |
| publisher | slug or part of a name: `statistisches-bundesamt`, `open-data-bayern`, `land-schleswig-holstein`, `berlin-open-data`, `open-nrw`, `gdi-de` (geodata), `mcloud` (Mobilithek: mobility) |
| level | `federal`, `state`, `district`, `municipality` |
| District keys | 5-digit AGS in the first label column of district tables: `09162` München (city), `11000` Berlin |

## Pitfalls

- Destatis symbols: `-` = nothing (zero), `.` = secret, `x` = not applicable, `/` = too uncertain;
  `...` (not yet available) is skipped. German decimals are converted (`120,3` → `120.3`).
- Read the `about:` line for the unit (e.g. *Mill. EUR*) and `notes:` for breaks in series
  (census 2011 and 2022, Hartz reform 2005).
- Price indices have different base years (CPI `2020=100`, house prices `2025=100`).
- Most GovData datasets are files and map services, not tables: check the `formats` column.
  Many city and state datasets repeat once per year or measurement date; filter by `publisher`.
- The Destatis datasets that show only `HTML` (e.g. *Arbeitslose in Deutschland*) are web pages;
  the ones with a `values` column can be read with `govdata_table`.
- `dataeu_search(country="de")` also covers German portals (850k datasets) and has English
  metadata for some; use it when GovData finds nothing.
