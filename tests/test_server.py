from fastmcp import Client

from europa_mcp import server


async def call(name: str, **args) -> str:
    async with Client(server.mcp) as c:
        result = await c.call_tool(name, args, raise_on_error=False)
    return "".join(getattr(b, "text", "") for b in result.content)


async def test_tools_listed_with_short_docs():
    async with Client(server.mcp) as c:
        tools = {t.name: t for t in await c.list_tools()}
    assert set(tools) == {
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
        "find_data",
        "country_guide",
    }
    for t in tools.values():
        assert len(t.description.strip().splitlines()) <= 3
        assert t.output_schema is None  # text only, no duplicated structured payload
        assert t.annotations.read_only_hint


async def test_instructions_carry_disclaimer_and_citation_rule():
    assert "not affiliated" in server.INSTRUCTIONS
    assert "source:" in server.INSTRUCTIONS


async def test_country_guides_served_as_tool_and_skill_resources():
    out = await call("country_guide", country="Germany")
    assert out.startswith("# Germany") and "name: de" not in out  # frontmatter dropped
    assert (await call("country_guide", country="EU")).startswith("# EU level")
    out = await call("country_guide", country="Netherlands")
    assert out.startswith("# Netherlands") and "cbs_search" in out
    out = await call("country_guide", country="fr")
    assert (
        out.startswith("No guide for that country yet. Available: eu")
        and 'dataeu_search(query, country="<iso2>")' in out
    )
    async with Client(server.mcp) as c:
        uris = {str(r.uri) for r in await c.list_resources()}
        assert {"skill://eu/SKILL.md", "skill://de/SKILL.md", "skill://nl/SKILL.md"} <= uris
        text = (await c.read_resource("skill://de/SKILL.md"))[0].text
    assert "govdata_search" in text


def test_every_country_has_a_skill_and_hints():
    from europa_mcp.countries import COUNTRIES

    assert [c.CODE for c in COUNTRIES] == ["eu", "de", "nl"]
    for c in COUNTRIES:
        assert (server.SKILLS_DIR / c.CODE / "SKILL.md").is_file(), c.CODE
        assert set(c.HINTS["sources"]) <= set(server.SOURCES)


PROFILE_ROWS = (
    "Country / code",
    "Languages",
    "APIs",
    "Access",
    "Licence",
    "Data types",
    "Geographic detail",
    "Tools",
    "Use instead",
)


async def test_every_country_skill_has_the_standard_profile_and_names_real_tools():
    import re

    from europa_mcp.countries import COUNTRIES

    async with Client(server.mcp) as client:
        registered = {t.name for t in await client.list_tools()}
    for c in COUNTRIES:
        text = (server.SKILLS_DIR / c.CODE / "SKILL.md").read_text("utf-8")
        assert text.startswith(f"---\nname: {c.CODE}\n"), c.CODE
        profile = text.split("## Profile", 1)[1].split("\n## ", 1)[0]
        assert [m for m in PROFILE_ROWS if f"| {m} |" not in profile] == [], c.CODE
        assert f"(`{c.CODE}`)" in profile, c.CODE
        row = profile.split("| Tools |", 1)[1].split("\n", 1)[0]
        # `a/b/c` shorthand after a prefix: eurostat_search/describe → eurostat_search, eurostat_describe
        named = set()
        for group in re.findall(r"`([a-z_]+_[a-z_/]+)", row):
            prefix, *rest = group.split("/")
            stem = prefix.rsplit("_", 1)[0]
            named |= {prefix, *(f"{stem}_{r}" for r in rest)}
        assert named and named <= registered, (c.CODE, sorted(named - registered))


async def test_index_skill_lists_every_country_and_is_served():
    from europa_mcp.countries import COUNTRIES

    text = (server.SKILLS_DIR / "overview" / "SKILL.md").read_text("utf-8")
    assert text.startswith("---\nname: overview\n")
    for c in COUNTRIES:
        assert f"| `{c.CODE}` |" in text and f"skill://{c.CODE}/SKILL.md" in text, c.CODE
    async with Client(server.mcp) as client:
        uris = {str(r.uri) for r in await client.list_resources()}
    assert "skill://overview/SKILL.md" in uris


async def test_country_guide_serves_the_index_skill_too():
    out = await call("country_guide", country="overview")
    assert out.startswith("# Overview: how to answer a data question") and "skill://nl/SKILL.md" in out


RULE_PHRASES = (
    "Source every answer.",
    "Only fetched data.",
    "No mixing.",
    "Ask when unclear.",
    "Plot inline.",
    'say "I cannot find data for this."',
    'say "I don\'t know."',
)


def test_answering_rules_are_in_the_instructions_every_skill_and_the_template():
    from pathlib import Path

    from europa_mcp.countries import COUNTRIES

    assert "never from memory, estimates or internet search" in server.INSTRUCTIONS
    assert "I cannot find data for this." in server.INSTRUCTIONS and "I don't know." in server.INSTRUCTIONS
    template = Path(__file__).parents[1] / ".claude/skills/add-country/templates/skill/SKILL.md"
    texts = {c.CODE: (server.SKILLS_DIR / c.CODE / "SKILL.md").read_text("utf-8") for c in COUNTRIES}
    texts["overview"] = (server.SKILLS_DIR / "overview" / "SKILL.md").read_text("utf-8")
    texts["template"] = template.read_text("utf-8")
    for name, text in texts.items():
        assert "## Answering rules (official use)" in text, name
        assert [p for p in RULE_PHRASES if p not in text] == [], name
