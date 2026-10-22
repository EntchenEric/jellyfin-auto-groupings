"""mal.py - MyAnimeList API client for fetching user lists."""

from __future__ import annotations

import logging
from typing import Any

import requests

import network

__all__ = ["fetch_mal_list"]

logger = logging.getLogger(__name__)

MAL_API_BASE_URL = "https://api.myanimelist.net/v2"

# Request timeout (seconds)
_REQUEST_TIMEOUT: int = 15


_KNOWN_STATUSES: frozenset[str] = frozenset(
    {
        "watching",
        "completed",
        "on_hold",
        "dropped",
        "plan_to_watch",
    },
)


def _normalize_mal_status(status: str | None) -> str | None:
    """Normalize a user-provided MAL status string to the API's expected values.

    Returns ``None`` when *status* is empty or ``"all"`` (meaning fetch all lists).
    Raises :exc:`ValueError` for unrecognised status values.

    Args:
        status: The status string to normalize.

    """
    if not status:
        return None
    s = status.lower().replace(" ", "_").replace("-", "_")
    if s == "all":
        return None
    if s == "current":
        return "watching"
    if s == "planning":
        return "plan_to_watch"
    if s == "paused":
        return "on_hold"
    if s in _KNOWN_STATUSES:
        return s
    valid = sorted(_KNOWN_STATUSES)
    msg = f"Unknown MAL status: {status!r}. Valid values: {valid}"
    raise ValueError(msg)


def fetch_mal_list(
    username: str,
    client_id: str,
    status: str | None = None,
) -> list[int]:
    """Fetch anime IDs from a user's MyAnimeList profile.

    Args:
        username: The MAL username.
        client_id: The MAL API Client ID.
        status: The list status to fetch (e.g., "watching", "completed",
                "on_hold", "dropped", "plan_to_watch").
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
        try:
            response = network.get(
                url,
                params=params,
                headers=headers,
                timeout=_REQUEST_TIMEOUT,
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as exc:
            msg = f"Failed to fetch MAL list for user {username!r}: {exc}"
            raise RuntimeError(msg) from exc

        try:
            data = response.json()
        except ValueError as exc:
            msg = f"Invalid JSON response from MAL API for user {username!r}: {exc}"
            raise RuntimeError(msg) from exc

        # A malformed payload (a bare list, a string where an object belongs,
        # a non-dict entry) used to raise AttributeError out of the fetcher,
        # which sync.py does not catch for every provider. Treat anything
        # unexpected as "no more entries" instead of crashing the sync.
        if not isinstance(data, dict):
            logger.warning(
                "Unexpected MAL response shape for user %r: expected an object",
                username,
            )
            break

        entries = data.get("data")
        if isinstance(entries, list):
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                node = entry.get("node")
                if not isinstance(node, dict):
                    continue
                media_id = node.get("id")
                if isinstance(media_id, int) and not isinstance(media_id, bool):
                    ids.append(media_id)

        # MAL pagination uses a 'next' URL in the 'paging' object
        paging = data.get("paging")
        next_url = paging.get("next") if isinstance(paging, dict) else None
        if not isinstance(next_url, str) or not next_url:
            break
        url = next_url
        # Once we have the 'next' URL, params are already included in it by MAL
        params = {}

    return ids
