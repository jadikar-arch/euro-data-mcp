---
name: nl
description: Netherlands official statistics from CBS (Statistics Netherlands) - population, housing, income, labour, prices, health, regional figures down to municipality and neighbourhood. Read before using the cbs_* tools.
---

# Netherlands: CBS (Statistics Netherlands)

**Use for** any figure about the Netherlands, especially regional detail (province, municipality,
neighbourhood) or Dutch-specific topics. For comparisons between EU countries use Eurostat
(`country_guide("eu")`); Eurostat also covers NL with harmonised definitions.

## Workflow (3–4 calls)

1. `cbs_search(query)`: **Dutch topic keywords** ("bevolking regio", "koopwoningen prijzen",
   "werkloosheid"). Common English words are translated, but Dutch works best. Leave places and
   years out of the query; they are codes you pick in step 3.
2. `cbs_describe(dataset_id)`: measures (`M000098`…) and dimensions (`RegioS`, `Perioden`, …)
   with code counts and the latest period.
3. `cbs_codes(dataset_id, dimension, query)`: look up codes, e.g. `"Amsterdam"` → `GM0363`.
   Use `dimension="Measures"` to search measures.
4. `cbs_data(dataset_id, measures, filters, latest=true)`: values. Filter every large dimension.

`cbs_releases(days)` lists tables getting new data soon.

## Codes

| Dimension | Pattern | Examples |
|---|---|---|
| Region (`RegioS`, `WijkenEnBuurten`) | `NL01` country, `LD` part of the country, `PV` province, `CR` COROP region, `GM` municipality, `WK` district, `BU` neighbourhood | `GM0363` Amsterdam, `GM0599` Rotterdam, `GM0518` 's-Gravenhage (The Hague), `PV27` Noord-Holland |
| Period (`Perioden`) | `YYYYJJ00` year, `YYYYKWnn` quarter, `YYYYMMnn` month | `2025JJ00`, `2026KW02`, `2026MM08` |
| Measures | `M` + digits; titles are Dutch | `M000098` population at start of period |

Place names that differ in CBS titles are aliased: The Hague / Den Haag → 's-Gravenhage,
Den Bosch → 's-Hertogenbosch, Friesland → Fryslân.

## Pitfalls

- **Municipal mergers:** municipality codes change over time. A table's regional classification
  is the year it was made for, so search the code in *that* table with `cbs_codes`.
- **Provisional figures:** recent periods may be marked provisional (`status` in `cbs_codes` for
  periods). `latest=true` returns the newest period that has a value.
- **Discontinued tables:** `cbs_search` hides them by default (`include_discontinued=true` shows
  them). Their figures are not updated; prefer the regular successor table.
- **Too broad:** `cbs_data` refuses queries estimated above 100k rows; add filters as the error
  message suggests.
- Titles, measures and codes are Dutch. Translate them in your answer and name the table you used
  (id + title).
