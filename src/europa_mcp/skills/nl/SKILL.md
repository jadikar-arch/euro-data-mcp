---
name: nl
description: Netherlands official statistics from CBS (Statistics Netherlands) - population, housing, income, labour, prices, health, regional figures down to municipality and neighbourhood. Read before using the cbs_* tools.
---

# Netherlands: CBS (Statistics Netherlands)

## Profile

| | |
|---|---|
| Country / code | Netherlands (`nl`) |
| Languages | Dutch titles, measures and region names (~4,900 tables). English query words are translated (`unemployment` → `werkloosheid`); answer in the user's language and name the table |
| APIs | CBS Open Data OData v4 (`datasets.cbs.nl/odata/v1`) |
| Access | Keyless, read-only, JSON. Pages of 100,000 rows; the tool refuses queries above ~100k rows |
| Licence | CC BY 4.0, © Centraal Bureau voor de Statistiek (CBS) |
| Data types | Statistics tables: time series (years, quarters, months) by region, age, sex, industry and more. About 1,290 regular tables; discontinued ones are hidden by default |
| Geographic detail | Country, part of country, province, COROP region, municipality, district (wijk), neighbourhood (buurt) |
| Tools | `cbs_search`, `cbs_describe`, `cbs_codes`, `cbs_data`, `cbs_releases` |
| Use instead | Eurostat for comparisons with other countries |

## Answering rules (official use)

These answers are used by government staff. A wrong or invented number is worse than no number.

- **Source every answer.** End with the `source:` line (link + licence) and name the table id. No source line, no figure.
- **Only fetched data.** Every number comes from a tool result in this conversation. Never estimate, round up, extrapolate, fill a gap or recall a figure from memory.
- **No mixing.** Do not combine these results with internet search results or other knowledge. If the user wants other sources, say they are outside this tool.
- **Ask when unclear.** If the country, period, region, unit, definition or breakdown is ambiguous, ask short questions before fetching. If several tables fit, show the list and let the user choose.
- **Plot inline.** For a series over time or a comparison of three or more values, draw a chart in the reply (use your client's chart tool if it has one, otherwise a table), from the fetched numbers only, labelled with unit, period and source.
- **Say what you could not do.** Nothing found: say "I cannot find data for this." Only part found (another period, region or definition): say exactly what the data covers. Not sure of the answer: say "I don't know." Never fill a gap with a guess.

**Use for** any figure about the Netherlands, especially regional detail (province, municipality,
neighbourhood) or Dutch-specific topics. For comparisons between EU countries use Eurostat
(`country_guide("eu")`); Eurostat also covers NL with harmonised definitions.

## Workflow (3-4 calls)

1. `find_data("unemployment")` ranks CBS tables with the exact call (`cbs_describe("80590ned")`).
   Or `cbs_search(query)` with **Dutch topic keywords** ("bevolking regio", "koopwoningen prijzen",
   "werkloosheid"); common English words are translated. Leave places and years out of the query:
   they are codes you pick in step 3.
2. `cbs_describe(dataset_id)`: measures (`M000098`...) and dimensions (`RegioS`, `Perioden`, ...)
   with code counts and the latest period.
3. `cbs_codes(dataset_id, dimension, query)`: look up codes, e.g. `"Amsterdam"` -> `GM0363`.
   Use `dimension="Measures"` to search measures.
4. `cbs_data(dataset_id, measures, filters, latest=true)`: values, ending with a `source:` line.
   Filter every large dimension.

`cbs_releases(days)` lists tables getting new data soon.

```
cbs_codes("37230ned", "RegioS", "Amsterdam")                  -> GM0363
cbs_data("37230ned", ["M000098"], {"RegioS": ["GM0363"]}, latest=true)
cbs_data("37230ned", ["M000098"], {"RegioS": ["GM0363", "GM0599"], "Perioden": ["2024JJ00", "2025JJ00"]})
```

## Codes

| Dimension | Pattern | Examples |
|---|---|---|
| Region (`RegioS`, `WijkenEnBuurten`) | `NL01` country, `LD` part of the country, `PV` province, `CR` COROP region, `GM` municipality, `WK` district, `BU` neighbourhood | `GM0363` Amsterdam, `GM0599` Rotterdam, `GM0518` 's-Gravenhage (The Hague), `PV27` Noord-Holland |
| Period (`Perioden`) | `YYYYJJ00` year, `YYYYKWnn` quarter, `YYYYMMnn` month | `2025JJ00`, `2026KW02`, `2026MM08` |
| Measures | `M` + digits (some `D`/digits + `_n`); titles are Dutch | `M000098` population at start of period |

Place names that differ in CBS titles are aliased: The Hague / Den Haag -> 's-Gravenhage,
Den Bosch -> 's-Hertogenbosch, Friesland -> Fryslan.

## Pitfalls

- **Municipal mergers:** municipality codes change over time. A table's regional classification
  is the year it was made for, so search the code in *that* table with `cbs_codes`.
- **Provisional figures:** recent periods may be marked provisional (`status` in `cbs_codes` for
  periods). `latest=true` returns the newest period that has a value.
- **Measures with the same title:** a title repeated in a table is prefixed with its group
  (`Werkloze beroepsbevolking: Seizoengecorrigeerd`). Read the whole name before answering.
- **Discontinued tables:** `cbs_search` hides them by default (`include_discontinued=true` shows
  them), and find_data leaves them out. Their figures are not updated; prefer the regular
  successor table.
- **Too broad:** `cbs_data` refuses queries estimated above 100k rows; add filters as the error
  message suggests.
- Titles, measures and codes are Dutch. Translate them in your answer and name the table you used
  (id + title).
