"""anilist.py - AniList API client for fetching user lists."""

from __future__ import annotations

import logging

import network

__all__ = ["fetch_anilist_list"]

logger = logging.getLogger(__name__)

ANILIST_API_URL = "https://graphql.anilist.co"

# Request timeout (seconds)
_REQUEST_TIMEOUT: int = 15


def fetch_anilist_list(
    username: str,
    status: str | None = None,
    api_url: str | None = None,
) -> list[int]:
    """Fetch anime IDs from a user's AniList profile.

    Args:
        username: The AniList username.
        status: The list status to fetch (e.g., "COMPLETED", "PLANNING", "CURRENT").
                If None, all lists are fetched.
        api_url: Override URL for the AniList GraphQL endpoint.
                 Falls back to :data:`ANILIST_API_URL` when ``None``.

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
            "REPEATING": "REPEATING",
        }
        normalized_status = status_map.get(status.upper())
        if normalized_status:
            variables["status"] = normalized_status

    resolved_url = api_url or ANILIST_API_URL

    logger.debug(
        "Fetching AniList list for user=%r status=%s",
        username,
        variables.get("status", "ALL"),
    )

    response = network.post(
        resolved_url,
        json={"query": query, "variables": variables},
        timeout=_REQUEST_TIMEOUT,
    )
    response.raise_for_status()

    data = response.json()
    root = data.get("data")
    if not isinstance(root, dict):
        logger.warning("Unexpected AniList response structure: 'data' is not a dict")
        return []
    collection = root.get("MediaListCollection")
    if not isinstance(collection, dict):
        logger.warning(
            "AniList returned empty MediaListCollection for user=%r", username
        )
        return []

    media_ids: list[int] = []
    for user_list in collection.get("lists") or []:
        if not isinstance(user_list, dict):
            continue
        entries = user_list.get("entries")
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            media_id = entry.get("mediaId")
            if isinstance(media_id, int):
                media_ids.append(media_id)

    return media_ids
