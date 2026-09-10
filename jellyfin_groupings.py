"""Jellyfin Auto-Groupings Script.

Automates grouping library items into collections in Jellyfin using the REST API.
"""

import logging
import re
from typing import Any, Dict, List, Optional
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def sanitize_name(name: str) -> str:
    """Sanitize movie or series name for matching and grouping comparisons.

    Args:
        name: Raw name string.

    Returns:
        Sanitized lower-case alphanumeric string with single spaces.
    """
    if not name:
        return ""
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", "", name)
    return " ".join(cleaned.lower().split())


def get_library_items(server_url: str, api_key: str, user_id: str) -> List[Dict[str, Any]]:
    """Fetch all items from Jellyfin library for a specific user.

    Args:
        server_url: Jellyfin server base URL.
        api_key: Jellyfin API key.
        user_id: Jellyfin user ID.

    Returns:
        List of item dictionaries returned by Jellyfin API.
    """
    endpoint = f"{server_url.rstrip('/')}/Users/{user_id}/Items"
    headers = {"X-MediaBrowser-Token": api_key}
    params = {
        "Recursive": "true",
        "IncludeItemTypes": "Movie,Series",
        "Fields": "SeriesName,CollectionFolder"
    }

    try:
        response = requests.get(endpoint, headers=headers, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        items = data.get("Items", [])
        logger.info("Retrieved %d items from Jellyfin.", len(items))
        return items
    except requests.RequestException as err:
        logger.error("Failed to fetch library items: %s", err)
        return []


def group_items_by_collection(items: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Group items based on SeriesName or collection metadata.

    Args:
        items: List of Jellyfin item dicts.

    Returns:
        Dictionary mapping collection names to lists of item dicts.
    """
    collections: Dict[str, List[Dict[str, Any]]] = {}

    for item in items:
        series_name = item.get("SeriesName")
        if series_name:
            collections.setdefault(series_name, []).append(item)

    logger.info("Grouped items into %d collections.", len(collections))
    return collections


def create_collection(
    server_url: str,
    api_key: str,
    name: str,
    item_ids: List[str]
) -> Optional[str]:
    """Create a collection in Jellyfin containing the specified items.

    Args:
        server_url: Jellyfin server base URL.
        api_key: Jellyfin API key.
        name: Name for the new collection.
        item_ids: List of Jellyfin item IDs to include.

    Returns:
        Collection ID if creation succeeded, None otherwise.
    """
    if not item_ids:
        logger.warning("No item IDs provided for collection '%s'. Skipping creation.", name)
        return None

    endpoint = f"{server_url.rstrip('/')}/Collections"
    headers = {"X-MediaBrowser-Token": api_key}
    params = {
        "Name": name,
        "Ids": ",".join(item_ids)
    }

    try:
        response = requests.post(endpoint, headers=headers, params=params, timeout=15)
        response.raise_for_status()
        result = response.json()
        collection_id = result.get("Id")
        logger.info("Successfully created collection '%s' (ID: %s).", name, collection_id)
        return collection_id
    except requests.RequestException as err:
        logger.error("Failed to create collection '%s': %s", name, err)
        return None


if __name__ == "__main__":
    print("Jellyfin Auto-Groupings Module. Import and call helper functions or configure credentials.")
