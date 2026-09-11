"""Jellyfin Auto-Groupings Script.

Automatically creates and manages Jellyfin collections (groupings) based on
configurable metadata rules (e.g., franchises, directors, genres, studios).
"""

import logging
import os
import sys
from typing import Any, Dict, List, Optional, Set

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


class JellyfinClient:
    """Client wrapper for Jellyfin REST API interaction."""

    def __init__(self, server_url: str, api_key: str, user_id: Optional[str] = None) -> None:
        self.server_url = server_url.rstrip("/")
        self.api_key = api_key
        self.user_id = user_id
        self.session = requests.Session()
        self.session.headers.update(
            {
                "X-Emby-Token": self.api_key,
                "Content-Type": "application/json",
            }
        )

    def get_items(self, include_item_types: str = "Movie") -> List[Dict[str, Any]]:
        """Fetch media items from Jellyfin server.

        Args:
            include_item_types: Comma-separated item types (e.g. 'Movie,Series').

        Returns:
            List of item dictionaries.
        """
        url = f"{self.server_url}/Items"
        params = {
            "IncludeItemTypes": include_item_types,
            "Recursive": "true",
            "Fields": "Genres,Studios,People,CollectionFolder",
        }
        if self.user_id:
            params["UserId"] = self.user_id

        try:
            resp = self.session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            return data.get("Items", [])
        except requests.RequestException as exc:
            logger.error("Failed to fetch items from Jellyfin: %s", exc)
            return []

    def create_collection(self, name: str, item_ids: List[str]) -> Optional[str]:
        """Create a collection with specified item IDs.

        Args:
            name: Collection name.
            item_ids: List of item IDs to include.

        Returns:
            Collection ID string if created, None otherwise.
        """
        if not item_ids:
            logger.warning("Cannot create collection '%s' with empty item_ids list.", name)
            return None

        url = f"{self.server_url}/Collections"
        params = {
            "Name": name,
            "Ids": ",".join(item_ids),
        }
        if self.user_id:
            params["IsLocked"] = "false"

        try:
            resp = self.session.post(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            collection_id = data.get("Id")
            logger.info("Created collection '%s' (ID: %s) with %d items.", name, collection_id, len(item_ids))
            return collection_id
        except requests.RequestException as exc:
            logger.error("Failed to create collection '%s': %s", name, exc)
            return None


def group_items_by_genre(items: List[Dict[str, Any]], min_count: int = 3) -> Dict[str, List[str]]:
    """Group item IDs by genre for genres meeting a minimum threshold count.

    Args:
        items: List of item dictionaries from Jellyfin API.
        min_count: Minimum number of items required to form a genre group.

    Returns:
        Mapping of genre name to list of item IDs.
    """
    genre_map: Dict[str, List[str]] = {}
    for item in items:
        item_id = item.get("Id")
        if not item_id:
            continue
        genres = item.get("Genres", [])
        for genre in genres:
            if not genre:
                continue
            genre_map.setdefault(genre, []).append(item_id)

    return {genre: ids for genre, ids in genre_map.items() if len(ids) >= min_count}


def group_items_by_studio(items: List[Dict[str, Any]], min_count: int = 3) -> Dict[str, List[str]]:
    """Group item IDs by studio for studios meeting a minimum threshold count.

    Args:
        items: List of item dictionaries from Jellyfin API.
        min_count: Minimum number of items required to form a studio group.

    Returns:
        Mapping of studio name to list of item IDs.
    """
    studio_map: Dict[str, List[str]] = {}
    for item in items:
        item_id = item.get("Id")
        if not item_id:
            continue
        studios = item.get("Studios", [])
        for studio in studios:
            studio_name = studio.get("Name") if isinstance(studio, dict) else studio
            if not studio_name:
                continue
            studio_map.setdefault(studio_name, []).append(item_id)

    return {studio: ids for studio, ids in studio_map.items() if len(ids) >= min_count}


def group_items_by_director(items: List[Dict[str, Any]], min_count: int = 2) -> Dict[str, List[str]]:
    """Group item IDs by Director for directors meeting a minimum threshold count.

    Args:
        items: List of item dictionaries from Jellyfin API.
        min_count: Minimum number of items required to form a director group.

    Returns:
        Mapping of director name to list of item IDs.
    """
    director_map: Dict[str, List[str]] = {}
    for item in items:
        item_id = item.get("Id")
        if not item_id:
            continue
        people = item.get("People", [])
        for person in people:
            if isinstance(person, dict) and person.get("Type") == "Director":
                name = person.get("Name")
                if name:
                    director_map.setdefault(name, []).append(item_id)

    return {director: ids for director, ids in director_map.items() if len(ids) >= min_count}


def main() -> None:
    """Main entry point for running Jellyfin Auto-Groupings script."""
    server_url = os.environ.get("JELLYFIN_URL", "http://localhost:8096")
    api_key = os.environ.get("JELLYFIN_API_KEY", "")
    user_id = os.environ.get("JELLYFIN_USER_ID")

    if not api_key:
        logger.error("JELLYFIN_API_KEY environment variable is required.")
        sys.exit(1)

    client = JellyfinClient(server_url=server_url, api_key=api_key, user_id=user_id)
    items = client.get_items()
    logger.info("Fetched %d items from Jellyfin.", len(items))

    genre_groups = group_items_by_genre(items)
    for genre, ids in genre_groups.items():
        client.create_collection(f"Genre: {genre}", ids)

    studio_groups = group_items_by_studio(items)
    for studio, ids in studio_groups.items():
        client.create_collection(f"Studio: {studio}", ids)

    director_groups = group_items_by_director(items)
    for director, ids in director_groups.items():
        client.create_collection(f"Director: {director}", ids)


if __name__ == "__main__":
    main()
