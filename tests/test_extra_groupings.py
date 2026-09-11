import pytest
from unittest.mock import MagicMock
from jellyfin_auto_groupings import JellyfinClient, group_items_by_pattern, sync_groupings


def test_group_items_by_pattern():
    items = [
        {"Id": "1", "Name": "Star Wars: Episode IV"},
        {"Id": "2", "Name": "Star Wars: Episode V"},
        {"Id": "3", "Name": "Avatar"},
    ]
    groups = group_items_by_pattern(items, r"^(Star Wars)")
    assert "Star Wars" in groups
    assert len(groups["Star Wars"]) == 2


def test_sync_groupings_dry_run():
    mock_client = MagicMock(spec=JellyfinClient)
    mock_client.get_all_items.return_value = []
    groups = {"Star Wars": [{"Id": "1"}, {"Id": "2"}]}
    summary = sync_groupings(mock_client, groups, dry_run=True)
    assert summary["Star Wars"] == ["1", "2"]
    mock_client.create_collection.assert_not_called()
