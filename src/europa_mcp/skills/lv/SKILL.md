---
name: lv
description: Latvia official statistics from the Central Statistical Bureau (CSB) Official Statistics Portal - population, labour market, prices, GDP, wages, housing, births and deaths, energy, with regional detail down to municipality and city. Read before using the csb_* tools.
---

# Latvia: Central Statistical Bureau (CSB)

## Profile

| | |
|---|---|
| Country / code | Latvia (`lv`) |
| Languages | English table titles and labels (~1,400 current tables); Latvian questions are matched through a term list. Place labels have diacritics (`Rīga`) |
| APIs | Official Statistics Portal PxWeb API (`data.stat.gov.lv/api/v1/en/OSP_PUB`) |
| Access | Keyless, read-only |
| Licence | Reuse with attribution (terms correspond to CC BY 4.0): cite the Central Statistical Bureau of Latvia and the Official Statistics Portal |
| Data types | Statistics tables (years, quarters `…Q1`, months `…M01`, weeks) by region, sex, age, activity; ~170 archived tables are hidden by default |
| Geographic detail | Latvia, statistical regions, State cities, municipalities (novads), towns, rural territories, neighbourhoods in the regional tables |
| Tools | `csb_search`, `csb_describe`, `csb_codes`, `csb_data` |
| Use instead | Eurostat for comparisons with other countries |

## Answering rules (official use)

These answers are used by government staff. A wrong or invented number is worse than no number.

- **Source every answer.** End with the `source:` line (link + licence) and name the table id. No source line, no figure.
- **Only fetched data.** Every number comes from a tool result in this conversation. Never estimate, round up, extrapolate, fill a gap or recall a figure from memory.
- **No mixing.** Do not combine these results with internet search results or other knowledge. If the user wants other sources, say they are outside this tool.
- **Ask when unclear.** If the country, period, region, unit, definition or breakdown is ambiguous, ask short questions before fetching. If several tables fit, show the list and let the user choose.
- **Plot inline.** For a series over time or a comparison of three or more values, draw a chart in the reply (use your client's chart tool if it has one, otherwise a table), from the fetched numbers only, labelled with unit, period and source.
- **Say what you could not do.** Nothing found: say "I cannot find data for this." Only part found (another period, region or definition): say exactly what the data covers. Not sure of the answer: say "I don't know." Never fill a gap with a guess.

**Use for** Latvian figures, especially by municipality or city. For comparisons between EU
countries use Eurostat (`country_guide("eu")`).

## Workflow (3-4 calls)

1. `find_data("unemployment rate")` ranks tables across all sources with the exact call (`csb_describe("EMP/NBBA/NBBB/NBB160c")`).
   Or `csb_search(query)`: English or local keywords; every word must match, and when none of the
   tables does it says so and lists partial matches. Leave places and years out of the query.
2. `csb_describe(table_id)`: variables with value counts, which are required, the measures, and the
   period range. The table id is the code after the last `/`; the full path works too.
3. `csb_codes(table_id, variable, query)`: look up a code by label, e.g. a municipality. The variable can be
   its code or its name from describe.
4. `csb_data(table_id, filters={variable: [codes]}, last_n=N)`: the newest period by default; `'*'` selects all
   values of a variable; variables left out and marked optional are totals. The answer ends with a `source:` line.

```
csb_codes("POP/IR/IRD/IRD081", "AREA", "Riga")                               -> LV0001000 Riga
csb_data("POP/IR/IRD/IRD081", {"AREA": ["LV0001000", "LV0002000"], "SEX": ["T"], "AgeGroup": ["TOTAL"]})
csb_data("IRS010", {"INDICATOR": ["POP_SY"]}, last_n=3)                      -> population at start of year
```

## Codes

| | Pattern | Examples (verified) |
|---|---|---|
| Table id | folder path + code; the last part alone works when unique | `POP/IR/IRD/IRD081` population by sex, age, area; `POP/IR/IRS/IRS010` key figures; `VEK/PC/PCI/PCI021m` consumer prices; `VEK/IK/IKP/IKP010` GDP |
| Area (`AREA`, `Territorial unit`) | `LV` country, `LV00A` etc. statistical regions, `LV0001000`-style municipality and city codes | `LV0001000` Riga, `LV0002000` Daugavpils |
| Sex | `T` total, `M` males, `F` females | |
| Period | `2026` year, `2026Q2` quarter, `2026M08` month | table titles end with their range |

## Pitfalls

- **Same label, several codes:** `Riga` is `LV0001000` (city) and `LVDPA0001` (the densely-populated-area version); `csb_data`
  asks for the code when a label is ambiguous. Use `csb_codes`.
- **Symbols:** `X` (not available) and `-` cells are omitted and counted in an `# omitted empty cells` line.
- **Unit columns:** some tables give both a number and a per-1,000 measure (`Number`, `Number of 1000 inhabitants`);
  the `measure` column says which one you are reading.
- **Optional variables are totals:** a variable you leave out (marked optional in describe) is the server default,
  normally the total; the answer lists which variables were left out.
- **No crime table** is in this list (crime statistics are published by other bodies): say you cannot find it.
- **Archived tables** (folders starting `A_`) are hidden; `include_discontinued=true` shows them.
