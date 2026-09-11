from jellyfin_auto_groupings import group_items_by_pattern

def test_group_items_by_pattern_no_match():
    items = [{"Id": "1", "Name": "Test Movie"}]
    assert group_items_by_pattern(items, r"NonExistentPattern") == {}
