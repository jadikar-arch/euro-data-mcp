"""Helpers shared by every country package: errors, error wrapping, text and compact tables."""

from __future__ import annotations

import functools
import json
import logging
import os
import unicodedata
from importlib.resources import files
from pathlib import Path
from typing import Any

from platformdirs import user_cache_dir

log = logging.getLogger("europa_mcp")


def setting(name: str, default: str = "") -> str:
    """EUROPA_<name> from the environment."""
    return os.environ.get(f"EUROPA_{name}") or default


def load_hints(package: str) -> dict[str, Any]:
    """A country package's hand-written hints.json (sources, synonyms, keywords, headline, entries)."""
    data = json.loads(files(package).joinpath("hints.json").read_text("utf-8"))
    keys = ("sources", "synonyms", "keywords", "headline", "entries")
    return {k: data.get(k) or ({} if k != "entries" else []) for k in keys}


def cache_dir() -> Path:
    path = Path(setting("CACHE_DIR") or user_cache_dir("europa-mcp"))
    path.mkdir(parents=True, exist_ok=True)
    return path


class UserError(Exception):
    """A user-facing error: the message is safe to return to the model."""


class NotFound(UserError):
    pass


# Query words that never help ranking. English, German, French, Spanish, Italian and Dutch, so a
# question asked in any of them is reduced to its topic words.
STOPWORDS = set(
    # English
    "the a an and or of in on for with per to by from is are what how many much which latest "
    "recent current newest number total data statistics figures table measurements measurement "
    "europe european eu "
    # German
    "der die das des dem den und oder fur vom im mit wie viel viele welche zahl anzahl daten "
    "deutschland germany german destatis govdata "
    # French
    "le la les un une des du et ou en au aux pour par sur dans est sont quel quelle quels combien "
    "donnees statistiques nombre "
    # Spanish
    "el los las y o en por para con es son que cual cuantos cuantas datos estadisticas numero "
    # Italian
    "il lo gli e o di da per con su che quale quanti quante dati statistiche numero "
    # Countries (English names): datasets are per topic, the country is a filter applied later
    "austria belgium bulgaria croatia cyprus czechia czech denmark estonia finland france greece "
    "hungary ireland italy latvia lithuania luxembourg malta netherlands poland portugal romania "
    "slovakia slovenia spain sweden norway iceland liechtenstein switzerland turkey turkiye "
    "albania montenegro serbia macedonia ukraine moldova "
    # Swedish, Finnish, Estonian and Latvian places: the city is a code picked later, not a topic
    "stockholm gothenburg goteborg malmo uppsala helsinki espoo tampere vantaa oulu turku tallinn tartu "
    "narva parnu riga daugavpils liepaja jelgava jurmala lapland sverige suomi eesti latvija "
    # Dutch places: CBS tables are per topic, the municipality or province is a code picked later
    "amsterdam rotterdam utrecht eindhoven groningen tilburg almere breda nijmegen haarlem maastricht "
    "arnhem zwolle leiden dordrecht hague haag gravenhage drenthe flevoland friesland fryslan gelderland "
    "limburg brabant overijssel zeeland holland "
    # Swedish, Finnish, Estonian and Latvian filler words ('number of', 'and')
    "och antal av för ja lukumaara maara ning arv un skaits "
    # Dutch
    "de het een en van op voor met naar over bij uit door zijn wat hoe hoeveel welke gegevens "
    "cijfers aantal".split()
)


def fold(s: str) -> str:
    """Lowercase and strip accents (matches the FTS `remove_diacritics` tokenizer)."""
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).casefold()


READ_ONLY = {"readOnlyHint": True, "openWorldHint": True}


def safe(fn):
    """Turn known errors into short strings; never leak tracebacks to the model."""

    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        try:
            return await fn(*args, **kwargs)
        except UserError as e:
            return f"Error: {e}"
        except Exception as e:  # noqa: BLE001
            log.exception("tool %s failed", fn.__name__)
            return f"Error: internal failure ({type(e).__name__}). Try again or simplify."

    return wrapper


