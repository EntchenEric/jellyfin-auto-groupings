"""Jellyfin Auto Groupings tool.

Automatically groups movies in Jellyfin into collections based on custom criteria,
TMDB collections, franchises, or custom tags/metadata.
"""

import os
import sys
import logging
from typing import Dict, List, Any, Optional, Set
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


class JellyfinClient:
    """Client interface for interacting with the Jellyfin REST API."""

    def __init__(self, server_url: str, api_key: str, user_id: Optional[str] = None) -> None:
        self.server_url = server_url.rstrip('/')
        self.api_key = api_key
        self.user_id = user_id
        self.session = requests.Session()
        self.session.headers.update({
            "X-Emby-Token": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json"
        })

    def get_users(self) -> List[Dict[str, Any]]:
        """Fetch all users from Jellyfin."""
        url = f"{self.server_url}/Users"
        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.error(f"Failed to fetch users: {e}")
            return []

    def get_movies(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch all movie items for a given user or default user."""
        uid = user_id or self.user_id
        if not uid:
            users = self.get_users()
            if users:
                uid = users[0].get("Id")
            else:
                logger.error("No User ID available to query movies.")
                return []

        url = f"{self.server_url}/Users/{uid}/Items"
        params = {
            "IncludeItemTypes": "Movie",
            "Recursive": "true",
            "Fields": "Genres,Tags,ProviderIds,CollectionFolder"
        }
        try:
            resp = self.session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json().get("Items", [])
        except requests.RequestException as e:
            logger.error(f"Failed to fetch movies: {e}")
            return []

    def create_collection(self, name: str, item_ids: List[str]) -> Optional[Dict[str, Any]]:
        """Create a collection with given name and list of item IDs."""
        if not item_ids:
            logger.warning(f"Cannot create collection '{name}' with no items.")
            return None

        url = f"{self.server_url}/Collections"
        params = {
            "Name": name,
            "Ids": ",".join(item_ids)
        }
        try:
            resp = self.session.post(url, params=params, timeout=30)
            resp.raise_for_status()
            logger.info(f"Created collection '{name}' with {len(item_ids)} items.")
            return resp.json()
        except requests.RequestException as e:
            logger.error(f"Failed to create collection '{name}': {e}")
            return None


def group_movies_by_tag(movies: List[Dict[str, Any]], tag_prefix: str = "Group:") -> Dict[str, List[str]]:
    """Group movies based on tags starting with a specific prefix.

    Example tag: 'Group:Marvel Cinematic Universe'
    """
    groups: Dict[str, List[str]] = {}
    for movie in movies:
        item_id = movie.get("Id")
        tags = movie.get("Tags", [])
        if not item_id:
            continue
        for tag in tags:
            if tag.startswith(tag_prefix):
                group_name = tag[len(tag_prefix):].strip()
                if group_name:
                    groups.setdefault(group_name, []).append(item_id)
    return groups


def group_movies_by_genre(movies: List[Dict[str, Any]], min_count: int = 2) -> Dict[str, List[str]]:
    """Group movies by genres if a genre has at least `min_count` movies."""
    genre_map: Dict[str, List[str]] = {}
    for movie in movies:
        item_id = movie.get("Id")
        genres = movie.get("Genres", [])
        if not item_id:
            continue
        for genre in genres:
            genre_map.setdefault(genre, []).append(item_id)
    return {g: ids for g, ids in genre_map.items() if len(ids) >= min_count}


def main() -> None:
    """Main entry point for jellyfin-auto-groupings."""
    server_url = os.environ.get("JELLYFIN_URL", "http://localhost:8096")
    api_key = os.environ.get("JELLYFIN_API_KEY", "")

    if not api_key:
        logger.error("JELLYFIN_API_KEY environment variable is required.")
        sys.exit(1)

    client = JellyfinClient(server_url, api_key)
    movies = client.get_movies()
    logger.info(f"Found {len(movies)} movies.")

    grouped = group_movies_by_tag(movies)
    for group_name, item_ids in grouped.items():
        client.create_collection(group_name, item_ids)


if __name__ == "__main__":
    main()
