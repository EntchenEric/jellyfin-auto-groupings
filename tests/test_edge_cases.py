from jellyfin_groupings import group_items_by_genre, group_items_by_studio, group_items_by_director

def test_group_items_empty():
    assert group_items_by_genre([]) == {}
    assert group_items_by_studio([]) == {}
    assert group_items_by_director([]) == {}

def test_group_items_missing_fields():
    items = [{"Id": "1"}, {"Id": "2", "Genres": None}]
    assert group_items_by_genre(items) == {}
