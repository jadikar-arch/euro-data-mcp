# StatFin (Statistics Finland) PxWeb v1: probe findings (2026-11-21)
- Base `https://pxdata.stat.fi/PxWeb/api/v1/en/StatFin`. Keyless JSON, licence CC BY 4.0.
- **Rate limit:** HTTP 429 with `Retry-After: 60` when called too fast (seen above roughly 30 requests a minute). The folder walk (136 folders) took 6 minutes and lost folders to 429s; tools keep to 24 calls a minute (`per_minute`).
- `GET <base>?query=*&filter=*` lists every table in **one request** (1,537 tables, 285 KB, 0.3 s): `{id, path, title, published}`. The same endpoint exists at Statistics Estonia and Latvia, not at SCB. It gives folder codes, not folder names, so rows have no topic trail.
- Table ids are `<folder>/<code>.px` (`vaerak/11rb.px`). Titles start with the code (`11rb -- Population …`) and end with the period range. One folder (`akay`) answers 400 for good.
- Variable codes are Finnish and table-specific (`alue_23_20260101` = Area as of 1 Jan 2026, `timeperiod_y`, `contentscode`). Many tables have 40+ measures (11ra: 43), so `statfin_data` asks which to select (> 6).
- Area codes: `SSS` whole country, `KU091` Helsinki. Period codes `2025`, `2026Q3`, `2026M09`.
- Verified: 11rb population 31 Dec 2025 = 5,652,881; Helsinki (KU091) 694,392.
- Human page: `https://pxdata.stat.fi/PxWeb/pxweb/en/StatFin/StatFin__<folder>/<table>.px/`.
