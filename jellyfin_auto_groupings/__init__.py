import logging
import re
from typing import Any, Dict, List, Optional
import requests
from jellyfin_auto_groupings.client import (
    JellyfinAPIError,
    JellyfinClient,
    create_groupings,
    get_decade_groups,
    get_movies_by_query,
    get_year_groups,
    group_items_by_pattern,
    group_movies_by_genre,
    group_movies_by_tag,
    process_groupings,
    sync_groupings,
)

logger = logging.getLogger(__name__)


class JellyfinGroupingManager:
    """Manager for orchestrating groupings across Jellyfin libraries."""
    def __init__(self, client: JellyfinClient):
        self.client = client

    def process(self, library_id: str = "") -> List[Dict[str, Any]]:
        return process_groupings(self.client, library_id)


def extract_collection_name(name: Optional[str]) -> Optional[str]:
    """Extract a collection name from a title (e.g. 'Toy Story 2' -> 'Toy Story Collection')."""
    if not name or not isinstance(name, str):
        return None
    match = re.match(r"^(.*?)(?:\s+\d+|\s*:\s*.*)$", name.strip())
    if match:
        base = match.group(1).strip()
        if base and base != name.strip():
            return f"{base} Collection"
    return None


def validate_movie_item(item: Optional[Dict[str, Any]]) -> bool:
    """Validate that an item dictionary has required Name and Id attributes."""
    if not isinstance(item, dict):
        return False
    return bool(item.get("Name")) and bool(item.get("Id"))


def group_movies_by_collection(movies: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Group movies into collections by inferring collection names."""
    collections: Dict[str, List[Dict[str, Any]]] = {}
    for movie in movies:
        if not validate_movie_item(movie):
            continue
        coll_name = extract_collection_name(movie.get("Name"))
        if coll_name:
            collections.setdefault(coll_name, []).append(movie)
    return {k: v for k, v in collections.items() if len(v) >= 2}


__all__ = [
    "JellyfinAPIError",
    "JellyfinClient",
    "JellyfinGroupingManager",
    "create_groupings",
    "extract_collection_name",
    "get_decade_groups",
    "get_movies_by_query",
    "get_year_groups",
    "group_items_by_pattern",
    "group_movies_by_collection",
    "group_movies_by_genre",
    "group_movies_by_tag",
    "process_groupings",
    "sync_groupings",
    "validate_movie_item",
]
