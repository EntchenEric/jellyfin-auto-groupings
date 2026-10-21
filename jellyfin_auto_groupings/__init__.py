import logging
import re
from typing import Any

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

    def process(self, library_id: str = "") -> list[dict[str, Any]]:
        return process_groupings(self.client, library_id)


def extract_collection_name(name: str | None) -> str | None:
    """Extract a collection name from a title (e.g. 'Toy Story 2' -> 'Toy Story Collection').

    Handles trailing numeric suffixes (" 2"), parenthesized years (" (1999)", "[2020]"),
    and colon separators ("Series: Episode 1" -> "Series").

    Args:
        name: The title to process.

    Returns:
        A collection name (e.g. "Toy Story Collection") when the title appears
        to be part of a series; ``None`` when no series prefix can be inferred.
    """
    if not name or not isinstance(name, str):
        return None

    original = name.strip()

    # Remove parenthesized / bracketed year or numeric suffixes, e.g. "(1999)", "[2020]".
    base = re.sub(r"[\[(]?\d+[\])]\s*$", "", original)
    # Remove trailing standalone numbers, e.g. " 2" or " 2020".
    base = re.sub(r"\s+\d+\s*$", "", base)
    # Take the portion before the first colon, e.g. "Series: Episode 1" -> "Series".
    base = base.split(":", 1)[0].strip()

    if base and base != original:
        return f"{base} Collection"
    return None


def validate_movie_item(item: dict[str, Any] | None) -> bool:
    """Validate that an item dictionary has required Name and Id attributes."""
    if not isinstance(item, dict):
        return False
    return bool(item.get("Name")) and bool(item.get("Id"))


def group_movies_by_collection(
    movies: list[dict[str, Any]], min_group_size: int = 2
) -> dict[str, list[dict[str, Any]]]:
    """Group movies into collections by inferring collection names.

    Args:
        movies: List of movie item dictionaries.
        min_group_size: Minimum number of movies required for a collection.

    Returns:
        A dictionary mapping collection names to lists of movies.
    """
    collections: dict[str, list[dict[str, Any]]] = {}
    for movie in movies:
        if not validate_movie_item(movie):
            continue
        coll_name = extract_collection_name(movie.get("Name"))
        if coll_name:
            collections.setdefault(coll_name, []).append(movie)
    return {k: v for k, v in collections.items() if len(v) >= min_group_size}


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
