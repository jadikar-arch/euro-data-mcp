"""Country packages. Each `countries/<cc>/` (ISO 3166-1 alpha-2, or `eu`) exposes:

- CODE, NAME            e.g. "de", "Germany"
- HINTS                 load_hints(__name__): its hints.json (source blurbs, synonyms, keywords, entries)
- SYNONYMS              English → local-language terms (applied both ways by find_data)
- register(mcp)         add the country's tools, named `<source>_<verb>` (e.g. govdata_search)
- map_builders()        {builder name: async () -> list[Entry]} for the find_data map
- start() / stop()      background tasks and client cleanup (server lifespan)

Its usage guide for the model lives in `europa_mcp/skills/<cc>/SKILL.md`.
To add a country, follow the `add-country` Claude Code skill in this repo.
"""

from __future__ import annotations

from types import ModuleType

from . import de, eu

COUNTRIES: list[ModuleType] = [eu, de]
