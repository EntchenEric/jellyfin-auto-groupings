import logging
import math
import os
import re
import sys
from typing import Any

import requests

from utils.helpers import items_from_body, string_list

logger = logging.getLogger(__name__)

#: A leading ``YYYY-MM-DD`` date, optionally followed by a time. Used to decide
#: whether a ``PremiereDate`` value is a real date before it is allowed to take
#: priority over the title in a sort key.
_LEADING_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")


class JellyfinAPIError(Exception):
    """Custom exception for Jellyfin API errors."""


class JellyfinClient:
    def __init__(self, server_url: str, api_key: str, user_id: str | None = None):
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
        self.session.headers.update(
            {
                "X-Emby-Token": self.api_key,
                "Content-Type": "application/json",
            }
        )

    def get_users(self) -> list[dict[str, Any]]:
        """Get all users from Jellyfin server.

        Returns:
            List of user dictionaries, empty list on error
        """
        url = f"{self.server_url}/Users"
        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
        except requests.RequestException:
            logger.exception("Failed to get users")
            return []
        # ``/Users`` answers with a bare array; ``null`` or an object here
        # would otherwise be returned despite the ``list`` annotation.
        body = resp.json()
        if not isinstance(body, list):
            return []
        return [entry for entry in body if isinstance(entry, dict)]

    def get_first_admin_user_id(self) -> str | None:
        """Get the first administrator user ID.

        Returns:
            Admin user ID if found, None otherwise
        """
        users = self.get_users()
        if not users:
            return None
        for u in users:
            # ``Policy`` is ``null`` for a user Jellyfin has not fully
            # configured; the default in ``.get(key, {})`` does not apply to a
            # present-but-null value, so the chained ``.get`` raised
            # AttributeError instead of falling through to the next user.
            policy = u.get("Policy")
            if isinstance(policy, dict) and policy.get("IsAdministrator"):
                admin_id = u.get("Id")
                if admin_id:
                    return admin_id
        return users[0].get("Id")

    def get_collections(self) -> list[dict[str, Any]]:
        """Get all collections (BoxSets) from Jellyfin.

        Returns:
            List of collection dictionaries, empty list on error
        """
        url = f"{self.server_url}/Items"
        params = {"IncludeItemTypes": "BoxSet", "Recursive": "true"}
        try:
            resp = self.session.get(url, params=params, timeout=30)
            resp.raise_for_status()
        except requests.RequestException:
            logger.exception("Failed to get collections")
            return []
        data = resp.json()
        return items_from_body(data)

    def get_collection_items(self, collection_id: str) -> list[dict[str, Any]]:
        """Get all items in a specific collection.

        Args:
            collection_id: ID of the collection to fetch items from

        Returns:
            List of item dictionaries in the collection, empty list on error
        """
        url = f"{self.server_url}/Items"
        params = {"ParentId": collection_id, "Recursive": "true"}
        try:
            resp = self.session.get(url, params=params, timeout=30)
            resp.raise_for_status()
        except requests.RequestException:
            logger.exception(f"Failed to get collection items for {collection_id}")
            return []
        data = resp.json()
        return items_from_body(data)

    def get_movies(self) -> list[dict[str, Any]]:
        """Get all movies from Jellyfin.

        Returns:
            List of movie dictionaries, empty list on error
        """
        uid = self.user_id or self.get_first_admin_user_id()
        if not uid:
            logger.warning("No user ID available for getting movies")
            return []
        url = f"{self.server_url}/Users/{uid}/Items"
        params = {"IncludeItemTypes": "Movie", "Recursive": "true"}
        try:
            resp = self.session.get(url, params=params, timeout=30)
            resp.raise_for_status()
        except requests.RequestException:
            logger.exception("Failed to get movies")
            return []
        data = resp.json()
        return items_from_body(data)

    def get_items(self, library_id: str | None = None) -> list[dict[str, Any]]:
        """Get items from a specific library or all movies if library_id not provided.

        Args:
            library_id: Optional library ID to filter items

        Returns:
            List of item dictionaries
        """
        if library_id:
            url = f"{self.server_url}/Items"
            params = {"ParentId": library_id, "Recursive": "true"}
            try:
                resp = self.session.get(url, params=params, timeout=30)
                resp.raise_for_status()
                data = resp.json()
                return items_from_body(data)
            except requests.RequestException:
                logger.exception(f"Failed to get items from library {library_id}:")
                return []
        return self.get_movies()

    def create_collection(
        self, name: str, item_ids: list[str]
    ) -> dict[str, Any] | None:
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
        url = f"{self.server_url}/Collections"
        # ``name`` is user-supplied (a group name or a tag), so it has to go
        # through ``params`` rather than an f-string. Pasted into the query
        # directly, an ``&`` split the name and dropped everything after it,
        # a ``+`` became a space, and a ``#`` truncated the URL before
        # ``Ids`` was ever sent — so "Best of 2024 #1" created an empty
        # collection instead of failing loudly.
        params = {"Name": name, "Ids": ids_str}
        try:
            resp = self.session.post(url, params=params, timeout=30)
            resp.raise_for_status()
        except requests.RequestException:
            logger.exception(f"Failed to create collection '{name}'")
            return None
        return resp.json()

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
            resp = self.session.post(
                url, json={"ForcedSortName": sort_name}, timeout=30
            )
            resp.raise_for_status()
        except requests.RequestException:
            logger.exception(f"Failed to update sort name for item {item_id}")
            return False
        logger.debug(f"Updated sort name for item {item_id} to '{sort_name}'")
        return True


