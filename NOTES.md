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
