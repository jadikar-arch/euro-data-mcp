"""Live smoke test: launch the real europa-mcp server over stdio and exercise every tool.

Usage: .venv/bin/python .claude/skills/test-tools/scripts/smoke.py [tool_name ...]
Exit code 0 = all checks passed, 1 = at least one failed.
"""

from __future__ import annotations

import asyncio
import re
import sys
import time
from collections.abc import Callable
from pathlib import Path

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

ROOT = Path(__file__).resolve().parents[4]
SERVER = ROOT / ".venv" / "bin" / "europa-mcp"
MAX_CHARS = 8000  # ~2k tokens; tool outputs should stay well under this
EXPECTED_TOOLS = {
    "eurostat_search", "eurostat_describe", "eurostat_codes", "eurostat_data",
    "agri_endpoints", "agri_data", "ep_meps", "ep_votes", "ep_query",
    "dataeu_search", "dataeu_facets", "dataeu_dataset", "dataeu_preview", "dataeu_sparql", "dataeu_quality", "dataeu_use_cases",
    "govdata_search", "govdata_dataset", "govdata_preview", "govdata_table",
    "find_data", "country_guide",
}

Check = Callable[[str], str | None]  # returns an error message, or None when OK


def contains(*needles: str) -> Check:
    return lambda out: next((f"missing {n!r}" for n in needles if n not in out), None)


def starts(prefix: str) -> Check:
    return lambda out: None if out.startswith(prefix) else f"expected to start with {prefix!r}"


def no_error(out: str) -> str | None:
    return f"tool returned {out.splitlines()[0]!r}" if out.startswith("Error") else None


def max_rows(n: int) -> Check:
    def check(out: str) -> str | None:
        rows = [line for line in out.splitlines()[1:] if not line.startswith(("#", "source:"))]
        return None if len(rows) <= n else f"{len(rows)} rows > limit {n}"
    return check


def cites_source(out: str) -> str | None:
    last = out.strip().splitlines()[-1] if out.strip() else ""
    return None if last.startswith("source: http") and " · licence: " in last else f"no source line: {last[:80]!r}"


def first_row_id(*ids: str) -> Check:
    """find_data's rank-1 row: rank|match|source|id|…"""
    def check(out: str) -> str | None:
        row = next((ln for ln in out.splitlines() if ln.startswith("1|")), "")
        got = row.split("|")[3] if row.count("|") >= 3 else ""
        return None if got in ids else f"rank 1 is {row[:70]!r}, want one of {ids}"
    return check


def ranked(out: str) -> str | None:
    lines = out.splitlines()
    ok = len(lines) > 2 and lines[1] == "rank|match|source|id|title|period|breakdowns|next call"
    return None if ok else "not a ranked list"


