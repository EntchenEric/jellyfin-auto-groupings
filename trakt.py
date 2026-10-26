"""trakt.py - Trakt API list fetching utilities.

Provides a single public function for fetching ordered IMDb IDs from a
Trakt list via the official Trakt v2 API.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlparse

import requests  # keep for exception type references

import network
from _common import host_matches, split_outbound_url

__all__ = ["fetch_trakt_list"]

logger = logging.getLogger(__name__)

# Request timeout (seconds)
_REQUEST_TIMEOUT: int = 15

# Maximum pages to fetch (safety guard, 50 000 items at 1 000/page)
_MAX_PAGES: int = 50
_PAGE_LIMIT: int = 1_000

_TRAKT_API_BASE: str = "https://api.trakt.tv"

#: Hosts that may serve a Trakt list page. The previous parse searched the
#: whole input for ``trakt.tv/users/<name>/lists/<slug>``, so a URL on any
#: host that merely *mentioned* that path (in a query string, say) supplied
#: the username and slug that were then fetched from the Trakt API.
_TRAKT_HOSTS: frozenset[str] = frozenset({"trakt.tv", "www.trakt.tv"})

# List path of a Trakt list URL, e.g. ``/users/jane/lists/my-list``.
_TRAKT_LIST_PATH_PATTERN: re.Pattern[str] = re.compile(
    r"/users/([^/]+)/lists/([^/?#]+)",
)

# A shorthand segment is a username or a slug: no scheme, no whitespace,
# no path separators. Usernames may contain a dot, so a first segment is only
# treated as a hostname when it actually is a Trakt host.
_TRAKT_SHORTHAND_SEGMENT: re.Pattern[str] = re.compile(r"^[A-Za-z0-9_.@-]+$")


def _trakt_error(list_url: str) -> ValueError:
    """Build the shared "unparseable Trakt reference" error."""
    return ValueError(
        f"Invalid Trakt list URL: {list_url!r}. "
        "Expected format: https://trakt.tv/users/username/lists/list-slug",
    )


def _parse_trakt_list_url(list_url: str) -> tuple[str, str]:
    """Parse username and list slug from a Trakt URL or shorthand.

    A full URL is accepted only when it points at a Trakt host, and the
    username and slug are read from its path. The previous implementation
    searched the raw input for the list path anywhere in the string, so
    ``https://evil.example/?u=trakt.tv/users/jane/lists/my-list`` was accepted
    and the sync then queried the Trakt API for ``jane``'s list instead of
    rejecting input that names no Trakt list at all.

    Two conveniences are preserved: a URL wrapped in Markdown link syntax
    (``[text](url)``, as pasted from a chat client) and a scheme-less
    ``trakt.tv/users/...`` URL. The shorthand ``username/list-slug`` form is
    still accepted.

    Args:
        list_url: The Trakt list URL, scheme-less URL, or ``user/slug``.

    Returns:
        A (username, list_slug) tuple.

    Raises:
        ValueError: If the URL cannot be parsed.

    """
    candidate = list_url.strip()
    if not candidate:
        raise _trakt_error(list_url)

    # Pull the URL out of Markdown link syntax before looking at it, so the
    # host check sees the URL and not the surrounding punctuation.
    markdown_url = re.search(r"https?://[^\s)\]]+", candidate)
    if markdown_url:
        candidate = markdown_url.group(0)

    if "//" in candidate or candidate.lower().startswith("http"):
        # ``split_outbound_url`` rejects a URL whose apparent host differs
        # between ``urlparse`` and the HTTP client, so
        # ``https://evil.example\@trakt.tv/users/jane/lists/x`` cannot supply
        # a username/slug while really naming someone else's server.
        split = split_outbound_url(candidate)
        if split is None:
            raise _trakt_error(list_url)
        base, host = split
        if not host_matches(host, _TRAKT_HOSTS, allow_subdomains=False):
            raise _trakt_error(list_url)
        path_match = _TRAKT_LIST_PATH_PATTERN.search(urlparse(base).path)
        if not path_match:
            raise _trakt_error(list_url)
        return path_match.group(1), path_match.group(2)

    if "/" not in candidate:
        raise _trakt_error(list_url)

    username, _, rest = candidate.partition("/")
    # A scheme-less URL such as ``trakt.tv/users/jane/lists/my-list`` has the
    # Trakt host in its first segment; validate it like a full URL instead of
    # treating ``trakt.tv`` as a username. Any other segment is a username,
    # which may itself contain a dot.
    if username.lower() in _TRAKT_HOSTS:
        return _parse_trakt_list_url(f"https://{candidate}")

    slug = rest.split("?", 1)[0].split("#", 1)[0].strip("/")
    if not (
        _TRAKT_SHORTHAND_SEGMENT.match(username)
        and _TRAKT_SHORTHAND_SEGMENT.match(slug)
    ):
        raise _trakt_error(list_url)
    return username, slug


def _build_trakt_headers(client_id: str) -> dict[str, str]:
    """Build standard Trakt API request headers.

    Args:
        client_id: The Trakt API Client ID.

    Returns:
        A dict of HTTP headers.

    """
    return {
        "trakt-api-key": client_id,
        "trakt-api-version": "2",
        "Content-Type": "application/json",
    }


def _fetch_trakt_page(
    username: str,
    list_slug: str,
    page: int,
    headers: dict[str, str],
) -> tuple[list[dict[str, Any]], int]:
    """Fetch a single Trakt list page.

    Args:
        username: Trakt username.
        list_slug: Trakt list slug.
        page: Page number to fetch.
        headers: HTTP headers for the request.

    Returns:
        A tuple of (items, total_pages).

    Raises:
        RuntimeError: If an HTTP error occurs.
        TypeError: If the response body is not a JSON list.

    """
    url = (
        f"{_TRAKT_API_BASE}/users/{username}/lists/{list_slug}/items"
        f"?page={page}&limit={_PAGE_LIMIT}"
    )
    try:
        resp = network.get(url, headers=headers, timeout=_REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.exceptions.RequestException as exc:
        msg = f"Failed to fetch Trakt list page {page}: {exc}"
        raise RuntimeError(msg) from exc

    try:
        items = resp.json()
    except ValueError as exc:
        msg = f"Invalid JSON response from Trakt API on page {page}: {exc}"
        raise RuntimeError(msg) from exc
    if not isinstance(items, list):
        msg = f"Unexpected Trakt API response shape on page {page}: expected a list"
        raise TypeError(msg)
    try:
        total_pages: int = int(resp.headers.get("X-Pagination-Page-Count", 1))
    except ValueError:
        total_pages = 1
    return items, total_pages


def _extract_imdb_ids_from_page(
    resp_json: list[dict[str, Any]],
    ids: list[str],
    seen: set[str],
) -> None:
    """Extract IMDb IDs from a Trakt page response, deduplicating via *seen*.

    Args:
        resp_json: The parsed JSON response (list of items).
        ids: List to collect IDs into.
        seen: Set of already-seen IDs for deduplication.

    """
    for entry in resp_json:
        if not isinstance(entry, dict):
            # Tolerate malformed entries (e.g. a bare string) instead of crashing
            continue
        item_type: str | None = entry.get("type")  # "movie" or "show"
        media: Any = entry.get(item_type, {}) if item_type else {}
        if not isinstance(media, dict):
            continue
        ids_obj: Any = media.get("ids", {})
        if not isinstance(ids_obj, dict):
            continue
        imdb_id: Any = ids_obj.get("imdb")
        # Trakt normally sends a string (``"tt0111161"``) or ``None``, but a
        # malformed or proxied response can put an object or a number here.
        # ``imdb_id not in seen`` on an unhashable value raised
        # ``TypeError: unhashable type: 'dict'``, which sync.py's handler does
        # not catch, so one bad entry aborted the whole run. A number would
        # also be matched against Jellyfin's string provider IDs and never
        # match, so only non-empty strings are accepted.
        if not isinstance(imdb_id, str):
            continue
        imdb_id = imdb_id.strip()
        if imdb_id and imdb_id not in seen:
            seen.add(imdb_id)
            ids.append(imdb_id)


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
    headers = _build_trakt_headers(client_id)

    ids: list[str] = []
    seen: set[str] = set()
    page: int = 1

    while True:
        try:
            items, total_pages = _fetch_trakt_page(
                username,
                list_slug,
                page,
                headers,
            )
        except TypeError as exc:
            # ``_fetch_trakt_page`` reports a wrong response shape as
            # ``TypeError``, but every caller of this function (sync.py)
            # treats a fetch failure as ``RuntimeError``/``ValueError``. An
            # uncaught ``TypeError`` escaped the group's error handling and
            # aborted the whole sync run instead of failing one group.
            msg = f"Unexpected Trakt API response for list {list_url!r}: {exc}"
            raise RuntimeError(msg) from exc
        if not items:
            break
        _extract_imdb_ids_from_page(items, ids, seen)
        if page >= total_pages:
            break
        if page >= _MAX_PAGES:
            # The README promises a warning when the cap truncates a list;
            # stopping silently makes a partial result look complete.
            logger.warning(
                "Stopping after %d pages (the safety limit) — the Trakt list "
                "%r has more entries than were fetched",
                _MAX_PAGES,
                list_url,
            )
            break
        page += 1

    return ids
