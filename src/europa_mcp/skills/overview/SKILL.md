---
name: overview
description: Start here for official European open data - which countries and sources the europa server covers, how to pick one, and the workflow every data question follows (find_data, country guide, tools, source line). Read first, then the guide of the country you use.
---

# Overview: how to answer a data question

## Covered

| Code | Country | Sources | Languages | Guide |
|---|---|---|---|---|
| `eu` | European Union | Eurostat (all EU/EEA countries), Commission DGs, agri-food prices, European Parliament, data.europa.eu | English | `skill://eu/SKILL.md` |
| `de` | Germany | Destatis tables, GovData catalogue | German | `skill://de/SKILL.md` |
| `nl` | Netherlands | CBS tables | Dutch | `skill://nl/SKILL.md` |

`country_guide()` (no argument) returns this list live. Every other EU/EEA country has harmonised
Eurostat data (filter `geo=<code>`) and its national portals' datasets through
`dataeu_search(query, country="<iso2>")`.

The same guides are available two ways: as resources `skill://<code>/SKILL.md`, and through the
tool `country_guide("<code>")` for clients that cannot read resources.

## Workflow

1. **Pick the country.** Named in the question: use its guide. Not named and several countries
   match: offer the user the countries (or an EU-wide comparison) and ask. Comparing countries:
   Eurostat. One country with regional detail or national definitions: its national source.
2. `find_data(topic)`: ranked datasets across all sources with the exact next call. Put only the
   topic in the query (any language); places and years are filters applied later. The user picks
   from the list; show it and wait if your client cannot ask them.
3. Read the country guide once before its first tool call: languages, codes, pitfalls.
4. Describe, look up codes, fetch: `<source>_describe`, `<source>_codes`, `<source>_data`.
5. **Check before answering.** Dataset title and the `fixed:` line (unit, period, region, sex,
   age) must match the question; if not, try the next candidate or say what the data covers.
6. **Cite.** Every data answer ends with `source: <link> · licence: <licence>`; pass both on,
   with the dataset id.

## Answering rules (official use)

These answers are used by government staff. A wrong or invented number is worse than no number.

- **Source every answer.** End with the `source:` line (link + licence) and name the table id. No source line, no figure.
- **Only fetched data.** Every number comes from a tool result in this conversation. Never estimate, round up, extrapolate, fill a gap or recall a figure from memory.
- **No mixing.** Do not combine these results with internet search results or other knowledge. If the user wants other sources, say they are outside this tool.
- **Ask when unclear.** If the country, period, region, unit, definition or breakdown is ambiguous, ask short questions before fetching. If several tables fit, show the list and let the user choose.
- **Plot inline.** For a series over time or a comparison of three or more values, draw a chart in the reply (use your client's chart tool if it has one, otherwise a table), from the fetched numbers only, labelled with unit, period and source.
- **Say what you could not do.** Nothing found: say "I cannot find data for this." Only part found (another period, region or definition): say exactly what the data covers. Not sure of the answer: say "I don't know." Never fill a gap with a guess.
