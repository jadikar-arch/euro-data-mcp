---
name: fi
description: Finland official statistics from Statistics Finland (StatFin) - population, labour market, prices, GDP, housing, earnings, births and deaths, migration, crime, energy, with regional detail down to municipality. Read before using the statfin_* tools.
---

# Finland: Statistics Finland (StatFin)

## Profile

| | |
|---|---|
| Country / code | Finland (`fi`) |
| Languages | English table titles and labels (~1,500 tables); Finnish and Swedish questions are matched through a term list. Answer in the user's language and name the table |
| APIs | StatFin PxWeb API (`pxdata.stat.fi/PxWeb/api/v1/en/StatFin`) |
| Access | Keyless, read-only. The server answers HTTP 429 when called too fast (seen above roughly 30 a minute); the tools keep to 24 a minute |
| Licence | CC BY 4.0, © Statistics Finland |
| Data types | Statistics tables (time series by year, quarter or month) by region, sex, age, industry and more; table titles end with their period range |
| Geographic detail | Whole country, regions (maakunta), municipalities (kunta, codes `KU…`) in the regional tables |
| Tools | `statfin_search`, `statfin_describe`, `statfin_codes`, `statfin_data` |
| Use instead | Eurostat for comparisons with other countries |

## Answering rules (official use)

These answers are used by government staff. A wrong or invented number is worse than no number.

- **Source every answer.** End with the `source:` line (link + licence) and name the table id. No source line, no figure.
- **Only fetched data.** Every number comes from a tool result in this conversation. Never estimate, round up, extrapolate, fill a gap or recall a figure from memory.
- **No mixing.** Do not combine these results with internet search results or other knowledge. If the user wants other sources, say they are outside this tool.
- **Ask when unclear.** If the country, period, region, unit, definition or breakdown is ambiguous, ask short questions before fetching. If several tables fit, show the list and let the user choose.
- **Plot inline.** For a series over time or a comparison of three or more values, draw a chart in the reply (use your client's chart tool if it has one, otherwise a table), from the fetched numbers only, labelled with unit, period and source.
- **Say what you could not do.** Nothing found: say "I cannot find data for this." Only part found (another period, region or definition): say exactly what the data covers. Not sure of the answer: say "I don't know." Never fill a gap with a guess.

**Use for** Finnish figures, especially by region or municipality. For comparisons between EU
countries use Eurostat (`country_guide("eu")`).

## Workflow (3-4 calls)

1. `find_data("unemployment rate")` ranks tables across all sources with the exact call (`statfin_describe("tyti/135z.px")`).
   Or `statfin_search(query)`: English or local keywords; every word must match, and when none of the
   tables does it says so and lists partial matches. Leave places and years out of the query.
2. `statfin_describe(table_id)`: variables with value counts, which are required, the measures, and the
   period range. The table id is the code after the last `/`; the full path works too.
3. `statfin_codes(table_id, variable, query)`: look up a code by label, e.g. a municipality. The variable can be
   its code or its name from describe.
4. `statfin_data(table_id, filters={variable: [codes]}, last_n=N)`: the newest period by default; `'*'` selects all
   values of a variable; variables left out and marked optional are totals. The answer ends with a `source:` line.

```
statfin_codes("11ra", "Area", "Helsinki")                                    -> KU091 Helsinki
statfin_data("11ra", {"Area": ["KU091", "SSS"], "Information": ["vaerak-vaesto"]}, last_n=1)
statfin_data("11rb", last_n=3)                                               -> population 31 Dec, whole country
```

## Codes

| | Pattern | Examples (verified) |
|---|---|---|
| Table id | folder + code + `.px` | `vaerak/11rb.px` population 1750-2025, `vaerak/11ra.px` key figures by region, `khi/11xs.px` consumer prices, `ntp/15a9.px` GDP annual |
| Area | `SSS` whole country, `KU` + 3 digits municipality, other groupings (`SA1`, `SK011`, `HVA90`) | `SSS` = WHOLE COUNTRY, `KU091` Helsinki, `KU020` Akaa |
| Period | `2025` year, `2026Q3` quarter, `2026M09` month | titles list the range, e.g. `1972M01-2026M10` |
| Measures | variable `contentscode` or a table-specific code | `vaerak-vaesto` = Population 31 Dec |
| Sex | `SSS` total, `1` males, `2` females | |

## Pitfalls

- **Many measures:** tables like `11ra` have 40+ measures; `statfin_data` asks you to choose some (code
  list in describe) instead of printing all of them.
- **Regions change:** area codes follow the year the table was made for (`alue_23_20260101` = 2026
  municipalities). Look the code up in that table with `statfin_codes`.
- **Provisional data:** a `*` after a year in a title (`1975-2025*`) means the latest year is provisional.
- **Several price indices:** CPI exists with different base years (`2015=100`, `2025=100`); say which one you used.
- **Unemployment:** `tyti/135z.px` (Labour Force Survey) and `tyonv/12r5.px` (unemployed jobseekers of the
  employment offices) are different measures; name the one you report.
- A table's `*` or `..` cells are omitted from the answer and counted in an `# omitted empty cells` line.
