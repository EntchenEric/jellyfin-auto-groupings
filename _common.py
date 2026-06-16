"""_common.py - Shared constants and utilities for Jellyfin Groupings.

This module holds constants and helpers that are referenced by multiple
other modules, reducing duplication and centralising common definitions.
"""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Source types
# ---------------------------------------------------------------------------

#: All valid group source types.
SOURCE_TYPES: frozenset[str] = frozenset(
    {
        "genre",
        "studio",
        "tag",
        "year",
        "actor",
        "general",
        "complex",
        "imdb_list",
        "trakt_list",
        "tmdb_list",
        "anilist_list",
        "mal_list",
        "letterboxd_list",
        "recommendations",
    },
)

#: Source types that use external list fetchers (not Jellyfin metadata filters).
LIST_SOURCE_TYPES: frozenset[str] = frozenset(
    {
        "imdb_list",
        "trakt_list",
        "tmdb_list",
        "anilist_list",
        "mal_list",
        "letterboxd_list",
        "recommendations",
    },
)

#: Metadata source types that can contain complex queries.
COMPLEX_QUERY_SOURCE_TYPES: frozenset[str] = frozenset(
    {
        "genre",
        "actor",
        "studio",
        "tag",
        "year",
    },
)

# ---------------------------------------------------------------------------
# HTTP request headers
# ---------------------------------------------------------------------------

#: Default browser-like headers used when scraping non-API web pages
#: (e.g. IMDb and Letterboxd).
DEFAULT_SCRAPING_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# ---------------------------------------------------------------------------
# Default filesystem search roots
# ---------------------------------------------------------------------------

#: Default directory roots the file-browser endpoint is allowed to explore.
DEFAULT_SEARCH_ROOTS: tuple[str, ...] = (
    str(Path.home()),
    "/media",
    "/mnt",
)

# ---------------------------------------------------------------------------
# Network / timeout defaults
# ---------------------------------------------------------------------------

#: Default timeout for external list-fetcher HTTP requests (seconds).
DEFAULT_LIST_FETCH_TIMEOUT: int = 15

#: Maximum number of pages to fetch from paginated list endpoints.
DEFAULT_LIST_MAX_PAGES: int = 50

#: Default page size for paginated API calls.
DEFAULT_LIST_PAGE_LIMIT: int = 1_000