def group_movies_by_tag(
    movies: list[dict[str, Any]], tag_prefix: str = "Group:"
) -> dict[str, list[str]]:
    """Group movies by tags with specified prefix.

    Args:
        movies: List of movie dictionaries from Jellyfin
        tag_prefix: Prefix that identifies grouping tags (default: 'Group:')

    Returns:
        Dictionary mapping group names to lists of item IDs
    """
    groups: dict[str, list[str]] = {}
    for movie in movies:
        item_id = movie.get("Id")
        if not item_id:
            continue
        # Jellyfin serialises an empty tag list as ``null``, and a tag entry
        # can be a non-string; both used to raise from ``startswith`` and
        # abort the grouping pass for the whole library. A bare string is one
        # tag, not one tag per character.
        for tag in string_list(movie.get("Tags")):
            if tag.startswith(tag_prefix):
                group_name = tag[len(tag_prefix) :].strip()
                if group_name:
                    groups.setdefault(group_name, []).append(item_id)
    return groups


def group_movies_by_genre(
    movies: list[dict[str, Any]], min_count: int = 1
) -> dict[str, list[str]]:
    """Group movies by genre.

    Args:
        movies: List of movie dictionaries from Jellyfin
        min_count: Minimum number of movies required to create a genre group

    Returns:
        Dictionary mapping genre names to lists of item IDs
    """
    groups: dict[str, list[str]] = {}
    for movie in movies:
        item_id = movie.get("Id")
        if not item_id:
            continue
        # ``null`` genres and non-string entries would create unusable group
        # keys, so they are skipped. A bare string is one genre, not one
        # genre per character.
        for genre in string_list(movie.get("Genres")):
            if genre:
                groups.setdefault(genre, []).append(item_id)
    return {g: ids for g, ids in groups.items() if len(ids) >= min_count}


def process_groupings(client: JellyfinClient, dry_run: bool = True) -> list[tuple]:
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
        col_name = col.get("Name") or "Collection"
        collection_id = col.get("Id") or ""
        if not collection_id:
            continue

        items = client.get_collection_items(collection_id)
        if not items:
            continue

        # Sort items by PremiereDate (oldest first), fallback to Name if date
        # missing. The key must be a single comparable type: Jellyfin sends
        # PremiereDate as a string normally but as a number in some payloads,
        # and mixing the two raised ``TypeError: '<' not supported between
        # instances of 'str' and 'int'`` and aborted the whole pass. A missing
        # or non-string Name likewise raised ``AttributeError`` from
        # ``.lower()``.
        #
        # A string only ranks as a date when it actually starts with one. A
        # placeholder such as ``"not-a-date"`` used to win the date rank and
        # sort ahead of a genuinely dated item, shifting every later sort name.
        def get_sort_key(item: dict[str, Any]) -> tuple[int, str]:
            premiere_date = item.get("PremiereDate")
            if isinstance(premiere_date, str):
                if _LEADING_DATE.match(premiere_date.strip()):
                    return (0, premiere_date.strip())
            elif (
                isinstance(premiere_date, (int, float))
                and not isinstance(premiere_date, bool)
                and math.isfinite(premiere_date)
            ):
                # A numeric year sorts as that year's first day, so it still
                # interleaves with the ISO strings instead of landing after
                # every one of them. Values outside a plausible year range are
                # not dates either.
                year = int(premiere_date)
                if 1 <= year <= 9999:
                    return (0, f"{year:04d}-01-01")
            name = item.get("Name")
            return (1, name.lower() if isinstance(name, str) else "")

        sorted_items = sorted(items, key=get_sort_key)

        for idx, item in enumerate(sorted_items, start=1):
            expected_sort_name = f"{col_name} {idx:02d}"
            current_sort = item.get("ForcedSortName", "")
            item_id = item.get("Id")

            if item_id and current_sort != expected_sort_name:
                changes.append(
                    (item_id, item.get("Name") or "Unknown", expected_sort_name)
                )
                if not dry_run:
                    success = client.update_item_sort_name(item_id, expected_sort_name)
                    if not success:
                        logger.warning(f"Failed to update sort name for item {item_id}")

    return changes


def main() -> None:
    """Main entry point for the jellyfin-groupings module."""
    api_key = os.environ.get("JELLYFIN_API_KEY")
    if not api_key:
        print(
            "Error: JELLYFIN_API_KEY environment variable is required.", file=sys.stderr
        )
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
