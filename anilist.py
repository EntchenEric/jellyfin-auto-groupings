"""anilist.py - AniList API client for fetching user lists."""

from __future__ import annotations

import logging
from typing import Any

import requests

import network

__all__ = ["fetch_anilist_list"]

logger = logging.getLogger(__name__)

ANILIST_API_URL = "https://graphql.anilist.co"

# Request timeout (seconds)
_REQUEST_TIMEOUT: int = 15


_ANILIST_STATUS_MAP: dict[str, str] = {
    "COMPLETED": "COMPLETED",
    "PLANNING": "PLANNING",
    "WATCHING": "CURRENT",
    "CURRENT": "CURRENT",
    "DROPPED": "DROPPED",
    "PAUSED": "PAUSED",
    "REWATCHING": "REPEATING",
    "REPEATING": "REPEATING",
}

_ANILIST_QUERY: str = """
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


def _resolve_anilist_status(status: str | None) -> str | None:
    """Normalize a user-provided AniList status to the API's expected value.

    Raises:
        ValueError: If *status* is not ``None``, ``"ALL"``, or a recognised
                    status key from :data:`_ANILIST_STATUS_MAP`.



    Args:
            status: The status string to normalize.

    """
    if not status or status.upper() == "ALL":
        return None
    normalized = _ANILIST_STATUS_MAP.get(status.upper())
    if normalized is None:
        valid = sorted(_ANILIST_STATUS_MAP)
        msg = f"Unknown AniList status: {status!r}. Valid values: {valid}"
        raise ValueError(msg)
    return normalized


def _extract_media_ids(data: dict[str, Any]) -> list[int]:
    """Extract integer media IDs from parsed AniList API response.

    Args:
        data: The API response data dict.

    """
    root = data.get("data")
    if not isinstance(root, dict):
        logger.warning("Unexpected AniList response structure: 'data' is not a dict")
        return []
    collection = root.get("MediaListCollection")
    if not isinstance(collection, dict):
        logger.warning("AniList returned empty MediaListCollection")
        return []

    ids: list[int] = []
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
                ids.append(media_id)
    return ids


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
    normalized_status = _resolve_anilist_status(status)

    variables: dict[str, str] = {"userName": username}
    if normalized_status:
        variables["status"] = normalized_status

    resolved_url = api_url or ANILIST_API_URL

    logger.debug(
        "Fetching AniList list for user=%r status=%s",
        username,
        normalized_status or "ALL",
    )

    try:
        response = network.post(
            resolved_url,
            json={"query": _ANILIST_QUERY, "variables": variables},
            timeout=_REQUEST_TIMEOUT,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as exc:
        msg = f"Failed to fetch AniList list for user {username!r}: {exc}"
        raise RuntimeError(msg) from exc

    return _extract_media_ids(response.json())
