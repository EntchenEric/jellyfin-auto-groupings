from jellyfin_auto_groupings.client import JellyfinClient, JellyfinAPIError
from .groupings import (
    create_groupings,
    group_by_tag,
    group_by_genre,
    group_by_studio,
    group_by_decade,
    parse_grouping_rules,
    process_groupings,
)

__all__ = [
    "create_groupings",
    "group_by_tag",
    "group_by_genre",
    "group_by_studio",
    "group_by_decade",
    "parse_grouping_rules",
    "process_groupings",
    "JellyfinClient",
    "JellyfinAPIError",
]