# (tool, label, args, checks)
CASES: list[tuple[str, str, dict, list[Check]]] = [
    # Cross-source map
    ("find_data", "house prices (EU + DE)", {"query": "house prices"},
     [no_error, ranked, contains("|Eurostat|prc_hpi", "let them choose")]),
    ("find_data", "headline: unemployment rate", {"query": "unemployment rate"},
     [no_error, first_row_id("une_rt_m", "une_rt_a", "une_rt_q", "tps00203", "teilm020")]),
    ("find_data", "French query", {"query": "chômage"},
     [no_error, first_row_id("une_rt_m", "une_rt_a", "une_rt_q", "tps00203", "teilm020")]),
    ("country_guide", "removed country", {"country": "nl"},
     [starts("Unknown country. Available: eu")]),
    ("find_data", "agri-food synonym", {"query": "pork prices"},
     [no_error, contains("pigmeat/prices", "agri_data(")]),
    ("find_data", "parliament", {"query": "how did MEPs vote"},
     [no_error, contains("ep_votes(")]),
    # Eurostat family
    ("eurostat_search", "house prices", {"query": "house price index", "limit": 5},
     [no_error, starts("id|title|period|updated"), contains("prc_hpi_q"), max_rows(5)]),
    ("eurostat_search", "DG TAXUD", {"query": "implicit tax", "agency": "taxud"},
     [no_error, contains("TAX_ITR")]),
    ("eurostat_describe", "prc_hpi_q", {"dataset_id": "prc_hpi_q"},
     [no_error, starts("PRC_HPI_Q:"), contains("geo|", "unit|")]),
    ("eurostat_describe", "DG EMPL id with $", {"dataset_id": "LMP_EXPME$HR", "agency": "empl"},
     [no_error, contains("LMP_TYPE|")]),
    ("eurostat_codes", "geo Netherlands", {"dataset_id": "prc_hpi_q", "dimension": "geo", "query": "Netherlands"},
     [no_error, contains("NL|Netherlands")]),
    ("eurostat_data", "NL house price index",
     {"dataset_id": "prc_hpi_q", "filters": {"geo": ["NL"], "purchase": ["TOTAL"], "unit": ["I15_Q"]}, "last_n": 4},
     [no_error, contains("fixed:", "Netherlands"), max_rows(6), cites_source]),
    ("eurostat_data", "too broad rejected", {"dataset_id": "nama_10_gdp"},
     [starts("Error: query too broad")]),
    # Agri-food
    ("agri_endpoints", "cereal", {"query": "cereal"},
     [no_error, contains("cereal/prices|", "code lookups")]),
    ("agri_data", "NL pig prices", {"endpoint": "pigmeat/prices", "params": {"memberStateCodes": "NL", "pigClasses": "E"}, "limit": 5},
     [no_error, contains("price"), max_rows(7), cites_source]),
    ("agri_data", "missing required param", {"endpoint": "oliveOil/production"},
     [starts("Error: oliveOil/production requires: granularity")]),
    # European Parliament
    ("ep_meps", "Dutch MEPs", {"country": "NL"},
     [no_error, starts("id|name|country|group"), contains("|NL|"), cites_source]),
    ("ep_votes", "plenary 2026-07-08", {"date": "2026-07-08", "roll_call_only": True, "limit": 5},
     [no_error, starts("topic|item|outcome"), max_rows(6)]),
    ("ep_query", "adopted texts search", {"endpoint": "adopted-texts", "params": {"text": "housing"}, "limit": 2},
     [no_error, contains("title:", "files:")]),
    # data.europa.eu
    ("dataeu_search", "NL datasets", {"query": "air quality", "country": "nl", "limit": 5},
     [no_error, starts("id|title|country"), max_rows(6)]),
    ("dataeu_search", "health, good quality", {"query": "hospital", "category": "health", "min_quality": "good", "limit": 3},
     [no_error, starts("id|title|country|catalogue|formats|modified|about"), max_rows(4)]),
    ("dataeu_search", "newest first", {"query": "air quality", "sort": "newest", "limit": 3},
     [no_error, starts("id|title|country"), max_rows(4)]),
    ("dataeu_preview", "unknown dataset", {"dataset_id": "nope-0000"},
     [starts("Error: Unknown dataset")]),
    ("dataeu_facets", "NL air quality by catalogue", {"query": "air quality", "country": "nl", "by": "catalogue,format", "top": 5},
     [no_error, contains("datasets match", "catalogue|datasets|name", "format|datasets|name")]),
    ("dataeu_sparql", "format counts",
     {"query": "SELECT ?f (COUNT(*) AS ?n) WHERE { ?d <http://purl.org/dc/terms/format> ?f } GROUP BY ?f ORDER BY DESC(?n)", "limit": 3},
     [no_error, starts("f|n")]),
    ("dataeu_sparql", "write rejected", {"query": "DELETE WHERE { ?s ?p ?o }"},
     [starts("Error: Only read-only")]),
    ("dataeu_quality", "Netherlands", {"scope": "country", "id": "NLD"},
     [no_error, contains("score", "metric|level")]),
    ("dataeu_use_cases", "Dutch use cases", {"country": "Netherlands", "limit": 3},
     [no_error, max_rows(4)]),
    # Germany: GovData catalogue + Destatis GENESIS tables
    ("country_guide", "de guide", {"country": "de"},
     [no_error, starts("# Germany"), contains("govdata_table")]),
    ("find_data", "German query", {"query": "Bevölkerung Bundesländer"},
     [no_error, ranked, contains("|Destatis|", 'govdata_table("12411-0010")')]),
    ("find_data", "GovData slice", {"query": "groundwater measurements", "sources": ["GovData"]},
     [no_error, contains("govdata_search(")]),
    ("govdata_search", "English terms translated", {"query": "population berlin", "limit": 5},
     [no_error, contains("id|title"), contains("berlin"), max_rows(6)]),
    ("govdata_search", "Destatis values column", {"query": "Bevölkerung Bundesländer", "publisher": "statistisches", "limit": 5},
     [no_error, contains('govdata_table("')]),
    ("govdata_search", "bad theme", {"query": "x", "theme": "space"},
     [starts("Error: Unknown theme")]),
    ("govdata_dataset", "Destatis dataset", {"dataset_id": "umgeschlagene-guter-umgeschlagene-container-binnenschifffahrt-bundeslander-monate"},
     [no_error, contains('values: govdata_table("46321-0101")', "files (n|format|name|url)")]),
    ("govdata_preview", "Destatis file redirects", {"dataset_id": "umgeschlagene-guter-umgeschlagene-container-binnenschifffahrt-bundeslander-monate"},
     [contains('govdata_table("46321-0101")')]),
    ("govdata_table", "population by state", {"table_id": "12411-0010", "query": "Bayern", "last_n": 2},
     [no_error, contains("fixed: label=Bayern", "Stichtag 31.12."), max_rows(8), cites_source]),
    ("govdata_table", "CPI monthly", {"table_id": "61111-0002", "last_n": 1},
     [no_error, contains("Verbraucherpreisindex 2020=100|")]),
    ("govdata_table", "unknown table", {"table_id": "99999-9999"},
     [starts("Error: Unknown Destatis table")]),
]


