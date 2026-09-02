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
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
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


# ---------------------------------------------------------------------------
# Group names / nested folder paths
# ---------------------------------------------------------------------------


def normalize_group_relpath(name: str) -> str | None:
    """Normalise a group name into a safe *relative* folder path.

    A group name may describe a nested location by separating levels with
    ``/`` (or ``\\`` on Windows-style input), e.g. ``"Anime/Action"`` creates
    ``<target>/Anime/Action``. This lets users build a browsable folder tree
    in Jellyfin instead of a flat list of libraries.

    Every segment is stripped of surrounding whitespace, and empty segments
    are dropped so ``"Anime//Action"`` and ``"Anime/ Action "`` normalise to
    ``"Anime/Action"``.

    The result is always relative and always stays inside the target
    directory: absolute paths, ``.``/``..`` segments and NUL bytes are
    rejected outright rather than sanitised, so a malformed name can never
    be silently turned into a path that escapes the base directory.

    Windows drive-letter absolute paths (e.g. ``"C:\\foo"`` or
    ``"C:/foo"``) are also rejected: after normalising separators they would
    otherwise be treated as a *relative* path rooted at a literal ``"C:"``
    segment, silently creating a confusing ``C:`` folder inside the target
    directory instead of the intended location.

    Args:
        name: The raw group name.

    Returns:
        The normalised relative path using ``/`` separators, or ``None`` if
        *name* is not a valid, safe group name.

    """
    if not isinstance(name, str) or "\x00" in name:
        return None

    segments = [seg.strip() for seg in name.replace("\\", "/").split("/")]
    cleaned = [seg for seg in segments if seg]

    if not cleaned:
        return None
    if any(seg in (".", "..") for seg in cleaned):
        return None
    # A leading single-letter drive segment (e.g. ``"C:"``) followed by more
    # segments is a Windows absolute path (``"C:\\foo"`` / ``"C:/foo"``).
    # Reject it so it can't be misread as a relative ``C:`` folder.  A bare
    # ``"C:"`` alone is left alone (ambiguous, harmless on POSIX), and
    # names like ``"a:b"`` (a colon inside a single segment) are unaffected.
    if (
        len(cleaned) > 1
        and len(cleaned[0]) == 2
        and cleaned[0][1] == ":"
        and cleaned[0][0].isalpha()
    ):
        return None

    return "/".join(cleaned)
