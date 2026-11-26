---
name: se
description: Sweden official statistics from Statistics Sweden (SCB) - population, labour market, prices, GDP, housing, wages, births and deaths, migration, trade, energy, with regional detail down to municipality. Read before using the scb_* tools.
---

# Sweden: Statistics Sweden (SCB)

## Profile

| | |
|---|---|
| Country / code | Sweden (`se`) |
| Languages | English table titles and labels (~3,400 tables); Swedish names of places (`Göteborg`, `Malmö`) and Swedish questions are matched through a term list. Answer in the user's language and name the table |
| APIs | SCB PxWeb API (`api.scb.se/OV0104/v1/doris/en/ssd`) |
| Access | Keyless, read-only. Limit: 10 calls per 10 seconds; the tools keep to about 55 a minute, so the first start builds the table list in roughly 12 minutes (then it is saved for a day) |
| Licence | CC0 1.0 for the open data of the statistical database; SCB asks to credit "Source: Statistics Sweden" |
| Data types | Statistics tables (years, quarters `…K1`, months `…M01`, weeks `…V01`) by region, sex, age, industry and more; titles end with their period range |
| Geographic detail | Sweden, counties (län, 2-digit codes), municipalities (kommun, 4-digit codes), some tables down to smaller areas |
| Tools | `scb_search`, `scb_describe`, `scb_codes`, `scb_data` |
| Use instead | Eurostat for comparisons with other countries |

## Answering rules (official use)

These answers are used by government staff. A wrong or invented number is worse than no number.

- **Source every answer.** End with the `source:` line (link + licence) and name the table id. No source line, no figure.
- **Only fetched data.** Every number comes from a tool result in this conversation. Never estimate, round up, extrapolate, fill a gap or recall a figure from memory.
- **No mixing.** Do not combine these results with internet search results or other knowledge. If the user wants other sources, say they are outside this tool.
- **Ask when unclear.** If the country, period, region, unit, definition or breakdown is ambiguous, ask short questions before fetching. If several tables fit, show the list and let the user choose.
- **Plot inline.** For a series over time or a comparison of three or more values, draw a chart in the reply (use your client's chart tool if it has one, otherwise a table), from the fetched numbers only, labelled with unit, period and source.
- **Say what you could not do.** Nothing found: say "I cannot find data for this." Only part found (another period, region or definition): say exactly what the data covers. Not sure of the answer: say "I don't know." Never fill a gap with a guess.

**Use for** Swedish figures, especially by county or municipality. For comparisons between EU
countries use Eurostat (`country_guide("eu")`).

## Workflow (3-4 calls)

1. `find_data("unemployment rate")` ranks tables across all sources with the exact call (`scb_describe("AM/AM0401/AM0401A/AKURLBefM")`).
   Or `scb_search(query)`: English or local keywords; every word must match, and when none of the
   tables does it says so and lists partial matches. Leave places and years out of the query.
2. `scb_describe(table_id)`: variables with value counts, which are required, the measures, and the
   period range. The table id is the code after the last `/`; the full path works too.
3. `scb_codes(table_id, variable, query)`: look up a code by label, e.g. a municipality. The variable can be
   its code or its name from describe.
4. `scb_data(table_id, filters={variable: [codes]}, last_n=N)`: the newest period by default; `'*'` selects all
   values of a variable; variables left out and marked optional are totals. The answer ends with a `source:` line.

```
scb_codes("BefolkningNy", "region", "Stockholm")                            -> 0180 Stockholm, 01 Stockholm county
scb_data("BefolkningNy", {"region": ["00", "0180"], "ContentsCode": ["BE0101N1"]}, last_n=2)
```

## Codes

| | Pattern | Examples (verified) |
|---|---|---|
| Table id | folder path + code; the last part alone works (`BefolkningNy`) | `BE/BE0101/BE0101A/BefolkningNy` population by region, age, sex 1968-2024; `PR/PR0101/PR0101A/KPI2020COICOPM` consumer prices; `AM/AM0401/AM0401A/AKURLBefM` labour force survey; `NR/NR0103/NR0103E/NR0103ENS2010T01NA` GDP |
| Region | `00` Sweden, 2 digits county, 4 digits municipality (first 2 = county) | `00` Sweden, `01` Stockholm county, `0180` Stockholm, `1480` Göteborg, `0114` Upplands Väsby |
| Sex | `1` men, `2` women | |
| Period | `2024` year, `2026K2` quarter, `2026M10` month, `2026V39` week | the variable is usually `Tid` |
| Measures | variable `ContentsCode` | `BE0101N1` Population, `BE0101N2` Population growth |

## Pitfalls

- **Newest year in a sibling table:** SCB often keeps the past in one table and the latest year in another:
  `BefolkningNy` ends in 2024, `BefolkningCKM` holds 2025, `BefolkManadCKM` the months of 2025-26. Check the
  period range in describe; if the year you need is missing, search for the sibling and say which table you used.
- **CKM tables (`…CKM`):** SCB's disclosure protection (Cell Key Method) randomly changes counts by up to 3, so
  totals may not equal the sum of their parts and small numbers are uncertain. The tool prints this note; pass it on.
- **Optional variables are totals:** region, age, sex and marital status can be left out; the answer lists
  which variables were left out. Choose a region, or you get the Sweden total.
- **Rate limit:** at most 10 calls per 10 seconds. If a call says the table list is still loading, wait and retry.
- **No crime table:** a search for reported crimes finds none in this database (police crime statistics are
  published by another body). Say you cannot find them.
- **Price indices:** CPI (`KPI2020…`) and CPIF (`KPIF2020`) are different measures with base year 2020=100.
