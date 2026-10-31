# Core notes
API probe findings live with each country: `src/europa_mcp/countries/<cc>/NOTES.md`.

## Source map for find_data (2026-10-11)
- Metadata available per API: the Eurostat TOC is a theme tree (4-space indent per level; datasets repeat under "Tables by themes"). Agri-food OpenAPI has one tag and a short summary per op; its ~60 parameterless lookups return code lists usable as keywords. The EP OpenAPI has tags and descriptions.
- Agri-food `taxud/weeklyData/*/{cn8,taric10}ProductCodes` take 15–90 s and contain only customs codes, so they are skipped. A full map build takes about 25 s (agri-food lookups dominate).
- FTS prefix queries (`"house"*`) match "household", so terms under 6 characters match whole words (plus s/es) only. Longer ones keep prefix matching for German compounds (bevölkerung → bevölkerungsstand).

## Headline ranking (2026-10-31)
- Everyday questions missed the obvious table: "unemployment rate" ranked `earn_nt_unemtrp` (unemployment *trap*) first, because `une_rt_m`'s title lacks the word "rate". Fix: `hints.json` `headline` lists ~50 most-asked Eurostat datasets with the words people use; they rank first among entries that match every query word.
- The marker token must be a made-up word (`zqheadline`): Eurostat theme paths contain "Headline indicators", so the real word collided.
- Broad words ("employment") match thousands of rows, so a headline dataset can fall outside the 600 bm25 candidates. Search runs a second FTS query limited to headline entries and merges both.
- `prc_hicp_manr` (the classic inflation table) ends in 2025; the current one is `prc_hicp_minr` (ECOICOP ver.2).
- Eval: `eval/run_eval.py` over 53 questions: hit@3 14/53 → 53/53. The questions were written alongside the fix; add real ones from the usage log.

## Hosted safety (2026-10-31)
- `*_preview` fetches publisher URLs from third-party metadata. `preview.check_url` resolves the hostname and requires every address to be public, and `web.fetch_prefix` follows redirects by hand so each hop is re-checked (a public URL can redirect to 127.0.0.1).
- Per-client rate limit keys on the first `X-Forwarded-For` hop (Cloud Run, Fly and most proxies set it). Behind no proxy it falls back to the socket address.
- `EUROPA_API_KEYS` uses FastMCP's StaticTokenVerifier (bearer token). Claude.ai custom connectors need OAuth, so keys are off by default.

## Map first, then the API (2026-10-31)
- The APIs can't route a question (Eurostat has no search endpoint; the TOC is titles only), and the map has no codes. So: map → dataset, live API → dimensions/codes/values, which also validates every code.
- `metabase.txt.gz` (4 MB, 1.3M lines `dataset<TAB>dim<TAB>code`) gives every dataset's dimensions in one download. `geo` NUTS level = code length − 2 after dropping aggregates (EU*, EA*, EFTA, EEA); city datasets use a `cities`/`metroreg` dimension, not `geo`. No `freq` dimension in it.
- A removed builder's rows used to stay in the SQLite cache forever (1,300 CBS rows were still served after 0.2.0). `SourceMap.prune()` runs on open.
- Headline rule bug: matching anywhere (incl. the title) made "Part-time employment rate" the headline answer to "employment rate". The span `zqheadline … zqend` holds the headline words (+ breakdowns); only those must cover the query.
- Main-table preference placed before title matches let loosely related `sdg_`/`tps` tables win ("population of cities" → crime-in-area SDG table); it now comes after title matches.
- Staleness cut-off is 3 years: some datasets update every 2–4 years (forest area ends 2024).
- Holdout misses worth fixing with real usage data: "euro area" read as topic words; "pigmeat market prices" matching "GDP at market prices"; "number of cattle" losing to agri-food beef endpoints.
