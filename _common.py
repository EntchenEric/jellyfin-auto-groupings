"""_common.py - Shared constants and utilities for Jellyfin Groupings.

This module holds constants and helpers that are referenced by multiple
other modules, reducing duplication and centralising common definitions.
"""

from __future__ import annotations

import calendar
import re
from pathlib import Path
from urllib.parse import urlparse

from urllib3.util import parse_url as _urllib3_parse_url

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


#: Shape of a seasonal ``MM-DD`` value, checked before the day is validated
#: against the month. February is allowed 29 days so a leap-year rule is not
#: rejected in non-leap years.
_MMDD_RE: re.Pattern[str] = re.compile(r"^(\d{2})-(\d{2})$")


def is_valid_mmdd(value: object) -> bool:
    """Return whether *value* is an ``MM-DD`` date that exists on a calendar.

    A shape-only check accepts ``"02-31"``, ``"04-31"``, and ``"02-30"``.
    Those are not real dates: :func:`sync._parse_mmdd` rejects them, and
    :func:`sync._is_in_season` then treats a malformed window as "always in
    season", so a seasonal group whose dates were never validated can never
    be cleaned up at the end of its season. Validating the month/day
    combination here catches the typo while the user is still on the form.

    February 29 is accepted unconditionally; the seasonal check compares only
    month and day, so a Feb-29 boundary is meaningful without knowing the
    year.

    Args:
        value: The candidate value, usually straight from ``config.json`` or a
            request body, so any JSON type may arrive.

    Returns:
        ``True`` only for a string of the form ``MM-DD`` naming a day that
        exists in that month.

    """
    if not isinstance(value, str):
        return False
    match = _MMDD_RE.match(value.strip())
    if match is None:
        return False
    month, day = int(match.group(1)), int(match.group(2))
    if not 1 <= month <= 12:
        return False
    # Leap year so February 29 is valid regardless of the current year.
    _, days_in_month = calendar.monthrange(2024, month)
    return 1 <= day <= days_in_month


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
    directory: ``.``/``..`` segments and NUL bytes are rejected outright
    rather than sanitised, so a malformed name can never be silently turned
    into a path that escapes the base directory. A leading ``/`` (or ``\\``)
    is dropped along with any other empty segment, so ``"/etc/passwd"``
    becomes the relative ``"etc/passwd"`` inside the target directory rather
    than being rejected — it names a nested folder there, never the absolute
    path it resembles.

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
    #
    # Windows drive letters are strictly ASCII ``[A-Za-z]``, so a non-ASCII
    # letter (e.g. ``"Ä:"``) is *not* a drive path and must remain a valid
    # relative name.
    if (
        len(cleaned) > 1
        and len(cleaned[0]) == 2
        and cleaned[0][1] == ":"
        and cleaned[0][0].isascii()
        and cleaned[0][0].isalpha()
    ):
        return None

    return "/".join(cleaned)


# ---------------------------------------------------------------------------
# Outbound URL validation
# ---------------------------------------------------------------------------


def _authority_host(candidate: str) -> str | None:
    """Return the host that an HTTP client would actually connect to.

    ``urllib.parse.urlparse`` does not follow RFC 3986 for the authority
    component: everything before the *last* ``@`` is treated as userinfo, so
    ``https://evil.example\\@letterboxd.com/u/list/x`` reports
    ``letterboxd.com``. ``requests``/``urllib3`` treat a backslash as the end
    of the authority, so the same URL is actually fetched from
    ``evil.example``. Validating with ``urlparse`` therefore let any host
    through by prefixing it with ``https://<host>\\@``, and the fetchers
    then made a request to an attacker-chosen server -- a server-side request
    forgery primitive reachable from a group's ``value`` in ``config.json``.

    Both parsers are consulted and the answer is only accepted when they
    agree. A URL the two disagree about is ambiguous by definition, so it is
    rejected rather than guessed at.

    Args:
        candidate: The URL to inspect.

    Returns:
        The lowercased host, or ``None`` when the two parsers disagree or
        either one finds no usable host.

    """
    stdlib_host = (urlparse(candidate).hostname or "").lower()
    # urllib3 is the parser that ``requests`` ultimately connects with, so
    # its answer is the one that matters. A lookup failure must mean
    # "reject", not crash.
    try:
        client_host = (_urllib3_parse_url(candidate).host or "").lower()
    except (ValueError, TypeError):
        return None
    if not stdlib_host or not client_host or stdlib_host != client_host:
        return None
    return client_host


def parse_outbound_url(candidate: str) -> str | None:
    """Return the canonical base URL of a user-supplied list URL, or ``None``.

    Shared by the list fetchers so every one of them validates the host the
    same way. The returned URL carries only scheme, host, and path: a pasted
    browser URL routinely has a query string, a fragment, and an explicit
    page segment, and only the path names the list.

    Args:
        candidate: The raw URL from config.

    Returns:
        ``"<scheme>://<netloc><path>"`` with any trailing slash removed, or
        ``None`` when the input is not an ``http(s)`` URL with an unambiguous
        host or carries userinfo.

    """
    if not isinstance(candidate, str):
        return None
    cleaned = candidate.strip()
    if not cleaned:
        return None
    # Tolerate a scheme-less input such as ``letterboxd.com/user/list/x``:
    # ``requests`` needs a scheme, and ``urlparse`` reports an empty host
    # without one. A protocol-relative ``//host/path`` gets the same
    # treatment; both are pasted from a browser address bar.
    if cleaned.startswith("//"):
        cleaned = f"https:{cleaned}"
    elif "//" not in cleaned:
        cleaned = f"https://{cleaned}"

    parsed = urlparse(cleaned)
    if parsed.scheme.lower() not in ("http", "https"):
        return None
    if _authority_host(cleaned) is None:
        return None
    # Credentials in the URL would be forwarded to the fetched host, and they
    # also make the authority ambiguous; list URLs never need them.
    if parsed.username or parsed.password:
        return None
    path = parsed.path.rstrip("/")
    # Hosts are case-insensitive, so the canonical form is lowercased. That
    # keeps two spellings of the same list from becoming two distinct
    # fetches, and lets callers compare hosts without normalising again.
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{path}"


def host_matches(host: str, allowed: frozenset[str], *, allow_subdomains: bool) -> bool:
    """Return whether *host* is one of *allowed* (or one of their subdomains).

    The suffix check is anchored on a ``.`` boundary so ``letterboxd.com.evil``
    and ``letterboxdevil.com`` cannot masquerade as ``letterboxd.com``.

    Args:
        host: The lowercased host from :func:`_authority_host`.
        allowed: The accepted apex hosts.
        allow_subdomains: Whether ``<something>.<apex>`` is also accepted.

    Returns:
        ``True`` when the host is acceptable.

    """
    if host in allowed:
        return True
    if not allow_subdomains:
        return False
    return any(host.endswith(f".{apex}") for apex in allowed)


def split_outbound_url(candidate: str) -> tuple[str, str] | None:
    """Return ``(base_url, host)`` for a user-supplied list URL, or ``None``.

    Combines :func:`parse_outbound_url` and :func:`_authority_host` so a
    caller validating a list URL gets the host that will really be contacted
    without re-parsing the canonical URL.

    Args:
        candidate: The raw URL from config.

    Returns:
        The canonical base URL and its lowercased host, or ``None`` when the
        input is unusable.

    """
    base = parse_outbound_url(candidate)
    if base is None:
        return None
    # ``base`` carries no userinfo, so both parsers agree on its host.
    host = _authority_host(base)
    if host is None:
        return None
    return base, host
