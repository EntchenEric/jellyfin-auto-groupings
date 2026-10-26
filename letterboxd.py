"""letterboxd.py - Letterboxd list scraping utilities.

Provides a single public function for fetching ordered IMDb or TMDb IDs from a
Letterboxd list by parsing the HTML.
"""

from __future__ import annotations

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from http import HTTPStatus
from urllib.parse import urlparse

import requests

import network
from _common import DEFAULT_LIST_MAX_PAGES, DEFAULT_SCRAPING_HEADERS

__all__ = ["fetch_letterboxd_list"]

logger = logging.getLogger(__name__)

# Request timeouts (seconds)
_FILM_PAGE_TIMEOUT: int = 10
_LIST_PAGE_TIMEOUT: int = 15

_MAX_EMPTY_CONSECUTIVE: int = 3

#: Safety guard shared with the other list fetchers (~72 films per page).
_MAX_PAGES: int = DEFAULT_LIST_MAX_PAGES
_MAX_WORKERS: int = 6

_REQUEST_HEADERS: dict[str, str] = {
    **DEFAULT_SCRAPING_HEADERS,
    "Referer": "https://letterboxd.com/",
}


# Matches each film's slug marker in list-page HTML.
_SLUG_PATTERN: str = r'data-film-slug="([^"]+)"'

# Matches one ``class`` attribute value. Letterboxd renders the next-page link
# as ``class="next "`` (trailing space) and marks the end of a list with
# ``class="next  is-disabled"``, so the value has to be split into tokens
# instead of compared against a literal string.
_CLASS_ATTR_PATTERN: re.Pattern[str] = re.compile(r'class="([^"]*)"')

# Token marker of a disabled next-page link.
_DISABLED_CLASS: str = "is-disabled"

# Matches a trailing ``/page/<n>`` segment on a list URL.
_PAGE_SEGMENT_PATTERN: re.Pattern[str] = re.compile(r"/page/\d+/?$")

#: Host that must serve a Letterboxd list URL. The previous check was a
#: substring test on the raw input, so ``https://evil.example/?r=letterboxd.com``
#: passed and the fetcher then requested pages from the attacker's host — a
#: server-side request forgery primitive reachable from a group's ``value``.
_LETTERBOXD_HOST: str = "letterboxd.com"


def _validate_list_url(list_url: str) -> str:
    """Return the list's canonical URL, or raise :exc:`ValueError`.

    The returned URL always addresses page 1 of the list and carries no
    query string, no fragment and no trailing slash, so the caller can build
    ``<url>/page/<n>/`` for later pages.

    Args:
        list_url: The candidate Letterboxd list URL.

    Returns:
        The cleaned URL.

    Raises:
        ValueError: If *list_url* is not an HTTP(S) URL on ``letterboxd.com``.

    """
    cleaned = list_url.strip()
    # Tolerate a scheme-less input such as ``letterboxd.com/user/list/x``,
    # which the old substring check accepted; requests needs a scheme.
    if cleaned and "//" not in cleaned:
        cleaned = f"https://{cleaned}"
    parsed = urlparse(cleaned)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https") or not (
        host == _LETTERBOXD_HOST or host.endswith("." + _LETTERBOXD_HOST)
    ):
        msg = f"Invalid Letterboxd URL: {list_url!r}"
        raise ValueError(msg)

    # A pasted browser URL routinely carries a tracking query string or a
    # fragment, and may already point at ``/page/3/``. Only the path names the
    # list, so the page walk has to start from a URL built purely from
    # scheme, host and path: appending ``/page/2/`` to
    # ``…/x?utm_source=tw`` produced ``…/x?utm_source=tw/page/2/``, which the
    # server resolved back to page 1. The walk then re-fetched page 1 until
    # the page cap and silently returned just the first page's films.
    path = _PAGE_SEGMENT_PATTERN.sub("", parsed.path).rstrip("/")
    return f"{parsed.scheme}://{parsed.netloc}{path}"


# Ordered ID patterns for a single film's HTML segment. Higher-priority
# patterns (TMDb data attribute) are tried first; the first hit wins.
# Each film's markup is scanned in isolation, so these must never reach
# across a neighbouring film's block.
_ID_SEGMENT_PATTERNS: list[str] = [
    # data-tmdb-id attribute directly on the film element (fastest, no href match)
    r'data-tmdb-id="(\d+)"',
    # IMDb URL in a link
    r"imdb\.com/title/(tt\d+)",
    # TMDb URL in a link
    r"themoviedb\.org/movie/(\d+)",
]


