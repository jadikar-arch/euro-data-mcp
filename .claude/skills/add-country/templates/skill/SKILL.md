---
name: <cc>
description: <Country> official data from <sources> - <main topics>. Read before using the <source>_* tools.
---

# <Country>: <sources>

## Profile

| | |
|---|---|
| Country / code | <Country> (`<cc>`) |
| Languages | <language of titles, labels and codes; are English query words translated?> |
| APIs | <API name and base URL for each source> |
| Access | <keyless or key; rate limits; page and size limits> |
| Licence | <licence and attribution line, as printed in the `source:` line> |
| Data types | <tables / time series / files / maps / parliament; how many; period range> |
| Geographic detail | <country, region, municipality, neighbourhood levels> |
| Tools | <`<source>_search`, `_describe`, `_codes`, `_data` ...> |
| Use instead | <when another source fits better, e.g. Eurostat for cross-country comparisons> |

## Answering rules (official use)

These answers are used by government staff. A wrong or invented number is worse than no number.

- **Source every answer.** End with the `source:` line (link + licence) and name the table id. No source line, no figure.
- **Only fetched data.** Every number comes from a tool result in this conversation. Never estimate, round up, extrapolate, fill a gap or recall a figure from memory.
- **No mixing.** Do not combine these results with internet search results or other knowledge. If the user wants other sources, say they are outside this tool.
- **Ask when unclear.** If the country, period, region, unit, definition or breakdown is ambiguous, ask short questions before fetching. If several tables fit, show the list and let the user choose.
- **Plot inline.** For a series over time or a comparison of three or more values, draw a chart in the reply (use your client's chart tool if it has one, otherwise a table), from the fetched numbers only, labelled with unit, period and source.
- **Say what you could not do.** Nothing found: say "I cannot find data for this." Only part found (another period, region or definition): say exactly what the data covers. Not sure of the answer: say "I don't know." Never fill a gap with a guess.

**Use for** <what this country's sources are best at>. For comparisons between EU countries use
Eurostat (`country_guide("eu")`).

## Workflow

1. `<source>_search(query)`: <language> keywords work best, e.g. "<example>".
2. `<source>_describe(id)`: <what it shows>.
3. `<source>_codes(id, dimension, query)`: e.g. "<place>" → `<code>`.
4. `<source>_data(id, filters, …)`: <how to get the latest period>.

## Codes

| Dimension | Pattern | Examples |
|---|---|---|
| Region | <scheme, e.g. municipality numbers> | <verified examples> |
| Period | <format> | <examples> |

## Pitfalls

- <things that went wrong while testing: classification changes, provisional data, units, limits>
