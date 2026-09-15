import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from jellyfin_auto_groupings import (
    JellyfinClient,
    group_items_by_pattern,
    sync_groupings,
)
from jellyfin_auto_groupings.client import (
    create_groupings,
    get_decade_groups,
    get_movies_by_query,
    get_year_groups,
    group_movies_by_genre,
    group_movies_by_tag,
    process_groupings,
)


def test_exports():
    assert JellyfinClient is not None
    assert callable(group_items_by_pattern)
    assert callable(sync_groupings)
    assert callable(create_groupings)
    assert callable(get_decade_groups)
    assert callable(get_year_groups)
    assert callable(get_movies_by_query)
    assert callable(group_movies_by_genre)
    assert callable(group_movies_by_tag)
    assert callable(process_groupings)
