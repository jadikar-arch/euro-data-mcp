# Golden test set (20 questions)

End-to-end questions for testing europa-mcp with **any model or app** (Claude, ChatGPT, Copilot,
Cursor, local models…). Each question has an expected answer fetched live from the official
APIs on **2026-10-31** (europa-mcp 0.4.0), the datasets that count as correct, and the source.

Unlike `eval/run_eval.py` (which scores only the dataset search), this tests the whole chain:
the model finds the dataset, lets you choose, fetches the right slice, answers correctly and
cites the source. It also includes a trap (G20) where no official figure exists.

## How to run a test

1. Connect the europa MCP server to the app (see the main README).
2. Open a **new chat** per question and paste the question exactly.
3. When the model shows ranked datasets (or a picker), choose the first one in the *Accepted
   datasets* column if it is offered; otherwise pick its top suggestion and note it.
4. Fill in a row of `scoresheet.csv` (one copy of the rows per model, `model` column filled in),
   answering each check with `y` or `n`.
5. Summarise: `uv run python eval/golden/score.py eval/golden/scoresheet.csv`

## Grading (5 checks per question)

| Check | Pass when |
|---|---|
| `value_ok` | The number matches within tolerance (see `golden_set.json`); for G19/G20 the behaviour matches |
| `dataset_ok` | The model used one of the accepted datasets |
| `citation_ok` | It gave the source link and licence |
| `user_choice_ok` | It showed ranked options and let you choose before fetching (or used the picker) |
| `no_hallucination` | No invented numbers, dataset ids or URLs |

Figures marked provisional (e.g. G03) can be revised by the publisher. If a check fails because
the official figure changed, re-fetch it and update `golden_set.json` rather than failing the model.

## Questions and expected answers

| ID | Area | Question | Expected answer | Accepted datasets |
|---|---|---|---|---|
| G01 | Eurostat · labour | What was the unemployment rate in Spain in 2024? | **11.4%** | `une_rt_a`, `tps00203`, `une_rt_m` |
| G02 | Eurostat · prices | What was the average annual inflation rate in the EU in 2024? | **2.6%** | `prc_hicp_aind`, `prc_hicp_manr`, `prc_hicp_minr` |
| G03 | Eurostat · economy | How large was Germany's GDP in 2024, in euros? | **€4,386,940 million (≈ €4.39 trillion), current prices, provisional** | `nama_10_gdp`, `namq_10_gdp` |
| G04 | Eurostat · population | How many people lived in Poland on 1 January 2025? | **36,497,495** | `tps00001`, `demo_pjan`, `demo_gind` |
| G05 | Eurostat · health | What was life expectancy at birth in Italy in 2023? | **83.3 years** | `demo_mlexpec`, `tps00208` |
| G06 | Eurostat · regional (NUTS 2) | What was the unemployment rate in Andalusia in 2024? | **16.5%** | `tgs00010`, `lfst_r_lfu3rt` |
| G07 | Eurostat · housing | By how much did house prices in the Netherlands rise in the second quarter of 2025 compared with a year earlier? | **+9.5%** | `prc_hpi_q` |
| G08 | Eurostat · public finance | What was Italy's government debt as a share of GDP in 2024? | **134.3% of GDP** | `gov_10dd_edpt1` |
| G09 | Eurostat · energy | What share of Sweden's energy came from renewable sources in 2023? | **66.4%** | `nrg_ind_ren` |
| G10 | Eurostat · earnings | What was the monthly minimum wage in France in the first half of 2026? | **€1,823 per month** | `earn_mw_cur` |
| G11 | Eurostat · living conditions | What share of people in the EU were at risk of poverty or social exclusion in 2024? | **21.0%** | `ilc_peps01n`, `tipslc10` |
| G12 | Eurostat · cities | How many people lived in Amsterdam on 1 January 2024? | **1,073,736 (Amsterdam greater city, Eurostat Urban Audit)** | `urb_cpop1` |
| G13 | Destatis (Germany) | How many people lived in Bavaria on 31 December 2025? | **13,245,503** | `12411-0010`, `12411-0001` |
| G14 | Destatis (Germany) | What was Germany's consumer price index in August 2026, and how much had prices risen in a year? | **125.8 (2020=100); +2.9% on August 2025** | `61111-0002`, `61111-0004` |
| G15 | EU agri-food | What was the price of class E pig carcasses in Germany in week 40 of 2026? | **€155.34 per 100 kg (28 Sep – 4 Oct 2026)** | `pigmeat/prices` |
| G16 | European Parliament | How did the European Parliament vote on the EU–Mexico Interim Agreement on Trade on 8 July 2026? | **Adopted: 474 for, 131 against, 60 abstentions (roll-call)** | `ep_votes` |
| G17 | European Commission · DG TAXUD | What was the implicit tax rate on labour in the Netherlands in 2024? | **31.87%** | `TAX_ITR` |
| G18 | Other language (Spanish) | ¿Cuál fue la tasa de desempleo juvenil (15-24 años) en Italia en 2024? | **20,3 %** | `une_rt_a`, `yth_empl_100`, `tesem140` |
| G19 | data.europa.eu | Find downloadable CSV open datasets about air quality in the Netherlands. | **Real data.europa.eu datasets with CSV files, e.g. 'Air quality' (GGD Amsterdam, id jlag-g3ubn4sha) and 'Air quality The Hague' (id denhaagluchtkwaliteit); about 347 matches** | `dataeu_search` |
| G20 | No official data (hallucination check) | What was the average daily screen time of teenagers in Belgium in 2025? | **No official figure. The closest Eurostat data (time-use survey, tus_20screen, 2020 wave) covers 11 countries and not Belgium.** | `tus_20screen` |

## What each question tests

- **G01–G05, G08–G11:** headline Eurostat indicators with a fixed period, correct unit and filter.
- **G06:** regional routing (NUTS 2); the national figure is a wrong answer.
- **G07:** choosing the right measure (rate of change, not an index level).
- **G12:** city data, and honesty about the "greater city" definition.
- **G13–G14:** German national data via Destatis (German labels).
- **G15:** EU agri-food weekly prices with dates.
- **G16:** European Parliament roll-call votes.
- **G17:** Commission DG data (agency `taxud`).
- **G18:** a non-English question, answered in the same language.
- **G19:** data.europa.eu catalogue search with real, checkable dataset ids.
- **G20:** no official figure exists: the model must say so rather than invent one.