async def main(only: set[str]) -> int:
    if not SERVER.exists():
        print(f"FAIL server binary not found: {SERVER} (run `uv sync`)")
        return 1
    transport = StdioTransport(command=str(SERVER), args=[], cwd=str(ROOT))
    failures = 0
    async with Client(transport, timeout=180) as c:
        tools = {t.name for t in await c.list_tools()}
        if not only:
            ok = tools == EXPECTED_TOOLS
            failures += not ok
            print(f"{'PASS' if ok else 'FAIL'}  list_tools: {sorted(tools)}")
        for tool, label, args, checks in CASES:
            if only and tool not in only:
                continue
            t0 = time.perf_counter()
            try:
                r = await c.call_tool(tool, args, raise_on_error=False)
                out = "".join(getattr(b, "text", "") for b in r.content)
                errs = [e for chk in checks if (e := chk(out))]
            except Exception as e:  # noqa: BLE001
                out, errs = "", [f"{type(e).__name__}: {e}"]
            if len(out) > MAX_CHARS:
                errs.append(f"response too large ({len(out)} chars)")
            dt = time.perf_counter() - t0
            status = "FAIL" if errs else "PASS"
            failures += bool(errs)
            print(f"{status}  {tool} / {label}  ({dt:.1f}s, ~{len(out) // 4} tok)")
            for e in errs:
                print(f"      - {e}")
            if errs and out:
                print("      output: " + out[:400].replace("\n", "\n              "))
    total = sum(1 for t, *_ in CASES if not only or t in only) + (0 if only else 1)
    print(f"\n{total - failures}/{total} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(set(sys.argv[1:]))))
