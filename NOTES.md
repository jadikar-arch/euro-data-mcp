# Core notes
API probe findings live with each country: `src/europa_mcp/countries/<cc>/NOTES.md`.

## Source map for find_data (2026-10-11)
- Metadata available per API: the Eurostat TOC is a theme tree (4-space indent per level; datasets repeat under "Tables by themes"). Agri-food OpenAPI has one tag and a short summary per op; its ~60 parameterless lookups return code lists usable as keywords. The EP OpenAPI has tags and descriptions.
- Agri-food `taxud/weeklyData/*/{cn8,taric10}ProductCodes` take 15–90 s and contain only customs codes, so they are skipped. A full map build takes about 25 s (agri-food lookups dominate).
- FTS prefix queries (`"house"*`) match "household", so terms under 6 characters match whole words (plus s/es) only. Longer ones keep prefix matching for Dutch compounds (bevolking → bevolkingsontwikkeling).
