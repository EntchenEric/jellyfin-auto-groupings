"""
Unit tests for jellyfin_auto_groupings.grouper module.
"""

from jellyfin_auto_groupings.grouper import CollectionGrouper


def test_collection_grouper_init():
    grouper = CollectionGrouper(pattern=r"^(.*) Collection")
    assert grouper.pattern == r"^(.*) Collection"


def test_collection_grouper_group():
    grouper = CollectionGrouper(pattern=r"^(.*) - Part")
    items = [
        {"Name": "Movie A - Part 1"},
        {"Name": "Movie A - Part 2"},
        {"Name": "Movie B - Part 1"},
        {"Name": "Movie C"},
    ]
    grouped = grouper.group(items)
    assert "Movie A" in grouped
    assert len(grouped["Movie A"]) == 2
    assert "Movie B" in grouped
    assert len(grouped["Movie B"]) == 1
    assert "Movie C" not in grouped