def _film_segments(html: str) -> list[tuple[str, str]]:
    """Split list-page HTML into ``(slug, segment)`` pairs.

    A film's segment runs from its slug marker up to the next film's slug
    marker, which keeps the ID lookup inside that film's own markup. Slicing
    rather than using a ``.*?`` regex matters because real Letterboxd markup
    wraps a single film's attributes across several lines: non-DOTALL ``.*?``
    never matched, and DOTALL alone would let a film without an ID borrow the
    next film's ID.

    Args:
        html: The HTML content of the Letterboxd list page.

    Returns:
        Pairs of film slug and the HTML that belongs to that film.

    """
    markers = list(re.finditer(_SLUG_PATTERN, html))
    segments: list[tuple[str, str]] = []
    for index, marker in enumerate(markers):
        end = markers[index + 1].start() if index + 1 < len(markers) else len(html)
        segments.append((marker.group(1), html[marker.start() : end]))
    return segments


def _extract_ids_from_list_page(html: str) -> dict[str, str]:
    """Extract IMDb/TMDb IDs embedded in list-page HTML.

    Returns a mapping of ``slug -> id`` for films where an ID was found
    directly on the list page, avoiding a per-film page fetch.

    Args:
        html: The HTML content of the Letterboxd list page.

    """
    found: dict[str, str] = {}

    for slug, segment in _film_segments(html):
        if slug in found:
            continue
        for pattern in _ID_SEGMENT_PATTERNS:
            match = re.search(pattern, segment)
            if match:
                found[slug] = match.group(1)
                break

    return found


def _deduplicate_slugs(slugs: list[str]) -> list[str]:
    """Preserve order while removing duplicate slugs.

    Args:
        slugs: List of Letterboxd film slugs.

    """
    seen: set[str] = set()
    result: list[str] = []
    for slug in slugs:
        if slug not in seen:
            seen.add(slug)
            result.append(slug)
    return result


def _fetch_ids_for_slugs(slugs: list[str]) -> dict[str, str | None]:
    """Resolve slugs to IDs in parallel using ThreadPoolExecutor.

    Args:
        slugs: List of Letterboxd film slugs.

    """
    results: dict[str, str | None] = {}
    if not slugs:
        return results
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as executor:
        future_map = {executor.submit(_fetch_id_for_slug, slug): slug for slug in slugs}
        for future in as_completed(future_map):
            slug = future_map[future]
            try:
                results[slug] = future.result()
            except (OSError, RuntimeError):
                logger.debug("Unexpected error for '%s'", slug, exc_info=True)
                results[slug] = None
    return results


def _has_next_page(html: str) -> bool:
    """Return whether *html* links to a further page of the list.

    The check inspects the ``next`` token of every ``class`` attribute rather
    than looking for the literal ``class="next"``. Real Letterboxd markup
    writes ``class="next "`` with a trailing space, so the literal comparison
    never matched and every list was silently truncated to its first page
    (72 films). A disabled control marks the last page and must not paginate
    further, otherwise the last page is requested twice.

    Args:
        html: The HTML content of a Letterboxd list page.

    Returns:
        ``True`` when a usable next-page link is present.

    """
    saw_next_token = False
    for match in _CLASS_ATTR_PATTERN.finditer(html):
        tokens = match.group(1).split()
        if "next" not in tokens:
            continue
        if _DISABLED_CLASS in tokens:
            # The control exists but marks the last page; a ``rel="next"``
            # attribute elsewhere must not override that.
            return False
        saw_next_token = True
    if saw_next_token:
        return True
    return 'rel="next"' in html


def _merge_page_results(
    unique_slugs: list[str],
    ids_from_list: dict[str, str],
    slug_results: dict[str, str | None],
    ids: list[str],
    seen_ids: set[str],
) -> None:
    """Append newly discovered IDs to *ids* while tracking *seen_ids*.

    Args:
        unique_slugs: Deduplicated list of slugs.
        ids_from_list: IDs extracted from the list page HTML.
        slug_results: Results from fetching IDs for each slug.
        ids: List to collect IDs into.
        seen_ids: Set of already-seen IDs.

    """
    for slug in unique_slugs:
        film_id = ids_from_list.get(slug) or slug_results.get(slug)
        if film_id and film_id not in seen_ids:
            ids.append(film_id)
            seen_ids.add(film_id)


