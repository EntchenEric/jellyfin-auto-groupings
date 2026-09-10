"""Auto-group Jellyfin media items by franchise, genre, director, decade, year, or custom tags."""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SPECIAL_COLLECTIONS: Dict[str, Dict[str, Any]] = {
    "Marvel Cinematic Universe": {"query": "MCU", "min_count": 3},
    "Star Wars Collection": {"query": "Star Wars", "min_count": 2},
    "Harry Potter Collection": {"query": "Harry Potter", "min_count": 2},
    "Lord of the Rings": {"query": "Lord of the Rings", "min_count": 2},
    "James Bond Collection": {"query": "James Bond", "min_count": 3},
}

CUSTOM_TAG_GROUPS: Dict[str, Dict[str, Any]] = {
    "Sci-Fi Classics": {"query": "Sci-Fi", "tags": ["sci-fi", "classic"], "min_count": 2},
    "Oscar Winners": {"query": "Oscar", "tags": ["oscar", "academy-award"], "min_count": 2},
    "90s Action": {"query": "Action", "tags": ["action", "90s"], "min_count": 2},
}


def get_movies_by_query(
    items: List[Dict[str, Any]], query: str, tags: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """Filter items matching a search query in their Name or Overview, and optionally matching tags."""
    matched: List[Dict[str, Any]] = []
    q_lower = query.lower()
    for item in items:
        name = item.get("Name", "").lower()
        overview = item.get("Overview", "").lower()
        item_tags = [t.lower() for t in item.get("Tags", [])]

        query_match = q_lower in name or q_lower in overview
        tag_match = True
        if tags:
            tag_match = any(t.lower() in item_tags for t in tags)

        if query_match and tag_match:
            matched.append(item)
    return matched


def get_decade_groups(items: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Group items into decade collections based on PremiereDate or ProductionYear."""
    decades: Dict[str, List[Dict[str, Any]]] = {}
    for item in items:
        year = item.get("ProductionYear")
        if not year and item.get("PremiereDate"):
            try:
                year = int(item["PremiereDate"][:4])
            except (ValueError, TypeError, IndexError):
                year = None
        if year and isinstance(year, int) and 1900 <= year <= 2100:
            decade_start = (year // 10) * 10
            decade_key = f"{decade_start}s Movies"
            decades.setdefault(decade_key, []).append(item)
    return decades


def get_year_groups(items: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Group items into exact release year collections."""
    years: Dict[str, List[Dict[str, Any]]] = {}
    for item in items:
        year = item.get("ProductionYear")
        if not year and item.get("PremiereDate"):
            try:
                year = int(item["PremiereDate"][:4])
            except (ValueError, TypeError, IndexError):
                year = None
        if year and isinstance(year, int) and 1900 <= year <= 2100:
            year_key = f"Best of {year}"
            years.setdefault(year_key, []).append(item)
    return years


def create_groupings(items: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Generate all collection groupings for a list of Jellyfin items."""
    groups: Dict[str, List[Dict[str, Any]]] = {}

    # Add standard collections
    all_collections = dict(SPECIAL_COLLECTIONS)
    all_collections.update(CUSTOM_TAG_GROUPS)
    for group_name, config in all_collections.items():
        query = config["query"]
        tags = config.get("tags")
        min_count = config.get("min_count", 2)
        movies = get_movies_by_query(items, query, tags)
        if len(movies) >= min_count:
            groups[group_name] = movies

    # Dynamic decade collections
    decades = get_decade_groups(items)
    for decade_name, movies in decades.items():
        if len(movies) >= 2:
            groups[decade_name] = movies

    # Dynamic release year collections
    years = get_year_groups(items)
    for year_name, movies in years.items():
        if len(movies) >= 3:
            groups[year_name] = movies

    return groups
