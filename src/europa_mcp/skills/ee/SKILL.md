---
name: ee
description: Estonia official statistics from Statistics Estonia (Statistikaamet) - population, labour market, prices, GDP, wages, housing, births and deaths, tourism, energy, with regional detail down to county and municipality. Read before using the statee_* tools.
---

# Estonia: Statistics Estonia (Statistikaamet)

## Profile

| | |
|---|---|
| Country / code | Estonia (`ee`) |
| Languages | English table titles (in capitals) and labels; variable codes are Estonian (`Sugu` = Sex, `Elukoht` = place of residence), their English names also work. Estonian questions are matched through a term list |
| APIs | Statistics Estonia PxWeb API (`andmed.stat.ee/api/v1/en/stat`) |
| Access | Keyless, read-only |
| Licence | CC BY-SA 4.0, © Statistics Estonia (Statistikaamet): derived material must be shared under the same licence |
| Data types | ~2,100 current statistics tables (years, quarters, months, weeks) and ~2,900 discontinued ones, hidden by default |
| Geographic detail | Whole country, counties (maakond), municipalities and settlements in the regional tables |
| Tools | `statee_search`, `statee_describe`, `statee_codes`, `statee_data` |
| Use instead | Eurostat for comparisons with other countries |

## Answering rules (official use)

These answers are used by government staff. A wrong or invented number is worse than no number.

- **Source every answer.** End with the `source:` line (link + licence) and name the table id. No source line, no figure.
- **Only fetched data.** Every number comes from a tool result in this conversation. Never estimate, round up, extrapolate, fill a gap or recall a figure from memory.
- **No mixing.** Do not combine these results with internet search results or other knowledge. If the user wants other sources, say they are outside this tool.
- **Ask when unclear.** If the country, period, region, unit, definition or breakdown is ambiguous, ask short questions before fetching. If several tables fit, show the list and let the user choose.
- **Plot inline.** For a series over time or a comparison of three or more values, draw a chart in the reply (use your client's chart tool if it has one, otherwise a table), from the fetched numbers only, labelled with unit, period and source.
- **Say what you could not do.** Nothing found: say "I cannot find data for this." Only part found (another period, region or definition): say exactly what the data covers. Not sure of the answer: say "I don't know." Never fill a gap with a guess.

**Use for** Estonian figures, especially by county or municipality. For comparisons between EU
countries use Eurostat (`country_guide("eu")`).

## Workflow (3-4 calls)

1. `find_data("population")` ranks tables across all sources with the exact call (`statee_describe("RV0240.PX")`).
   Or `statee_search(query)`: English or local keywords; every word must match, and when none of the
   tables does it says so and lists partial matches. Leave places and years out of the query.
2. `statee_describe(table_id)`: variables with value counts, which are required, the measures, and the
   period range. The table id is the code after the last `/`; the full path works too.
3. `statee_codes(table_id, variable, query)`: look up a code by label, e.g. a municipality. The variable can be
   its code or its name from describe.
4. `statee_data(table_id, filters={variable: [codes]}, last_n=N)`: the newest period by default; `'*'` selects all
   values of a variable; variables left out and marked optional are totals. The answer ends with a `source:` line.

```
statee_codes("RV0240", "Place of residence", "Tallinn")                      -> 784  ..Tallinn
statee_data("RV0240", {"Place of residence": ["784", "00"], "Age": ["Total"], "Sex": ["Males and females"]}, last_n=2)
```

## Codes

| | Pattern | Examples (verified) |
|---|---|---|
| Table id | code + `.PX` (case varies: `RV0240.PX`, `IA002.px`) | `RV0240.PX` population by sex, age, residence; `RV030.PX` births and deaths; `IA002.px` consumer prices; `RAA0012.PX` GDP; `PA111.px` wages |
| Place of residence | `00` whole country, county and municipality codes | `00` Whole country, `784` Tallinn |
| Sex | `1` males and females, `2` males, `3` females | |
| Age | `000` total, then groups | `000` Total, `0-17`, `18-64`, `65+` |
| Period | year `2026`; quarterly and monthly tables list their own codes | look them up with `statee_codes` |

## Pitfalls

- **Hierarchy dots:** labels start with dots for sub-levels (`..Tallinn`); matching ignores them.
- **Several codes for one name:** `Tartu county` and its city/town/rural parts have separate codes; use `statee_codes`.
- **Discontinued tables** (folder "Lepetatud tabelid") are hidden; `include_discontinued=true` shows them.
- **Foreign trade is not reachable:** the office's API refuses to list its foreign-trade folders (HTTP 400),
  and no trade-in-goods table appears in the table list. Say so; use Eurostat for Estonia's trade.
- **No crime tables** appear in the table list (searching `crime` or `offences` finds none). If asked, say you cannot find them.
- **Population vs survey tables:** words like "population" also appear in survey-sample tables
  (`TU17`, `TS540`); read the title before using a table.
- **CC BY-SA:** when passing figures on, name Statistics Estonia as the source and keep the licence.
