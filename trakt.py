"""trakt.py - Trakt API list fetching utilities.

Provides a single public function for fetching ordered IMDb IDs from a
Trakt list via the official Trakt v2 API.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import requests

__all__ = ["fetch_trakt_list"]

logger = logging.getLogger(__name__)

# Request timeout (seconds)
_REQUEST_TIMEOUT: int = 15

# Maximum pages to fetch (safety guard, 50 000 items at 1 000/page)
_MAX_PAGES: int = 50
_PAGE_LIMIT: int = 1_000

_TRAKT_API_BASE: str = "https://api.trakt.tv"


def _parse_trakt_list_url(list_url: str) -> tuple[str, str]:
    """Parse username and list slug from a Trakt URL or shorthand."""
    full_url_match = re.search(
        r"trakt\.tv/users/([^/]+)/lists/([^/?#]+)", list_url,
    )
    if full_url_match:
        return full_url_match.group(1), full_url_match.group(2)
    if "/" in list_url and not list_url.startswith("http"):
        parts = list_url.split("/", 1)
        return parts[0], parts[1]
    msg = (
        f"Invalid Trakt list URL: {list_url!r}. "
        "Expected format: https://trakt.tv/users/username/lists/list-slug"
    )
    raise ValueError(msg)


def fetch_trakt_list(list_url: str, client_id: str) -> list[str]:
    """Fetch a Trakt list and return its items as IMDb title IDs in list order.

    *list_url* may be a full Trakt URL
    (``https://trakt.tv/users/jane/lists/my-list``) or a shorthand
    ``username/list-slug`` string.

    Args:
        list_url: Full Trakt list URL or ``"username/list-slug"`` shorthand.
        client_id: Trakt API Client ID (``trakt_client_id`` in config).

    Returns:
        An ordered list of IMDb title IDs (``["tt0111161", ...]``).  Items
        without an IMDb ID are silently skipped.

    Raises:
        ValueError: If *client_id* is empty or *list_url* cannot be parsed.
        RuntimeError: If an HTTP error occurs while fetching a page.

    """
    if not client_id:
        msg = (
            "A Trakt API Client ID (trakt_client_id) is required to fetch Trakt lists."
        )
        raise ValueError(msg)

    list_url = list_url.strip()
    username, list_slug = _parse_trakt_list_url(list_url)

    headers: dict[str, str] = {
        "trakt-api-key": client_id,
        "trakt-api-version": "2",
        "Content-Type": "application/json",
    }

    ids: list[str] = []
    page: int = 1

    while True:
        url = (
            f"{_TRAKT_API_BASE}/users/{username}/lists/{list_slug}/items"
            f"?page={page}&limit={_PAGE_LIMIT}"
        )
        try:
            resp = requests.get(url, headers=headers, timeout=_REQUEST_TIMEOUT)
            resp.raise_for_status()
        except requests.exceptions.RequestException as exc:
            msg = f"Failed to fetch Trakt list page {page}: {exc}"
            raise RuntimeError(msg) from exc

        items: list[dict[str, Any]] = resp.json()
        if not items:
            break

        for entry in items:
            item_type: str | None = entry.get("type")  # "movie" or "show"
            media: dict[str, Any] = entry.get(item_type, {}) if item_type else {}
            imdb_id: str | None = media.get("ids", {}).get("imdb")
            if imdb_id and imdb_id not in ids:
                ids.append(imdb_id)

        try:
            total_pages: int = int(resp.headers.get("X-Pagination-Page-Count", 1))
        except ValueError:
            total_pages = 1
        if page >= total_pages or page >= _MAX_PAGES:
            break
        page += 1

    return ids
