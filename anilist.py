"""
anilist.py – AniList API client for fetching user lists.
"""

from __future__ import annotations

import requests

ANILIST_API_URL = "https://graphql.anilist.co"

# Request timeout (seconds)
_REQUEST_TIMEOUT: int = 15


def fetch_anilist_list(username: str, status: str | None = None) -> list[int]:
    """
    Fetch anime IDs from a user's AniList profile.

    Args:
        username: The AniList username.
        status: The list status to fetch (e.g., "COMPLETED", "PLANNING", "CURRENT").
                If None, all lists are fetched.

    Returns:
        A list of AniList anime IDs (integers).
    """
    query = """
    query ($userName: String, $status: MediaListStatus) {
      MediaListCollection(userName: $userName, type: ANIME, status: $status) {
        lists {
          name
          entries {
            mediaId
          }
        }
      }
    }
    """

    variables = {
        "userName": username,
    }
    if status and status.upper() != "ALL":
        # Normalize status
        status_map = {
            "COMPLETED": "COMPLETED",
            "PLANNING": "PLANNING",
            "WATCHING": "CURRENT",
            "CURRENT": "CURRENT",
            "DROPPED": "DROPPED",
            "PAUSED": "PAUSED",
            "REWATCHING": "REPEATING",
            "REPEATING": "REPEATING"
        }
        normalized_status = status_map.get(status.upper())
        if normalized_status:
            variables["status"] = normalized_status

    response = requests.post(
        ANILIST_API_URL,
        json={"query": query, "variables": variables},
        timeout=_REQUEST_TIMEOUT
    )
    response.raise_for_status()

    data = response.json()
    root = data.get("data")
    if not isinstance(root, dict):
        return []
    collection = root.get("MediaListCollection") or {}
    if not collection:
        return []

    return [
        entry["mediaId"]
        for user_list in collection.get("lists", [])
        for entry in user_list.get("entries", [])
        if entry.get("mediaId")
    ]
