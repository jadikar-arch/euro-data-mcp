# Statistics Estonia PxWeb v1: probe findings (2026-11-21)
- Base `https://andmed.stat.ee/api/v1/en/stat` (English). Keyless JSON. Licence **CC BY-SA 4.0** (ShareAlike), from the office's dissemination principles.
- One-request listing (`?query=*&filter=*`): 4,998 tables in 0.5 s, 1.2 MB. **2,857 of them sit in `Lepetatud_tabelid` ("discontinued tables")**, hidden by default (`include_discontinued=true` shows them).
- Table ids end `.PX` or `.px` (case differs). Titles are in capitals and start with the code. Variable codes are Estonian (`Sugu`, `Elukoht`, `Aasta`, `Vanus`, `Näitaja`), their English names work. Value labels carry hierarchy dots (`..Tallinn`), ignored when matching.
- Tables have no `ContentsCode` variable: the measure is the table itself or a `Näitaja` (indicator) variable that must be chosen.
- Folders `majandus/valiskaubandus/{kaupade_valiskaubandus,kaupade_TEC,teenuste_valiskaubandus}` and `keskkond/keskkonnaseisund` list as folders but answer HTTP 400; no foreign-trade table is in the listing. No crime tables found.
- Verified: RV0240 population 1 Jan 2026 whole country 1,360,745, Tallinn (784) 452,563.
- Human page: `https://andmed.stat.ee/en/stat/<folders joined by __>/<table>` (with or without `.PX`).
