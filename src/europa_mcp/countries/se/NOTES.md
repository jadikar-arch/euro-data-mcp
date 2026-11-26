# SCB (Statistics Sweden) PxWeb v1: probe findings (2026-11-21)
- Base `https://api.scb.se/OV0104/v1/doris/en/ssd` (English). Keyless JSON. Licence: CC0 for the open data of the database and API; SCB suggests "Source: Statistics Sweden". Limit: 10 calls per 10 seconds per IP.
- No table-search endpoint (`?query=` answers 400), so the catalogue is built by walking the folder tree: ~300 folders, **3,386 tables, ~12 minutes** at 55 calls a minute. Saved for 24 h in the cache directory (`pxweb-scb.json`); the server builds it in the background at start.
- Folder texts give the topic trail ("Population > Population statistics > Number of inhabitants"), used for ranking and `topic:` in describe.
- Table: GET `<table>` → `variables` (`code`, `text`, `values`, `valueTexts`, `elimination`, `time`). Data: POST `{"query": [{"code", "selection": {"filter": "item|top|all", "values"}}], "response": {"format": "json"}}` → `columns` (d/t/c) and `data` rows `{key, values}`. Variables with `elimination: true` may be left out (the server aggregates); the others must be selected.
- Time series are split: `BefolkningNy` ends 2024, `BefolkningCKM` holds 2025, `BefolkManadCKM` the months of 2025-26.
- Tables ending `CKM` use SCB's Cell Key Method (counts randomly adjusted by up to ±3; totals need not add up; from spring 2025 for population statistics). `scb_data` and `scb_describe` print this.
- Region codes: `00` Sweden, 2 digits county (län), 4 digits municipality (kommun); labels are Swedish place names (`Göteborg`), alias `gothenburg` → `goteborg`.
- Verified: BefolkningNy 2024 Sweden 10,587,710, Stockholm (0180) 995,574.
- No police-crime table (published by another body); no tourism table matched.
