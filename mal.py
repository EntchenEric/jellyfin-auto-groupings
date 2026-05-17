"""mal.py - MyAnimeList API client for fetching user lists."""

from __future__ import annotations

from typing import Any

import requests

MAL_API_BASE_URL = "https://api.myanimelist.net/v2"

# Request timeout (seconds)
_REQUEST_TIMEOUT: int = 15

_VALID_MAL_STATUSES: frozenset[str] = frozenset(
    {"watching", "completed", "on_hold", "dropped", "plan_to_watch"}
)


def _normalize_mal_status(status: str | None) -> str | None:
    """Normalize a user-provided MAL status string to the API's expected values."""
    if not status:
        return None
    s = status.lower().replace(" ", "_").replace("-", "_")
    mapping = {
        "current": "watching",
        "planning": "plan_to_watch",
        "paused": "on_hold",
        "all": None,
    }
    return mapping.get(s, s)


def fetch_mal_list(username: str, client_id: str, status: str | None = None) -> list[int]:
    """Fetch anime IDs from a user's MyAnimeList profile.

    Args:
        username: The MAL username.
        client_id: The MAL API Client ID.
        status: The list status to fetch (e.g., "watching", "completed", "on_hold", "dropped", "plan_to_watch").
                If None, all lists are fetched.

    Returns:
        A list of MyAnimeList anime IDs (integers).

    """
    if not client_id:
        msg = "MyAnimeList Client ID is required."
        raise ValueError(msg)

    normalized_status = _normalize_mal_status(status)

    url = f"{MAL_API_BASE_URL}/users/{username}/animelist"
    params: dict[str, Any] = {
        "fields": "id",
        "limit": 100,
    }
    if normalized_status:
        params["status"] = normalized_status

    headers = {
        "X-MAL-CLIENT-ID": client_id,
    }

    ids = []

    while url:
        response = requests.get(url, params=params, headers=headers, timeout=_REQUEST_TIMEOUT)
        response.raise_for_status()

        data = response.json()
        for entry in data.get("data", []):
            node = entry.get("node", {})
            if node.get("id"):
                ids.append(node["id"])

        # MAL pagination uses a 'next' URL in the 'paging' object
        url = data.get("paging", {}).get("next")
        # Once we have the 'next' URL, params are already included in it by MAL
        params = {}

    return ids
