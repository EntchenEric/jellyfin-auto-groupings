"""imdb.py - IMDb list scraping utilities.

Provides a single public function for fetching ordered IMDb IDs from a
public IMDb list page via regex extraction over the rendered HTML.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

import requests

import network
from _common import DEFAULT_LIST_FETCH_TIMEOUT as _REQUEST_TIMEOUT
from _common import DEFAULT_LIST_MAX_PAGES
from _common import DEFAULT_SCRAPING_HEADERS as _REQUEST_HEADERS

__all__ = ["fetch_imdb_list"]

logger = logging.getLogger(__name__)

# Maximum number of pages to scrape (safety guard, ~5 000 items at 100/page).
# Shared with the other list fetchers so every source truncates at the same
# point, and so the README's "safety cap (50 pages)" is actually true here.
_MAX_PAGES: int = DEFAULT_LIST_MAX_PAGES

# IMDb list IDs are the literal ``ls`` prefix followed by digits. Anything
# else (``ls``, ``lsabc``) would be pasted straight into the request URL and
# fetched only to come back as an empty or error page.
_LIST_ID_PATTERN: re.Pattern[str] = re.compile(r"^ls\d+$")

#: Hosts that may serve an IMDb list page. A URL is only accepted when its
#: host is one of these; the ID is then taken from the trimmed path rather
#: than from an unanchored ``ls\d+`` search.
_IMDB_HOSTS: frozenset[str] = frozenset({"imdb.com", "www.imdb.com", "m.imdb.com"})

# Matches the list-ID segment of an IMDb list path, e.g. ``/list/ls000024390/``.
_LIST_PATH_PATTERN: re.Pattern[str] = re.compile(r"/list/(ls\d+)(?:/|$)")


def _normalize_list_id(list_id: str) -> str:
    """Reduce *list_id* to a bare ``ls\\d+`` value or raise :exc:`ValueError`.

    A full IMDb list URL is accepted only when it points at an IMDb host, and
    its ID is read from the path. The previous unanchored ``ls\\d+`` search ran
    over the whole input, so ``"ls123abc"`` and ``"garbage-ls123"`` were
    silently truncated to a *different*, valid-looking ID and fetched as if the
    user had asked for it. Anything that is neither a bare ID nor a genuine
    IMDb list URL is rejected instead of being guessed at.

    Args:
        list_id: A bare ``ls\\d+`` list ID or a full IMDb list URL.

    Returns:
        The bare list ID.

    Raises:
        ValueError: If *list_id* cannot be resolved to an IMDb list ID.

    """
    candidate = list_id.strip()
    if _LIST_ID_PATTERN.match(candidate):
        return candidate

    # Tolerate a scheme-less input such as ``imdb.com/list/ls123``; without a
    # scheme ``urlparse`` reports an empty ``hostname`` and the URL would be
    # rejected even though it names a real IMDb list.
    parsed = urlparse(candidate if "//" in candidate else f"https://{candidate}")
    host = (parsed.hostname or "").lower()
    if parsed.scheme in ("http", "https") and host in _IMDB_HOSTS:
        path_match = _LIST_PATH_PATTERN.search(parsed.path)
        if path_match:
            return path_match.group(1)

    msg = f"Invalid IMDb list ID: {list_id!r}. Expected format: ls000024390"
    raise ValueError(msg)


def fetch_imdb_list(list_id: str) -> list[str]:
    r"""Fetch an IMDb list and return its IMDb title IDs in list order.

    *list_id* may be a full URL (e.g. ``https://www.imdb.com/list/ls000024390/``)
    or a bare list ID (e.g. ``ls000024390``).  The function paginates
    automatically and deduplicates results while preserving order.

    Args:
        list_id: A full IMDb list URL or a bare ``ls\\d+`` list ID.

    Returns:
        An ordered list of IMDb title IDs (e.g. ``["tt0111161", ...]``).

    Raises:
        ValueError: If *list_id* cannot be parsed as a valid IMDb list ID.
        RuntimeError: If an HTTP error occurs while fetching a page.

    """
    list_id = _normalize_list_id(list_id)

    ids: list[str] = []
    seen: set[str] = set()
    page: int = 1

    while True:
        page_url = (
            f"https://www.imdb.com/list/{list_id}/"
            f"?sort=list_order,asc&st_dt=&mode=detail&page={page}"
        )
        try:
            resp = network.get(
                page_url,
                headers=_REQUEST_HEADERS,
                timeout=_REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
        except requests.exceptions.RequestException as exc:
            logger.exception("HTTP error fetching IMDb list page %d", page)
            msg = f"Failed to fetch IMDb list page {page}: {exc}"
            raise RuntimeError(msg) from exc

        html: str = resp.text

        # Extract title IDs from canonical anchor hrefs: href="/title/tt1234567/"
        found: list[str] = re.findall(r'href="/title/(tt\d+)/', html)

        for tt in found:
            if tt not in seen:
                ids.append(tt)
                seen.add(tt)

        # Stop when there is no pagination link pointing to the next page
        has_next = re.search(r'class="[^"]*next-page[^"]*"', html) or re.search(
            r'rel="next"',
            html,
        )
        if not has_next:
            break
        if page >= _MAX_PAGES:
            # Stopping silently would look like "the list ends here", so the
            # user gets a truncated collection with no hint that more exists.
            logger.warning(
                "Stopping after %d pages (the safety limit) — the IMDb list "
                "%s has more entries than were fetched",
                _MAX_PAGES,
                list_id,
            )
            break

        page += 1

    return ids