def _fetch_id_for_slug(slug: str) -> str | None:
    """Fetch the IMDb or TMDb ID from a film's detail page.

    Args:
        slug: The Letterboxd film slug (e.g., ``"the-godfather"``).

    Returns:
        The extracted ID as a string, or ``None`` if no ID was found.

    """
    film_url = f"https://letterboxd.com/film/{slug}/"
    try:
        resp = network.get(
            film_url,
            headers=_REQUEST_HEADERS,
            timeout=_FILM_PAGE_TIMEOUT,
        )
        resp.raise_for_status()
        html = resp.text

        imdb_match = re.search(r'href="[^"]*imdb\.com/title/(tt\d+)', html)
        if imdb_match:
            return imdb_match.group(1)

        tmdb_match = re.search(r'href="[^"]*themoviedb\.org/movie/(\d+)', html)
        if tmdb_match:
            return tmdb_match.group(1)

        tmdb_attr = re.search(r'data-tmdb-id="(\d+)"', html)
        if tmdb_attr:
            return tmdb_attr.group(1)

    except requests.exceptions.RequestException:
        logger.warning(
            "Failed to fetch Letterboxd film page for '%s'",
            slug,
            exc_info=True,
        )
        return None

    return None


def fetch_letterboxd_list(list_url: str) -> list[str]:
    """Fetch a Letterboxd list and return its IMDb or TMDb IDs in list order.

    Extracts IDs embedded in list-page HTML where possible; remaining slugs
    are resolved via parallel film-page requests.

    Args:
        list_url: Full Letterboxd list URL.

    Returns:
        An ordered list of IDs (IMDb ``tt...`` or TMDb numeric strings).

    Raises:
        ValueError: If *list_url* is invalid.
        RuntimeError: If an HTTP error occurs while fetching a list page.

    """
    list_url = _validate_list_url(list_url)

    ids: list[str] = []
    seen_ids: set[str] = set()
    page = 1
    consecutive_empty: int = 0

    while True:
        current_url = f"{list_url}/page/{page}/" if page > 1 else f"{list_url}/"

        try:
            resp = network.get(
                current_url,
                headers=_REQUEST_HEADERS,
                timeout=_LIST_PAGE_TIMEOUT,
            )
            if resp.status_code == HTTPStatus.NOT_FOUND and page > 1:
                break
            resp.raise_for_status()
        except requests.exceptions.RequestException as exc:
            msg = f"Failed to fetch Letterboxd list page {page}: {exc}"
            raise RuntimeError(msg) from exc

        html = resp.text

        ids_from_list = _extract_ids_from_list_page(html)

        slugs = re.findall(r'data-film-slug="([^"]+)"', html)
        if not slugs:
            slugs = re.findall(r'href="/film/([^/"]+)/"', html)

        unique_slugs = _deduplicate_slugs(slugs)
        if not unique_slugs:
            logger.warning("No film slugs found on Letterboxd page %d", page)
            consecutive_empty += 1
            if consecutive_empty >= _MAX_EMPTY_CONSECUTIVE:
                logger.info(
                    "Stopping after %d empty consecutive pages",
                    consecutive_empty,
                )
                break
            page += 1
            time.sleep(0.5)
            continue

        consecutive_empty = 0

        slugs_to_fetch = [s for s in unique_slugs if s not in ids_from_list]
        logger.info(
            "Letterboxd page %d: %d slugs (%d from list, %d to fetch)",
            page,
            len(unique_slugs),
            len(ids_from_list),
            len(slugs_to_fetch),
        )

        slug_results = _fetch_ids_for_slugs(slugs_to_fetch)
        _merge_page_results(unique_slugs, ids_from_list, slug_results, ids, seen_ids)

        if not _has_next_page(html):
            break

        if page >= _MAX_PAGES:
            # Silently stopping here used to look like "the list is that
            # short"; say so instead, because the user sees a truncated
            # collection with no hint that more films exist.
            logger.warning(
                "Stopping after %d pages (the safety limit) — the list has "
                "more entries than were fetched",
                _MAX_PAGES,
            )
            break

        page += 1
        time.sleep(0.5)

    return ids
