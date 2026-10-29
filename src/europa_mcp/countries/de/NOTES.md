# Germany APIs: probe findings (2026-10-18)

- **GovData** `https://ckan.govdata.de/api/3/action` (also at `www.govdata.de/ckan/api/3/action`): CKAN 2.10 with the `dcatde` extension, keyless, no rate-limit headers seen. **Catalogue only**: `datastore_search` is not enabled ("Action name not known"), so values live in the linked files and services.
  - `package_search?q=&fq=organization:X AND groups:Y&rows=&start=&sort=`: 168,671 datasets. Titles, descriptions and tags are German only (`population` finds 151 datasets, `bevölkerung` thousands).
  - Facets (`facet.field=["groups","organization","res_format","tags"]`, `facet.limit=`, `rows=0`): 13 groups with DCAT-AP theme codes (`envi` Umwelt 56k, `regi` 48k, `gove` 43k, `econ` 30k, `tech`, `soci`, `agri`, `educ`, `tran`, `ener`, `heal` 3.9k, `just`, `intr`). 77 organizations; most datasets come from the states (Schleswig-Holstein 29k, GDI-DE 27k, Bayern 27k, Brandenburg, Hamburg, Rheinland-Pfalz, NRW) plus Destatis (3,153).
  - Formats are mostly EU file-type URIs (`…/file-type/CSV`), sometimes bare (`CSV`, `WMS`). Licences are in `license_id` as `dcat-ap.de/def/licenses/…` but often empty; the useful DCAT-AP.de fields sit in `extras` (`politicalGeocodingLevelURI` = federal/state/municipality, `issued`, `modified`, `publisher_name`, `contributorID`).
  - Organization and group lists: `organization_list`, `group_list?all_fields=true`.
- **GovData SPARQL** `https://www.govdata.de/sparql` (send `Accept: application/sparql-results+json`): 200,080 `dcat:Dataset`. Overlaps `dataeu_sparql`, so it is not wrapped.
- **data.europa.eu** already harvests German portals (850,421 datasets with `country=de`, more than GovData), so plain keyword search over GovData adds little. What GovData adds: German themes, publishers and administrative levels as facets, and direct Destatis table files.
- **Destatis GENESIS downloads** (linked from the 3,153 Destatis datasets; `extras.identifier`): `https://genesis.destatis.de/genesisWS/downloads/00/tables/<table>_00.csv` (also `.xml`), keyless.
  - The CSV is ISO-8859-1 and `;`-separated. Its first rows are `Tabelle: 46321-0101`, the title and the statistic name; then 1–3 header rows (years, months), then rows of row labels (e.g. state; measure; unit) followed by values.
  - Missing values are `-` (zero) and `...` (not yet available); `.` means secret, `x` not applicable, `/` too uncertain. Files are tens of KB to MBs, so download once and cache.
  - Table IDs are `NNNNN-NNNN` (`12411-0001` population).
- **GENESIS official API** `https://genesis.destatis.de/genesisWS/rest/2020/` (Swagger at `/genesisWS/swagger-ui/index.html`; `www-genesis` redirects here): POST only (GET returns 405). `helloworld/logincheck` logs in as `GAST`, but `catalogue/*` and `data/*` return 401 Code 15 without a registered account (free; username and password or API token in the headers).
- **GENESIS web-app API** `https://genesis.destatis.de/genesis/api/rest/` (base from `/datenbank/online/environment.json`; undocumented, used by the website, so it may change): keyless GET with `language=en|de`, labels in German and English.
  - `statistics` lists 331 statistics; `statistics/{code}/tables` lists 3,045 tables in total; `search?searchTerm=` returns matching statistic and table codes.
  - `tables/{id}/information` (variables and definitions), `tables/{id}/structure` (label, notes, lastChange), `tables/{id}/data` (JSON-stat-like `{data:[{id,size,dimension,…}]}`). `12411-0010` has 68 reference dates vs 10 in the GovData CSV.
  - `tables/{id}/download/{format}/{lang}` returns 405 on GET.
