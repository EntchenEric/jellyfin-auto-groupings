from jellyfin_auto_groupings.client import JellyfinClient, JellyfinAPIError
from jellyfin_auto_groupings.main import (
    main,
    process_groupings,
    create_groupings,
    get_decade_groups,
    get_year_groups,
    get_movies_by_query,
    group_movies_by_tag,
)

group_items_by_pattern = process_groupings
sync_groupings = process_groupings

class JellyfinGroupingManager:
    def __init__(self, client):
        self.client = client
    def process(self, library_id):
        return process_groupings(self.client, library_id)

__all__ = [
    "JellyfinClient",
    "JellyfinAPIError",
    "main",
    "group_items_by_pattern",
    "sync_groupings",
    "JellyfinGroupingManager",
    "group_movies_by_tag",
    "get_movies_by_query",
    "get_year_groups",
    "get_decade_groups",
    "create_groupings",
    "process_groupings",
]
