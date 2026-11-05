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
    out = await call("country_guide", country="nl")
    assert (
        out.startswith("No guide for that country yet. Available: eu")
        and 'dataeu_search(query, country="<iso2>")' in out
    )
    async with Client(server.mcp) as c:
        uris = {str(r.uri) for r in await c.list_resources()}
        assert {"skill://eu/SKILL.md", "skill://de/SKILL.md"} <= uris
        assert not any("skill://nl/" in u for u in uris)
        text = (await c.read_resource("skill://de/SKILL.md"))[0].text
    assert "govdata_search" in text


def test_every_country_has_a_skill_and_hints():
    from europa_mcp.countries import COUNTRIES

    assert [c.CODE for c in COUNTRIES] == ["eu", "de"]
    for c in COUNTRIES:
        assert (server.SKILLS_DIR / c.CODE / "SKILL.md").is_file(), c.CODE
        assert set(c.HINTS["sources"]) <= set(server.SOURCES)
