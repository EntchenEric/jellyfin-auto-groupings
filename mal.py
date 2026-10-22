"""mal.py - MyAnimeList API client for fetching user lists."""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlparse

import requests

import network
from _common import DEFAULT_LIST_MAX_PAGES

__all__ = ["fetch_mal_list"]

logger = logging.getLogger(__name__)

MAL_API_BASE_URL = "https://api.myanimelist.net/v2"

# Request timeout (seconds)
_REQUEST_TIMEOUT: int = 15

#: Safety guard shared with the other list fetchers. This walker used to
#: follow ``paging.next`` with no bound at all: an upstream that always
#: returns a ``next`` URL (or repeats the same one) looped forever and the
#: sync run never finished. The cap matches IMDb/Trakt/TMDb/Letterboxd so
#: every source truncates at the same point and logs the same warning.
_MAX_PAGES: int = DEFAULT_LIST_MAX_PAGES

#: Host that must serve a ``paging.next`` URL. The next URL comes from the
#: API response, but a malformed or tampered body could point it anywhere;
#: following it blindly turned the fetcher into an open HTTP client for the
#: attacker's host (a server-side request forgery primitive) and sent the
#: user's MAL client ID there in a header.
_MAL_API_HOST: str = "api.myanimelist.net"

#: MAL usernames are alphanumeric plus ``-`` and ``_``. The previous code
#: pasted the value straight into the request path, so a value such as
#: ``"../../admin"`` produced ``/users/../../admin/animelist`` and the
#: request escaped the ``/users/`` prefix instead of naming a user.
_MAL_USERNAME_PATTERN: re.Pattern[str] = re.compile(r"^[A-Za-z0-9_-]+$")


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

    if not isinstance(username, str) or not _MAL_USERNAME_PATTERN.match(username):
        msg = (
            f"Invalid MyAnimeList username: {username!r}. "
            "Expected letters, digits, hyphens and underscores only."
        )
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
    page = 1

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
        if not isinstance(next_url, str) or not next_url.strip():
            break

        # Only follow the next page on the MAL API itself. A URL that names
        # another host, or that is not HTTP(S) at all, ends the walk instead
        # of sending the client ID somewhere else.
        parsed_next = urlparse(next_url)
        next_host = (parsed_next.hostname or "").lower()
        if parsed_next.scheme not in ("http", "https") or next_host != _MAL_API_HOST:
            logger.warning(
                "Ignoring MAL pagination URL on unexpected host %r for user %r",
                next_host or next_url,
                username,
            )
            break

        if page >= _MAX_PAGES:
            logger.warning(
                "Stopping after %d pages (the safety limit) — the "
                "MyAnimeList list for %r has more entries than were fetched",
                _MAX_PAGES,
                username,
            )
            break

        url = next_url
        page += 1
        # Once we have the 'next' URL, params are already included in it by MAL
        params = {}

    return ids
