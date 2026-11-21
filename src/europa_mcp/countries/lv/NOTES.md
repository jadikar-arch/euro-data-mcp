# CSB Latvia (Official Statistics Portal) PxWeb v1: probe findings (2026-11-21)
- Base `https://data.stat.gov.lv/api/v1/en/OSP_PUB`. Keyless JSON. Terms (About page "Licence and copyright notice"): commercial and non-commercial reuse allowed with attribution of the responsible authority and the portal, "correspond to CC BY 4.0"; modified data must be marked as such.
- One-request listing: 1,575 tables in 0.3 s (the full folder walk finds 1,659 because some tables sit in two folders). 164 are in archive folders named `A_…`, hidden by default.
- The root lists `POP`, `EMP`, … (the `START` folder is implicit); ids are `POP/IR/IRS/IRS010`. The human page needs the `START__` prefix: `…/pxweb/en/OSP_PUB/START__POP__IR__IRS/IRS010/`.
- Symbols: `X` = not available (also in the per-1,000 measure of population tables), `-`, `..`.
- Several codes can share a label (`Riga`: `LV0001000` city, `LVDPA0001` densely populated area).
- No crime table. House-price index tables exist (`VEK/PC/PCI/PCI050c`); a substring search first returned gas prices "for household consumers" for `house prices`, which is why matching is by whole word.
- Verified: IRD081 Riga 588,911 and Daugavpils 77,486 (1 Jan 2026).
