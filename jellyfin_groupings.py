import contextlib
import logging
import os
import sys
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


class JellyfinAPIError(Exception):
    """Custom exception for Jellyfin API errors."""
    pass


class JellyfinClient:
    def __init__(self, server_url: str, api_key: str, user_id: Optional[str] = None):
        """Initialize Jellyfin client.

        Args:
            server_url: Jellyfin server URL (e.g., 'http://localhost:8096')
            api_key: Jellyfin API key for authentication
            user_id: Optional user ID for user-specific operations
        """
        self.server_url = server_url.rstrip("/")
        self.api_key = api_key
        self.user_id = user_id
        self.session = requests.Session()
        self.session.headers.update({
            "X-Emby-Token": self.api_key,
            "Content-Type": "application/json",
        })

    def get_users(self) -> List[Dict[str, Any]]:
        """Get all users from Jellyfin server.

        Returns:
            List of user dictionaries, empty list on error
        """
        url = f"{self.server_url}/Users"
        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.error(f"Failed to get users: {e}")
            return []

    def get_first_admin_user_id(self) -> Optional[str]:
        """Get the first administrator user ID.

        Returns:
            Admin user ID if found, None otherwise
        """
        users = self.get_users()
        if not users:
            return None
        for u in users:
            if u.get("Policy", {}).get("IsAdministrator"):
                return u.get("Id")
        return users[0].get("Id")

    def get_collections(self) -> List[Dict[str, Any]]:
        """Get all collections (BoxSets) from Jellyfin.

        Returns:
            List of collection dictionaries, empty list on error
        """
        url = f"{self.server_url}/Items?IncludeItemTypes=BoxSet&Recursive=true"
        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            return data.get("Items", [])
        except requests.RequestException as e:
            logger.error(f"Failed to get collections: {e}")
            return []

    def get_collection_items(self, collection_id: str) -> List[Dict[str, Any]]:
        """Get all items in a specific collection.

        Args:
            collection_id: ID of the collection to fetch items from

        Returns:
            List of item dictionaries in the collection, empty list on error
        """
        url = f"{self.server_url}/Items?ParentId={collection_id}&Recursive=true"
        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            return data.get("Items", [])
        except requests.RequestException as e:
            logger.error(f"Failed to get collection items for {collection_id}: {e}")
            return []

    def get_movies(self) -> List[Dict[str, Any]]:
        """Get all movies from Jellyfin.

        Returns:
            List of movie dictionaries, empty list on error
        """
        uid = self.user_id or self.get_first_admin_user_id()
        if not uid:
            logger.warning("No user ID available for getting movies")
            return []
        url = f"{self.server_url}/Users/{uid}/Items?IncludeItemTypes=Movie&Recursive=true"
        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            return data.get("Items", [])
        except requests.RequestException as e:
            logger.error(f"Failed to get movies: {e}")
            return []

    def get_items(self, library_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get items from a specific library or all movies if library_id not provided.

        Args:
            library_id: Optional library ID to filter items

        Returns:
            List of item dictionaries
        """
        if library_id:
            url = f"{self.server_url}/Items?ParentId={library_id}&Recursive=true"
            try:
                resp = self.session.get(url, timeout=30)
                resp.raise_for_status()
                data = resp.json()
                return data.get("Items", [])
            except requests.RequestException as e:
                logger.error(f"Failed to get items from library {library_id}: {e}")
                return []
        return self.get_movies()

    def create_collection(self, name: str, item_ids: List[str]) -> Optional[Dict[str, Any]]:
        """Create a new collection with specified items.

        Args:
            name: Name for the new collection
            item_ids: List of item IDs to include in the collection

        Returns:
            Created collection dictionary on success, None on failure
        """
        if not item_ids:
            logger.warning("Cannot create collection with empty item list")
            return None
        ids_str = ",".join(item_ids)
        url = f"{self.server_url}/Collections?Name={name}&Ids={ids_str}"
        try:
            resp = self.session.post(url, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.error(f"Failed to create collection '{name}': {e}")
            return None

    def update_item_sort_name(self, item_id: str, sort_name: str) -> bool:
        """Update the sort name of an item.

        Args:
            item_id: ID of the item to update
            sort_name: New sort name to set

        Returns:
            True if successful, False otherwise
        """
        url = f"{self.server_url}/Items/{item_id}"
        try:
            resp = self.session.post(url, json={"ForcedSortName": sort_name}, timeout=30)
            resp.raise_for_status()
            logger.debug(f"Updated sort name for item {item_id} to '{sort_name}'")
            return True
        except requests.RequestException as e:
            logger.error(f"Failed to update sort name for item {item_id}: {e}")
            return False


def group_movies_by_tag(movies: List[Dict[str, Any]], tag_prefix: str = "Group:") -> Dict[str, List[str]]:
    """Group movies by tags with specified prefix.

    Args:
        movies: List of movie dictionaries from Jellyfin
        tag_prefix: Prefix that identifies grouping tags (default: 'Group:')

    Returns:
        Dictionary mapping group names to lists of item IDs
    """
    groups: Dict[str, List[str]] = {}
    for movie in movies:
        item_id = movie.get("Id")
        if not item_id:
            continue
        for tag in movie.get("Tags", []):
            if tag.startswith(tag_prefix):
                group_name = tag[len(tag_prefix):].strip()
                if group_name:
                    groups.setdefault(group_name, []).append(item_id)
    return groups


def group_movies_by_genre(movies: List[Dict[str, Any]], min_count: int = 1) -> Dict[str, List[str]]:
    """Group movies by genre.

    Args:
        movies: List of movie dictionaries from Jellyfin
        min_count: Minimum number of movies required to create a genre group

    Returns:
        Dictionary mapping genre names to lists of item IDs
    """
    groups: Dict[str, List[str]] = {}
    for movie in movies:
        item_id = movie.get("Id")
        if not item_id:
            continue
        for genre in movie.get("Genres", []):
            groups.setdefault(genre, []).append(item_id)
    return {g: ids for g, ids in groups.items() if len(ids) >= min_count}


def process_groupings(client: JellyfinClient, dry_run: bool = True) -> List[tuple]:
    """Process groupings for all collections, updating sort names sequentially.

    Args:
        client: Initialized JellyfinClient instance
        dry_run: If True, only report changes without applying them

    Returns:
        List of tuples (item_id, item_name, new_sort_name) for items that need updates
    """
    collections = client.get_collections()
    changes = []

    for col in collections:
        col_name = col.get("Name", "Collection")
        collection_id = col.get("Id", "")
        if not collection_id:
            continue

        items = client.get_collection_items(collection_id)
        if not items:
            continue

        # Sort items by PremiereDate (oldest first), fallback to Name if date missing
        def get_sort_key(item: Dict[str, Any]) -> str:
            premiere_date = item.get("PremiereDate", "")
            if premiere_date:
                return premiere_date
            return item.get("Name", "").lower()

        sorted_items = sorted(items, key=get_sort_key)

        for idx, item in enumerate(sorted_items, start=1):
            expected_sort_name = f"{col_name} {idx:02d}"
            current_sort = item.get("ForcedSortName", "")
            item_id = item.get("Id")

            if item_id and current_sort != expected_sort_name:
                changes.append((item_id, item.get("Name", "Unknown"), expected_sort_name))
                if not dry_run:
                    success = client.update_item_sort_name(item_id, expected_sort_name)
                    if not success:
                        logger.warning(f"Failed to update sort name for item {item_id}")

    return changes


def main() -> None:
    """Main entry point for the jellyfin-groupings module."""
    api_key = os.environ.get("JELLYFIN_API_KEY")
    if not api_key:
        print("Error: JELLYFIN_API_KEY environment variable is required.")
        sys.exit(1)
    url = os.environ.get("JELLYFIN_URL", "http://localhost:8096")
    client = JellyfinClient(url, api_key)
    movies = client.get_movies()
    groups = group_movies_by_tag(movies)
    for group_name, item_ids in groups.items():
        result = client.create_collection(group_name, item_ids)
        if result is None:
            logger.warning(f"Failed to create collection '{group_name}'")


if __name__ == "__main__":
    main()
