"""Live smoke test: launch the real europa-mcp server over stdio and exercise every tool.

Usage: .venv/bin/python .claude/skills/test-tools/scripts/smoke.py [--country eu|de|nl] [tool_name ...]
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
    "eurostat_search",
    "eurostat_describe",
    "eurostat_codes",
    "eurostat_data",
    "agri_endpoints",
    "agri_data",
    "ep_meps",
    "ep_votes",
    "ep_query",
    "dataeu_search",
    "dataeu_facets",
    "dataeu_dataset",
    "dataeu_preview",
    "dataeu_sparql",
    "dataeu_quality",
    "dataeu_use_cases",
    "govdata_search",
    "govdata_dataset",
    "govdata_preview",
    "govdata_table",
    "cbs_search",
    "cbs_describe",
    "cbs_codes",
    "cbs_data",
    "cbs_releases",
    "scb_search",
    "scb_describe",
    "scb_codes",
    "scb_data",
    "statfin_search",
    "statfin_describe",
    "statfin_codes",
    "statfin_data",
    "statee_search",
    "statee_describe",
    "statee_codes",
    "statee_data",
    "csb_search",
    "csb_describe",
    "csb_codes",
    "csb_data",
    "find_data",
    "country_guide",
}

# Which tools belong to which country package (the cross-country find_data / country_guide cases are
# assigned by label). A new country adds one entry here and its labels to COUNTRY_LABELS.
COUNTRY_TOOLS = {
    "eu": {t for t in EXPECTED_TOOLS if t.startswith(("eurostat_", "agri_", "ep_", "dataeu_"))},
    "de": {t for t in EXPECTED_TOOLS if t.startswith("govdata_")},
    "nl": {t for t in EXPECTED_TOOLS if t.startswith("cbs_")},
    "se": {t for t in EXPECTED_TOOLS if t.startswith("scb_")},
    "fi": {t for t in EXPECTED_TOOLS if t.startswith("statfin_")},
    "ee": {t for t in EXPECTED_TOOLS if t.startswith("statee_")},
    "lv": {t for t in EXPECTED_TOOLS if t.startswith("csb_")},
}
COUNTRY_LABELS = {
    "de": {"de guide", "German query", "GovData slice"},
    "nl": {"nl guide", "Dutch unemployment", "English house prices"},
    "se": {"se guide", "Swedish unemployment"},
    "fi": {"fi guide", "Finnish consumer prices"},
    "ee": {"ee guide", "Estonian consumer prices"},
    "lv": {"lv guide", "Latvian population"},
}
SHARED = {"find_data", "country_guide", "dataeu_use_cases"}  # tools that serve several countries

# An upstream outage reaches the tool as 'Error: <host> error 500 after 3 attempts' (or unreachable / timed out).
UPSTREAM_DOWN = re.compile(r"^Error: [\w.-]+ (?:error 5\d\d|unreachable|timed out)")

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
    (
        "find_data",
        "house prices (EU + DE)",
        {"query": "house prices"},
        [no_error, ranked, contains("|Eurostat|prc_hpi", "let them choose")],
    ),
    (
        "find_data",
        "headline: unemployment rate",
        {"query": "unemployment rate"},
        [no_error, first_row_id("une_rt_m", "une_rt_a", "une_rt_q", "tps00203", "teilm020")],
    ),
    (
        "find_data",
        "French query",
        {"query": "chômage"},
        [no_error, first_row_id("une_rt_m", "une_rt_a", "une_rt_q", "tps00203", "teilm020")],
    ),
    (
        "country_guide",
        "coverage overview",
        {},
        [no_error, starts("code|country|sources"), contains("\nnl|Netherlands|")],
    ),
    (
        "find_data",
        "no country named",
        {"query": "house prices"},
        [no_error, contains("# No country named. Matches exist for:")],
    ),
    (
        "find_data",
        "uncovered country",
        {"query": "unemployment Slovakia"},
        [no_error, contains("# No national source for geo=SK")],
    ),
    (
        "country_guide",
        "country without a guide",
        {"country": "fr"},
        [starts("No guide for that country yet. Available: eu")],
    ),
    ("find_data", "agri-food synonym", {"query": "pork prices"}, [no_error, contains("pigmeat/prices", "agri_data(")]),
    ("find_data", "parliament", {"query": "how did MEPs vote"}, [no_error, contains("ep_votes(")]),
    # Eurostat family
    (
        "eurostat_search",
        "house prices",
        {"query": "house price index", "limit": 5},
        [no_error, starts("id|title|period|updated"), contains("prc_hpi_q"), max_rows(5)],
    ),
    ("eurostat_search", "DG TAXUD", {"query": "implicit tax", "agency": "taxud"}, [no_error, contains("TAX_ITR")]),
    (
        "eurostat_describe",
        "prc_hpi_q",
        {"dataset_id": "prc_hpi_q"},
        [no_error, starts("PRC_HPI_Q:"), contains("geo|", "unit|")],
    ),
    (
        "eurostat_describe",
        "DG EMPL id with $",
        {"dataset_id": "LMP_EXPME$HR", "agency": "empl"},
        [no_error, contains("LMP_TYPE|")],
    ),
    (
        "eurostat_codes",
        "geo Netherlands",
        {"dataset_id": "prc_hpi_q", "dimension": "geo", "query": "Netherlands"},
        [no_error, contains("NL|Netherlands")],
    ),
    (
        "eurostat_data",
        "NL house price index",
        {"dataset_id": "prc_hpi_q", "filters": {"geo": ["NL"], "purchase": ["TOTAL"], "unit": ["I15_Q"]}, "last_n": 4},
        [no_error, contains("fixed:", "Netherlands"), max_rows(6), cites_source],
    ),
    ("eurostat_data", "too broad rejected", {"dataset_id": "nama_10_gdp"}, [starts("Error: query too broad")]),
    # Agri-food
    ("agri_endpoints", "cereal", {"query": "cereal"}, [no_error, contains("cereal/prices|", "code lookups")]),
    (
        "agri_data",
        "NL pig prices",
        {"endpoint": "pigmeat/prices", "params": {"memberStateCodes": "NL", "pigClasses": "E"}, "limit": 5},
        [no_error, contains("price"), max_rows(7), cites_source],
    ),
    (
        "agri_data",
        "missing required param",
        {"endpoint": "oliveOil/production"},
        [starts("Error: oliveOil/production requires: granularity")],
    ),
    # European Parliament
    (
        "ep_meps",
        "Dutch MEPs",
        {"country": "NL"},
        [no_error, starts("id|name|country|group"), contains("|NL|"), cites_source],
    ),
    (
        "ep_votes",
        "plenary 2026-07-08",
        {"date": "2026-07-08", "roll_call_only": True, "limit": 5},
        [no_error, starts("topic|item|outcome"), max_rows(6)],
    ),
    (
        "ep_query",
        "adopted texts search",
        {"endpoint": "adopted-texts", "params": {"text": "housing"}, "limit": 2},
        [no_error, contains("title:", "files:")],
    ),
    # data.europa.eu
    (
        "dataeu_search",
        "NL datasets",
        {"query": "air quality", "country": "nl", "limit": 5},
        [no_error, starts("id|title|country"), max_rows(6)],
    ),
    (
        "dataeu_search",
        "health, good quality",
        {"query": "hospital", "category": "health", "min_quality": "good", "limit": 3},
        [no_error, starts("id|title|country|catalogue|formats|modified|about"), max_rows(4)],
    ),
    (
        "dataeu_search",
        "newest first",
        {"query": "air quality", "sort": "newest", "limit": 3},
        [no_error, starts("id|title|country"), max_rows(4)],
    ),
    ("dataeu_preview", "unknown dataset", {"dataset_id": "nope-0000"}, [starts("Error: Unknown dataset")]),
    (
        "dataeu_facets",
        "NL air quality by catalogue",
        {"query": "air quality", "country": "nl", "by": "catalogue,format", "top": 5},
        [no_error, contains("datasets match", "catalogue|datasets|name", "format|datasets|name")],
    ),
    (
        "dataeu_sparql",
        "format counts",
        {
            "query": "SELECT ?f (COUNT(*) AS ?n) WHERE { ?d <http://purl.org/dc/terms/format> ?f } GROUP BY ?f ORDER BY DESC(?n)",
            "limit": 3,
        },
        [no_error, starts("f|n")],
    ),
    ("dataeu_sparql", "write rejected", {"query": "DELETE WHERE { ?s ?p ?o }"}, [starts("Error: Only read-only")]),
    ("dataeu_quality", "Netherlands", {"scope": "country", "id": "NLD"}, [no_error, contains("score", "metric|level")]),
    ("dataeu_use_cases", "Dutch use cases", {"country": "Netherlands", "limit": 3}, [no_error, max_rows(4)]),
    # Germany: GovData catalogue + Destatis GENESIS tables
    ("country_guide", "de guide", {"country": "de"}, [no_error, starts("# Germany"), contains("govdata_table")]),
    (
        "find_data",
        "German query",
        {"query": "Bevölkerung Bundesländer"},
        [no_error, ranked, contains("|Destatis|", 'govdata_table("12411-0010")')],
    ),
    (
        "find_data",
        "GovData slice",
        {"query": "groundwater measurements", "sources": ["GovData"]},
        [no_error, contains("govdata_search(")],
    ),
    (
        "govdata_search",
        "English terms translated",
        {"query": "population berlin", "limit": 5},
        [no_error, contains("id|title"), contains("berlin"), max_rows(6)],
    ),
    (
        "govdata_search",
        "Destatis values column",
        {"query": "Bevölkerung Bundesländer", "publisher": "statistisches", "limit": 5},
        [no_error, contains('govdata_table("')],
    ),
    ("govdata_search", "bad theme", {"query": "x", "theme": "space"}, [starts("Error: Unknown theme")]),
    (
        "govdata_dataset",
        "Destatis dataset",
        {"dataset_id": "bevolkerung-bundeslander-stichtag"},
        [no_error, contains('values: govdata_table("12411-0010")', "files (n|format|name|url)")],
    ),
    (
        "govdata_preview",
        "Destatis file redirects",
        {"dataset_id": "bevolkerung-bundeslander-stichtag"},
        [contains('govdata_table("12411-0010")')],
    ),
    (
        "govdata_table",
        "population by state",
        {"table_id": "12411-0010", "query": "Bayern", "last_n": 2},
        [no_error, contains("fixed: label=Bayern", "Stichtag 31.12."), max_rows(8), cites_source],
    ),
    (
        "govdata_table",
        "CPI monthly",
        {"table_id": "61111-0002", "last_n": 1},
        [no_error, contains("Verbraucherpreisindex 2020=100|")],
    ),
    ("govdata_table", "unknown table", {"table_id": "99999-9999"}, [starts("Error: Unknown Destatis table")]),
    # Netherlands: CBS OData
    ("country_guide", "nl guide", {"country": "nl"}, [no_error, starts("# Netherlands"), contains("cbs_data")]),
    (
        "find_data",
        "Dutch unemployment",
        {"query": "werkloosheid"},
        [no_error, ranked, contains("|CBS|", 'cbs_describe("80590ned")')],
    ),
    (
        "find_data",
        "English house prices",
        {"query": "house prices Netherlands", "sources": ["CBS"]},
        [no_error, ranked, contains("cbs_describe(")],
    ),
    (
        "cbs_search",
        "English terms translated",
        {"query": "population municipality", "limit": 5},
        [no_error, contains("id|title"), max_rows(6)],
    ),
    ("cbs_search", "no match", {"query": "zzzzqq"}, [starts("No tables match")]),
    (
        "cbs_describe",
        "population by region",
        {"dataset_id": "37230ned"},
        [no_error, contains("RegioS|", "Perioden|", "M000098|")],
    ),
    (
        "cbs_codes",
        "Den Haag alias",
        {"dataset_id": "37230ned", "dimension": "RegioS", "query": "Den Haag"},
        [no_error, contains("GM0518|")],
    ),
    (
        "cbs_codes",
        "unknown dimension",
        {"dataset_id": "37230ned", "dimension": "Nope"},
        [starts("Error: Unknown dimension")],
    ),
    (
        "cbs_data",
        "Amsterdam population",
        {"dataset_id": "37230ned", "measures": ["M000098"], "filters": {"RegioS": ["GM0363"]}, "latest": True},
        [no_error, contains("fixed: Regio's=Amsterdam"), max_rows(4), cites_source],
    ),
    (
        "cbs_data",
        "measure groups kept",
        {"dataset_id": "80590ned", "latest": True, "limit": 20},
        [no_error, contains("Werkloosheidspercentage: Seizoengecorrigeerd"), cites_source],
    ),
    ("cbs_data", "too broad", {"dataset_id": "37230ned"}, [starts("Error: query too broad")]),
    ("cbs_data", "unknown table", {"dataset_id": "00000xx"}, [starts("Error: Unknown CBS table")]),
    ("cbs_releases", "next week", {"days": 7, "limit": 5}, [no_error, max_rows(6)]),
    # Sweden, Finland, Estonia, Latvia: PxWeb tables
    ("country_guide", "se guide", {"country": "se"}, [no_error, starts("# Sweden"), contains("scb_data", "CKM")]),
    ("country_guide", "fi guide", {"country": "fi"}, [no_error, starts("# Finland"), contains("statfin_data")]),
    (
        "country_guide",
        "ee guide",
        {"country": "ee"},
        [no_error, starts("# Estonia"), contains("statee_data", "CC BY-SA")],
    ),
    ("country_guide", "lv guide", {"country": "lv"}, [no_error, starts("# Latvia"), contains("csb_data")]),
    (
        "find_data",
        "Swedish unemployment",
        {"query": "arbetslöshet", "sources": ["SCB"]},
        [no_error, ranked, contains("|SCB|", "scb_describe(")],
    ),
    (
        "find_data",
        "Finnish consumer prices",
        {"query": "kuluttajahinnat", "sources": ["StatFin"]},
        [no_error, ranked, contains("|StatFin|", "statfin_describe(")],
    ),
    (
        "find_data",
        "Estonian consumer prices",
        {"query": "tarbijahinnad", "sources": ["StatEE"]},
        [no_error, ranked, contains("|StatEE|", "IA002")],
    ),
    (
        "find_data",
        "Latvian population",
        {"query": "iedzīvotāji", "sources": ["CSB"]},
        [no_error, ranked, contains("|CSB|", "csb_describe(")],
    ),
    (
        "scb_search",
        "table found",
        {"query": "population by region marital status age sex"},
        [no_error, contains("BefolkningNy"), max_rows(12)],
    ),
    (
        "scb_describe",
        "population table",
        {"table_id": "BefolkningNy"},
        [no_error, contains("Region|region|", "BE0101N1|Population", "optional"), max_rows(30)],
    ),
    (
        "scb_codes",
        "Gothenburg alias",
        {"table_id": "BefolkningNy", "variable": "region", "query": "Gothenburg"},
        [no_error, contains("1480|Göteborg")],
    ),
    (
        "scb_data",
        "Sweden and Stockholm",
        {"table_id": "BefolkningNy", "filters": {"region": ["00", "0180"], "ContentsCode": ["BE0101N1"]}, "last_n": 1},
        [no_error, contains("Sweden|", "Stockholm|", "licence: CC0 1.0"), cites_source, max_rows(8)],
    ),
    (
        "scb_data",
        "ckm note",
        {"table_id": "BefolkManadCKM", "filters": {"region": ["00"], "Alder": ["TotSA"]}},
        [no_error, contains("# note: this table uses SCB's Cell Key Method")],
    ),
    ("scb_data", "unknown table", {"table_id": "NoSuchTable"}, [starts("Error: Unknown SCB table")]),
    (
        "statfin_search",
        "table found",
        {"query": "key figures population region"},
        [no_error, contains("11ra.px"), max_rows(12)],
    ),
    (
        "statfin_describe",
        "key figures",
        {"table_id": "11ra"},
        [no_error, contains("Area|", "vaerak-vaesto|Population 31 Dec"), max_rows(60)],
    ),
    (
        "statfin_codes",
        "Helsinki",
        {"table_id": "11ra", "variable": "Area", "query": "Helsinki"},
        [no_error, contains("KU091|Helsinki")],
    ),
    (
        "statfin_data",
        "Helsinki population",
        {"table_id": "11ra", "filters": {"Area": ["KU091", "SSS"], "Information": ["vaerak-vaesto"]}, "last_n": 1},
        [no_error, contains("Helsinki|", "WHOLE COUNTRY|", "licence: CC BY 4.0"), cites_source, max_rows(8)],
    ),
    ("statfin_data", "many measures need a choice", {"table_id": "11ra"}, [starts("Error: Choose values for:")]),
    (
        "statee_search",
        "table found",
        {"query": "population by sex age place of residence"},
        [no_error, contains("RV0240"), max_rows(12)],
    ),
    (
        "statee_describe",
        "population table",
        {"table_id": "RV0240"},
        [no_error, contains("Place of residence", "Age"), max_rows(20)],
    ),
    (
        "statee_codes",
        "Tallinn",
        {"table_id": "RV0240", "variable": "Place of residence", "query": "Tallinn"},
        [no_error, contains("784|..Tallinn")],
    ),
    (
        "statee_data",
        "Tallinn population",
        {
            "table_id": "RV0240",
            "filters": {"Place of residence": ["784", "00"], "Age": ["Total"], "Sex": ["Males and females"]},
            "last_n": 1,
        },
        [no_error, contains("..Tallinn|", "Whole country|", "licence: CC BY-SA 4.0"), cites_source, max_rows(6)],
    ),
    (
        "statee_search",
        "archived tables are hidden",
        {"query": "population"},
        [no_error, lambda out: "discontinued tables shown by default" if "[discontinued]" in out else None],
    ),
    ("csb_search", "table found", {"query": "life expectancy"}, [no_error, contains("IRP010"), max_rows(12)]),
    (
        "csb_describe",
        "population by area",
        {"table_id": "POP/IR/IRD/IRD081"},
        [no_error, contains("AREA|Territorial unit|", "SEX|Sex|"), max_rows(20)],
    ),
    (
        "csb_codes",
        "Riga",
        {"table_id": "POP/IR/IRD/IRD081", "variable": "AREA", "query": "Riga"},
        [no_error, contains("LV0001000|Riga")],
    ),
    (
        "csb_data",
        "Riga and Daugavpils",
        {
            "table_id": "POP/IR/IRD/IRD081",
            "filters": {"AREA": ["LV0001000", "LV0002000"], "SEX": ["T"], "AgeGroup": ["TOTAL"]},
        },
        [no_error, contains("Riga|", "Daugavpils|", "Official Statistics Portal"), cites_source, max_rows(6)],
    ),
    ("csb_data", "required choice", {"table_id": "IRS010"}, [starts("Error: Choose values for: INDICATOR")]),
    (
        "csb_data",
        "bad code",
        {"table_id": "IRS010", "filters": {"INDICATOR": ["BAD"]}},
        [starts("Error: Unknown value 'BAD' for INDICATOR")],
    ),
]


def in_country(cc: str, tool: str, label: str) -> bool:
    """Does this case test country `cc`? Shared tools are matched by label; eu takes the rest."""
    if tool in SHARED and tool != "dataeu_use_cases":
        other = set().union(*(v for k, v in COUNTRY_LABELS.items() if k != cc))
        return label in COUNTRY_LABELS[cc] if cc in COUNTRY_LABELS else label not in other
    return tool in COUNTRY_TOOLS[cc]


async def main(only: set[str], country: str | None = None) -> int:
    if not SERVER.exists():
        print(f"FAIL server binary not found: {SERVER} (run `uv sync`)")
        return 1
    transport = StdioTransport(command=str(SERVER), args=[], cwd=str(ROOT))
    failures = 0
    skipped = 0
    async with Client(transport, timeout=180) as c:
        tools = {t.name for t in await c.list_tools()}
        if country:
            missing = COUNTRY_TOOLS[country] - tools
            failures += bool(missing)
            print(
                f"{'FAIL' if missing else 'PASS'}  list_tools ({country}): missing {sorted(missing)}"
                if missing
                else f"PASS  list_tools ({country}): {len(COUNTRY_TOOLS[country])} tools"
            )
        elif not only:
            ok = tools == EXPECTED_TOOLS
            failures += not ok
            print(f"{'PASS' if ok else 'FAIL'}  list_tools: {sorted(tools)}")
        for tool, label, args, checks in CASES:
            if only and tool not in only:
                continue
            if country and not in_country(country, tool, label):
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
            if UPSTREAM_DOWN.match(out):  # the data source is down: nothing this server can fix or prove
                skipped += 1
                print(f"SKIP  {tool} / {label}  ({dt:.1f}s) upstream down: {out[:120]}")
                continue
            status = "FAIL" if errs else "PASS"
            failures += bool(errs)
            print(f"{status}  {tool} / {label}  ({dt:.1f}s, ~{len(out) // 4} tok)")
            for e in errs:
                print(f"      - {e}")
            if errs and out:
                print("      output: " + out[:400].replace("\n", "\n              "))
    total = sum(
        1 for t, label, *_ in CASES if (not only or t in only) and (not country or in_country(country, t, label))
    ) + (0 if only and not country else 1)
    print(
        f"\n{total - failures - skipped}/{total} passed" + (f", {skipped} skipped (upstream down)" if skipped else "")
    )
    return 1 if failures else 0


if __name__ == "__main__":
    argv = sys.argv[1:]
    cc = None
    if "--country" in argv:
        i = argv.index("--country")
        cc = argv[i + 1] if i + 1 < len(argv) else ""
        del argv[i : i + 2]
        if cc not in COUNTRY_TOOLS:
            sys.exit(f"unknown country {cc!r}; known: {', '.join(COUNTRY_TOOLS)}")
    sys.exit(asyncio.run(main(set(argv), cc)))
