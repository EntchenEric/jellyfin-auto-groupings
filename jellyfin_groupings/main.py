import os
import sys
from typing import Any

import requests

from utils.helpers import items_from_body

#: Default per-request timeout in seconds. Without an explicit timeout
#: ``requests`` waits forever, so an unresponsive Jellyfin server hung the
#: CLI instead of failing with an error the caller could act on.
_DEFAULT_TIMEOUT = 30


class JellyfinGroupings:
    """Client for managing Jellyfin collection groupings automatically."""

    def __init__(
        self,
        url: str,
        api_key: str,
        timeout: int = _DEFAULT_TIMEOUT,
    ) -> None:
        """Initialise the client.

        Args:
            url: Jellyfin server base URL; a trailing slash is trimmed so
                endpoint paths do not double up.
            api_key: Jellyfin API key sent as the ``X-Emby-Token`` header.
            timeout: Per-request timeout in seconds. ``requests`` blocks
                indefinitely when this is omitted, so a value is always sent.

        """
        self.url = url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.headers = {
            "X-Emby-Token": self.api_key,
            "Content-Type": "application/json",
        }

    def get_collections(self) -> list[dict[str, Any]]:
        """Retrieve all existing collections (BoxSets) from Jellyfin."""
        endpoint = f"{self.url}/Collections"
        params: dict[str, str] = {"IncludeItemTypes": "BoxSet", "Recursive": "true"}
        response = requests.get(
            endpoint, headers=self.headers, params=params, timeout=self.timeout
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return items_from_body(data)

    def get_movies(self) -> list[dict[str, Any]]:
        """Retrieve all movies with ProviderIds from Jellyfin."""
        endpoint = f"{self.url}/Items"
        params: dict[str, str] = {
            "IncludeItemTypes": "Movie",
            "Recursive": "true",
            "Fields": "ProviderIds",
        }
        response = requests.get(
            endpoint, headers=self.headers, params=params, timeout=self.timeout
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return items_from_body(data)

    def create_collection(self, name: str, item_ids: list[str]) -> dict[str, Any]:
        """Create a new collection with specified item IDs."""
        endpoint = f"{self.url}/Collections"
        params = {"Name": name, "Ids": ",".join(item_ids)}
        response = requests.post(
            endpoint, headers=self.headers, params=params, timeout=self.timeout
        )
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return data

    def add_to_collection(self, collection_id: str, item_ids: list[str]) -> None:
        """Add items to an existing collection."""
        endpoint = f"{self.url}/Collections/{collection_id}/Items"
        params = {"Ids": ",".join(item_ids)}
        response = requests.post(
            endpoint, headers=self.headers, params=params, timeout=self.timeout
        )
        response.raise_for_status()


def main() -> None:
    """Main entry point to execute grouping sync."""
    url = os.environ.get("JELLYFIN_URL", "http://localhost:8096")
    api_key = os.environ.get("JELLYFIN_API_KEY", "")

    if not api_key:
        print(
            "Error: JELLYFIN_API_KEY environment variable is required.", file=sys.stderr
        )
        return

    client = JellyfinGroupings(url, api_key)
    collections = client.get_collections()
    movies = client.get_movies()

    print(f"Found {len(collections)} existing collections.")
    print(f"Found {len(movies)} movies.")


if __name__ == "__main__":
    main()