def fmt_value(v: Any) -> str:
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() else str(round(v, 6))
    return str(v)


def cell(s: Any) -> str:
    return str(s).replace("|", "/").replace("\n", " ")


def clip(s: Any, n: int = 200) -> str:
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[:n].rsplit(" ", 1)[0] + "…"


def compact_table(cols: list[str], table: list[list[str]], keep_last: bool = True) -> list[str]:
    """`fixed: col=v; …` for columns constant across rows, then a `|` table of the rest."""
    if not table:
        return []
    last = len(cols) - 1
    keep = [i for i in range(len(cols)) if (keep_last and i == last) or len({t[i] for t in table}) > 1] or [last]
    out = []
    fixed = [f"{cols[i]}={table[0][i]}" for i in range(len(cols)) if i not in keep and table[0][i]]
    if fixed:
        out.append("fixed: " + "; ".join(cell(f) for f in fixed))
    out.append("|".join(cell(cols[i]) for i in keep))
    out += ["|".join(cell(t[i]) for i in keep) for t in table]
    return out


def as_list(v: Any) -> list[str]:
    """Accept 'a', 'a,b' or ['a','b'] from the model."""
    if v is None:
        return []
    items = v if isinstance(v, (list, tuple, set)) else str(v).split(",")
    return [s for s in (str(x).strip() for x in items) if s]


def source_line(url: str, licence: str) -> str:
    """Last line of every data answer, so the model can cite where the numbers come from."""
    return f"source: {url} · licence: {licence}"


EC_LICENCE = "CC BY 4.0, © European Union"  # Commission reuse policy (Decision 2011/833/EU)


# Country names, demonyms and big cities (folded) → Eurostat `geo` code, so find_data can tell the user which
# national source covers the country they named (or that only Eurostat does) and lead with it.
COUNTRY_NAMES: dict[str, str] = {
    **{
        name: code
        for code, names in {
            "AT": "austria austrian",
            "BE": "belgium belgian",
            "BG": "bulgaria bulgarian",
            "HR": "croatia croatian",
            "CY": "cyprus cypriot",
            "CZ": "czechia czech",
            "DK": "denmark danish",
            "EE": "estonia estonian eesti tallinn tartu narva parnu",
            "FI": "finland finnish suomi helsinki espoo tampere vantaa oulu turku",
            "FR": "france french",
            "DE": "germany german deutschland berlin hamburg munich munchen cologne koln frankfurt stuttgart dusseldorf",
            "EL": "greece greek",
            "HU": "hungary hungarian",
            "IE": "ireland irish",
            "IT": "italy italian",
            "LV": "latvia latvian latvija riga daugavpils liepaja jelgava jurmala",
            "LT": "lithuania lithuanian",
            "LU": "luxembourg",
            "MT": "malta maltese",
            "NL": "netherlands dutch nederland holland amsterdam rotterdam utrecht eindhoven groningen tilburg almere breda nijmegen haarlem maastricht",
            "PL": "poland polish",
            "PT": "portugal portuguese",
            "RO": "romania romanian",
            "SK": "slovakia slovak",
            "SI": "slovenia slovenian",
            "ES": "spain spanish",
            "SE": "sweden swedish sverige stockholm gothenburg goteborg malmo uppsala",
            "NO": "norway norwegian",
            "IS": "iceland icelandic",
            "CH": "switzerland swiss",
        }.items()
        for name in names.split()
    },
}


def countries_in(query: str) -> list[str]:
    """Eurostat geo codes of the countries a question names, in order, without repeats."""
    import re

    words = re.findall(r"\w+", fold(query))
    return list(dict.fromkeys(COUNTRY_NAMES[w] for w in words if w in COUNTRY_NAMES))
