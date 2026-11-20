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
