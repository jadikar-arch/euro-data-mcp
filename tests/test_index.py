from europa_mcp.countries.nl.index import parse_description, query_groups


def test_parse_description_splits_period_and_boilerplate():
    body, period = parse_description("Over bevolking.\n\nGegevens beschikbaar vanaf: 1995\nStatus: x")
    assert body == "Over bevolking."
    assert period == "1995"


def test_query_groups_expands_english_and_drops_stopwords():
    assert query_groups("What is the population of Amsterdam") == [
        ["population", "bevolking", "inwoners"],
        ["amsterdam"],
    ]
    assert query_groups("house")[0][:2] == ["house", "woningen"]  # singular → plural synonym


async def test_initial_sync_indexes_catalog_and_details(index, fake_cbs):
    assert index.count() == 3
    row = index.get("37230NED")  # case-insensitive
    assert row["id"] == "37230ned"
    assert row["period"] == "januari 2002"
    assert "Overledenen" in row["terms"]  # measure titles indexed for active tables
    assert index.get("00372")["terms"] == ""  # discontinued: no detail fetch


async def test_search_ranks_title_matches_and_hides_discontinued(index):
    rows, total = index.search("bevolking regio")
    assert [r["id"] for r in rows] == ["37230ned", "83625NED"]  # both terms in title first
    assert total == 2
    rows, _ = index.search("bevolking", include_discontinued=True)
    assert {r["id"] for r in rows} == {"37230ned", "00372"}
    rows, _ = index.search("house prices")
    assert rows[0]["id"] == "83625NED"
    rows, _ = index.search("overledenen")  # only in measure titles
    assert rows[0]["id"] == "37230ned"


async def test_incremental_sync_fetches_only_changes(index, fake_cbs):
    fake_cbs.catalog[1] = {**fake_cbs.catalog[1], "Version": "v2", "Title": "Koopwoningen; nieuw"}
    del fake_cbs.catalog[2]
    fake_cbs.calls.clear()
    invalidated: list[str] = []

    stats = await index.sync(on_change=invalidated.extend)

    assert stats["changed"] == 1 and stats["removed"] == 1 and stats["total"] == 2
    assert index.get("83625NED")["title"] == "Koopwoningen; nieuw"
    assert index.get("00372") is None
    assert sorted(invalidated) == ["00372", "83625NED"]
    # Details refetched only for the changed dataset.
    assert not any(c.startswith("/CBS/37230ned") for c in fake_cbs.calls)
    assert "/CBS/83625NED/MeasureCodes" in fake_cbs.calls


async def test_sync_refuses_mass_deletion(index, fake_cbs, monkeypatch):
    big = [{**fake_cbs.catalog[0], "Identifier": f"T{i}", "Version": "v1"} for i in range(60)]
    fake_cbs.catalog.extend(big)
    await index.sync(details=False)
    del fake_cbs.catalog[3:]  # remote suddenly lost 60 of 63 tables
    stats = await index.sync(details=False)
    assert stats["removed"] == 0 and index.count() == 63
