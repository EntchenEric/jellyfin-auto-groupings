"""Tests for create_groupings two-mode behavior and edge cases."""

from jellyfin_auto_groupings.client import create_groupings


def test_create_groupings_mode1_groups_by_query_and_decade():
    items = [
        {
            "Name": "Iron Man",
            "Id": "1",
            "Genres": [],
            "Tags": [],
            "ProductionYear": 2008,
        },
        {
            "Name": "Iron Man 2",
            "Id": "2",
            "Genres": [],
            "Tags": [],
            "ProductionYear": 2010,
        },
        {
            "Name": "Star Wars",
            "Id": "3",
            "Genres": [],
            "Tags": [],
            "ProductionYear": 1977,
        },
    ]
    res = create_groupings(items)
    # MCU group (Iron Man movies match the "MCU" overview query only if
    # tagged/overview present; verify decade groups always appear)
    assert "2000s Movies" in res
    assert "2010s Movies" in res
    assert "1970s Movies" in res


def test_create_groupings_mode1_mcu_via_overview():
    items = [
        {
            "Name": "Iron Man",
            "Id": "1",
            "Tags": [],
            "Overview": "Part of the MCU.",
            "ProductionYear": 2008,
        },
        {
            "Name": "The Avengers",
            "Id": "2",
            "Tags": [],
            "Overview": "MCU crossover event.",
            "ProductionYear": 2012,
        },
    ]
    res = create_groupings(items)
    assert "Marvel Cinematic Universe" in res
    assert len(res["Marvel Cinematic Universe"]) == 2


def test_create_groupings_mode1_empty_items():
    res = create_groupings([])
    assert res == {}


def test_create_groupings_docstring_balanced():
    doc = create_groupings.__doc__
    assert doc is not None
    assert doc.count('"""') % 2 == 0
    assert "For case 2:" in doc


def test_create_groupings_mode2_min_group_size():
    class FakeClient:
        def __init__(self):
            self.created = []

        def create_collection(self, name, item_ids):
            self.created.append((name, item_ids))
            return {"Name": name, "Id": "col-1", "Ids": item_ids}

    client = FakeClient()
    items = [
        {"Name": "Harry Potter 1", "Id": "a"},
        {"Name": "Harry Potter 2", "Id": "b"},
        {"Name": "Standalone", "Id": "c"},
    ]
    created = create_groupings(client, items=items, min_group_size=2)
    # Only the 2-item group (first word "Harry") exceeds min_group_size;
    # mode 2 groups items by the leading name prefix (first word).
    assert len(created) == 1
    assert created[0]["Name"] == "Harry"


def test_create_groupings_mode2_empty_items_returns_list():
    class FakeClient:
        def create_collection(self, name, item_ids):  # pragma: no cover
            return {}

    assert create_groupings(FakeClient(), items=[]) == []
