"""anilist.py - AniList API client for fetching user lists."""

from __future__ import annotations

import logging
import re
from typing import Any

import requests

import network
from _common import parse_outbound_url

__all__ = ["fetch_anilist_list"]

logger = logging.getLogger(__name__)

ANILIST_API_URL = "https://graphql.anilist.co"

# Request timeout (seconds)
_REQUEST_TIMEOUT: int = 15

# A host is letters/digits/hyphens/dots (or an IP literal); anything else
# means ``parse_outbound_url`` coerced plain prose such as "not a url" into a
# "host". Posting to that can only fail with an opaque InvalidURL, so reject
# it here with the fetcher's own message.
_HOSTNAME_PATTERN: re.Pattern[str] = re.compile(
    r"^(?:[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?\.)+[A-Za-z0-9-]+$"
    r"|^\d{1,3}(?:\.\d{1,3}){3}$"
    r"|^\[[0-9a-fA-F:]+\]$",
)


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

    Args:
        status: The status string to normalize.

    Raises:
        ValueError: If *status* is not ``None``, ``"ALL"``, or a recognised
                    status key from :data:`_ANILIST_STATUS_MAP`.

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
    lists = collection.get("lists")
    if not isinstance(lists, list):
        return ids
    for user_list in lists:
        if not isinstance(user_list, dict):
            continue
        entries = user_list.get("entries")
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            media_id = entry.get("mediaId")
            # ``bool`` is an ``int`` subclass, so ``True`` would otherwise be
            # collected as media ID 1.
            if isinstance(media_id, int) and not isinstance(media_id, bool):
                ids.append(media_id)
    return ids


def _resolve_anilist_api_url(api_url: str | None) -> str:
    """Validate the AniList endpoint override, returning the usable URL.

    ``anilist_api_url`` is user-controlled input (``config.json`` or the
    ``ANILIST_API_URL`` environment variable) that reaches ``network.post``
    directly, so it is validated with the same authority check the list
    fetchers apply to their URLs: on an authority where ``urlparse`` and the
    HTTP client disagree (``https://evil.example\\@graphql.anilist.co``) the
    two parsers report different hosts, so posting verbatim sent the request
    to whichever host the client resolved — a server-side request forgery
    primitive driven from config. A custom self-hosted endpoint stays
    allowed; only unusable or ambiguous URLs are rejected.

    Args:
        api_url: The configured override, or ``None`` for the built-in default.

    Returns:
        The canonical URL to post to (scheme, host, path; no query, fragment,
        or credentials).

    Raises:
        ValueError: If the override is not an http(s) URL with an unambiguous
            authority and no userinfo.

    """
    if api_url is None:
        return ANILIST_API_URL
    base = parse_outbound_url(api_url)
    if base is None:
        msg = f"Invalid AniList API URL: {api_url!r}"
        raise ValueError(msg)
    # ``parse_outbound_url`` coerces scheme-less prose ("not a url") into a
    # "host"; require the result to actually look like a hostname.
    host = base.split("//", 1)[-1].split("/", 1)[0]
    if not _HOSTNAME_PATTERN.match(host):
        msg = f"Invalid AniList API URL: {api_url!r}"
        raise ValueError(msg)
    return base


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

    resolved_url = _resolve_anilist_api_url(api_url)

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

    try:
        payload = response.json()
    except ValueError as exc:
        msg = f"Invalid JSON response from AniList API for user {username!r}: {exc}"
        raise RuntimeError(msg) from exc

    # ``_extract_media_ids`` reads ``data`` off this value. A body that is a
    # bare list or a string raised ``AttributeError``, which the sync layer
    # does not catch, so one malformed response aborted the whole run
    # instead of failing this group.
    if not isinstance(payload, dict):
        msg = (
            f"Unexpected AniList API response shape for user {username!r}: "
            f"expected a JSON object, got {type(payload).__name__}"
        )
        raise RuntimeError(msg)  # noqa: TRY004 - callers handle RuntimeError

    return _extract_media_ids(payload)
