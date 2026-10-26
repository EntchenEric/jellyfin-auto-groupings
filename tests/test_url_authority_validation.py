"""Regression tests for outbound URL authority validation.

Every list fetcher turns a group's ``value`` from ``config.json`` into an
outbound HTTP request, so the identifier is attacker-influenced input that
reaches ``requests``. A host allow-list is only as strong as the parser behind
it, and the two parsers involved disagree on a few authorities:

``urllib.parse.urlparse`` treats everything before the *last* ``@`` as
userinfo, so ``https://evil.example\\@letterboxd.com/u/list/x`` reports the
host ``letterboxd.com``. ``requests``/``urllib3`` end the authority at the
backslash and connect to ``evil.example``. Validating with ``urlparse`` alone
therefore accepted any host when it was prefixed with
``https://<host>\\@`` and the server then made the request on the caller's
behalf — a server-side request forgery primitive driven by config.

The validators now compare both parsers and reject an ambiguous authority.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

import imdb
import letterboxd
import tmdb
import trakt
from _common import (
    _authority_host,
    host_matches,
    parse_outbound_url,
    split_outbound_url,
)

#: Hosts whose apparent authority differs between ``urlparse`` and the HTTP
#: client. Each one would be fetched from ``evil.example``.
_AMBIGUOUS_AUTHORITIES = (
    "https://evil.example\\@letterboxd.com/u/list/x",
    "https://evil.example\\@imdb.com/list/ls000024390/",
    "https://evil.example\\@www.themoviedb.org/list/8204231",
    "https://evil.example\\@trakt.tv/users/jane/lists/my-list",
)


# --- the shared helpers ---------------------------------------------------


@pytest.mark.parametrize("supplied", _AMBIGUOUS_AUTHORITIES)
def test_backslash_before_at_sign_is_ambiguous(supplied):
    """`urlparse` and the HTTP client must agree before a URL is trusted."""
    assert _authority_host(supplied) is None
    assert parse_outbound_url(supplied) is None
    assert split_outbound_url(supplied) is None


@pytest.mark.parametrize(
    "supplied",
    [
        "https://letterboxd.com/u/list/x",
        "https://www.imdb.com/list/ls000024390/",
        "https://www.themoviedb.org/list/8204231",
    ],
)
def test_agreeing_authorities_are_accepted(supplied):
    """A URL both parsers agree on still resolves to scheme, host and path."""
    split = split_outbound_url(supplied)
    assert split is not None
    base, host = split
    assert base.startswith("https://")
    assert host == base.removeprefix("https://").split("/")[0]


def test_parse_outbound_url_drops_query_fragment_and_trailing_slash():
    """Only the path names the list; page segments are appended later."""
    assert (
        parse_outbound_url("https://letterboxd.com/u/list/x/?utm=1#top")
        == "https://letterboxd.com/u/list/x"
    )


def test_parse_outbound_url_rejects_embedded_credentials():
    """Credentials would be forwarded to the fetched host; list URLs need none."""
    assert parse_outbound_url("https://user:secret@letterboxd.com/u/list/x") is None


@pytest.mark.parametrize(
    "supplied",
    ["javascript:alert(1)", "file:///etc/passwd", "ftp://letterboxd.com/x", ""],
)
def test_parse_outbound_url_rejects_non_http_schemes(supplied):
    assert parse_outbound_url(supplied) is None


def test_host_matches_requires_a_dot_boundary_for_subdomains():
    """A lookalike suffix must not pass for the apex host."""
    allowed = frozenset({"letterboxd.com"})
    assert host_matches("letterboxd.com", allowed, allow_subdomains=True)
    assert host_matches("www.letterboxd.com", allowed, allow_subdomains=True)
    assert not host_matches("letterboxd.com.evil.tld", allowed, allow_subdomains=True)
    assert not host_matches("notletterboxd.com", allowed, allow_subdomains=True)
    assert not host_matches("www.letterboxd.com", allowed, allow_subdomains=False)


# --- the validators ------------------------------------------------------


@pytest.mark.parametrize(
    "supplied",
    [
        "https://evil.example\\@letterboxd.com/u/list/x",
        "https://letterboxd.com.evil.tld/u/list/x",
        "https://user:pass@letterboxd.com/u/list/x",
    ],
)
def test_letterboxd_rejects_ambiguous_or_lookalike_authorities(supplied):
    with pytest.raises(ValueError, match="Invalid Letterboxd URL"):
        letterboxd._validate_list_url(supplied)


@pytest.mark.parametrize(
    "supplied",
    [
        "https://evil.example\\@imdb.com/list/ls000024390/",
        "https://imdb.com.evil.tld/list/ls000024390/",
        "https://user:pass@imdb.com/list/ls000024390/",
    ],
)
def test_imdb_rejects_ambiguous_or_lookalike_authorities(supplied):
    with pytest.raises(ValueError, match="Invalid IMDb list ID"):
        imdb._normalize_list_id(supplied)


@pytest.mark.parametrize(
    "supplied",
    [
        "https://evil.example\\@www.themoviedb.org/list/8204231",
        "https://www.themoviedb.org.evil.tld/list/8204231",
        "https://user:pass@www.themoviedb.org/list/8204231",
    ],
)
def test_tmdb_rejects_ambiguous_or_lookalike_authorities(supplied):
    with pytest.raises(ValueError, match="Invalid TMDb list URL"):
        tmdb._normalize_tmdb_list_id(supplied)


def test_letterboxd_bypass_fails_before_any_request():
    """The whole point: no HTTP call may happen for a foreign authority."""
    with (
        patch("letterboxd.network.get") as mock_get,
        pytest.raises(ValueError, match="Invalid Letterboxd URL"),
    ):
        letterboxd.fetch_letterboxd_list(
            "https://evil.example\\@letterboxd.com/u/list/x",
        )

    assert mock_get.call_count == 0


def test_imdb_bypass_fails_before_any_request():
    with (
        patch("imdb.network.get") as mock_get,
        pytest.raises(ValueError, match="Invalid IMDb list ID"),
    ):
        imdb.fetch_imdb_list("https://evil.example\\@imdb.com/list/ls000024390/")

    assert mock_get.call_count == 0


@pytest.mark.parametrize(
    "supplied",
    [
        "https://evil.example\\@trakt.tv/users/jane/lists/my-list",
        "https://trakt.tv.evil.tld/users/jane/lists/my-list",
        "https://user:pass@trakt.tv/users/jane/lists/my-list",
    ],
)
def test_trakt_rejects_ambiguous_or_lookalike_authorities(supplied):
    with pytest.raises(ValueError, match="Invalid Trakt list URL"):
        trakt._parse_trakt_list_url(supplied)


@pytest.mark.parametrize(
    ("supplied", "expected"),
    [
        ("https://trakt.tv/users/jane/lists/my-list", ("jane", "my-list")),
        ("trakt.tv/users/jane/lists/my-list", ("jane", "my-list")),
        ("jane/my-list", ("jane", "my-list")),
    ],
)
def test_trakt_accepts_real_references(supplied, expected):
    """The stricter host check must not reject genuine Trakt references."""
    assert trakt._parse_trakt_list_url(supplied) == expected
