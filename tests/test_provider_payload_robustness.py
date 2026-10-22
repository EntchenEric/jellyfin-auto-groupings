"""Regression tests for malformed provider payloads.

Every fetcher parses a response body written by somebody else. A shape the
fetcher did not expect used to crash with ``AttributeError``/``TypeError``,
and those types were not in the ``except`` tuple at the sync layer, so one bad
upstream payload aborted an entire sync run instead of failing one group.

Each test here pins one such shape and asserts that the fetcher either skips
the unusable data or raises the error type the caller actually handles. The
page-cap tests at the end assert the truncation warning the README promises.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

import anilist
import imdb
import letterboxd
import mal
import sync
import tmdb
import trakt

# --- tmdb.get_tmdb_recommendations ----------------------------------------


def test_recommendation_without_id_is_skipped():
    """A result with no ``id`` must not become the literal id ``"None"``."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"results": [{"title": "no id here"}, {"id": 5}]}

    with patch("tmdb.network.get", return_value=resp):
        recs = tmdb.get_tmdb_recommendations([("1", "movie")], "key")

    assert recs == ["5"]


def test_recommendation_with_boolean_id_is_skipped():
    """``True`` is an ``int``; it must not be sent on as TMDb id ``"True"``."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"results": [{"id": True}, {"id": 7}]}

    with patch("tmdb.network.get", return_value=resp):
        recs = tmdb.get_tmdb_recommendations([("1", "movie")], "key")

    assert recs == ["7"]


def test_recommendation_non_object_payload_is_skipped():
    """A JSON list instead of an object must not raise."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = [{"id": 1}]

    with patch("tmdb.network.get", return_value=resp):
        recs = tmdb.get_tmdb_recommendations([("1", "movie")], "key")

    assert recs == []


def test_recommendation_non_object_entry_is_skipped():
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"results": ["junk", {"id": 8}]}

    with patch("tmdb.network.get", return_value=resp):
        recs = tmdb.get_tmdb_recommendations([("1", "movie")], "key")

    assert recs == ["8"]


# --- tmdb.fetch_tmdb_list -------------------------------------------------


def test_tmdb_list_skips_non_dict_items():
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"items": ["junk", {"id": 10}], "total_pages": 1}

    with patch("tmdb.network.get", return_value=resp):
        ids = tmdb.fetch_tmdb_list("123", "key")

    assert ids == ["10"]


def test_tmdb_collect_skips_missing_and_boolean_ids():
    ids: list[str] = []
    seen: set[str] = set()

    tmdb._collect_tmdb_ids_from_page({"items": "not a list"}, ids, seen)
    assert ids == []

    tmdb._collect_tmdb_ids_from_page(
        {"items": [{"id": None}, {"id": True}, {"id": 0}, {"id": 4}]},
        ids,
        seen,
    )
    assert ids == ["0", "4"]


def test_tmdb_list_keeps_paginating_on_non_integer_total_pages():
    """A malformed ``total_pages`` must not end the walk after page 1."""
    pages = [
        {"items": [{"id": 1}], "total_pages": "lots"},
        {"items": [{"id": 2}], "total_pages": "lots"},
        {"items": [], "total_pages": 1},
    ]

    with patch("tmdb.network.get") as mock_get:
        responses = []
        for payload in pages:
            resp = MagicMock()
            resp.raise_for_status.return_value = None
            resp.json.return_value = payload
            responses.append(resp)
        mock_get.side_effect = responses
        ids = tmdb.fetch_tmdb_list("123", "key")

    assert ids == ["1", "2"]
    assert mock_get.call_count == 3


def test_tmdb_list_rejects_non_object_payload():
    """A bare list body must not escape as ``AttributeError``.

    ``sync.py`` catches ``RuntimeError``/``ValueError`` per group.  An
    ``AttributeError`` from ``data.get`` escaped that handler and aborted the
    whole run instead of failing this one group.
    """
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status.return_value = None
    resp.json.return_value = [{"id": 1}]

    with (
        patch("tmdb.network.get", return_value=resp),
        pytest.raises(RuntimeError, match="Unexpected TMDb API response shape"),
    ):
        tmdb.fetch_tmdb_list("123", "key")


def test_tmdb_list_rejects_invalid_json():
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.side_effect = ValueError("not json")

    with (
        patch("tmdb.network.get", return_value=resp),
        pytest.raises(RuntimeError, match="Invalid JSON response from TMDb"),
    ):
        tmdb.fetch_tmdb_list("123", "key")


@pytest.mark.parametrize(
    ("supplied", "expected"),
    [
        ("8204231", "8204231"),
        ("  8204231  ", "8204231"),
        # Real TMDb list URLs render the name after the ID, so the ID is the
        # segment right after ``/list/`` and not the last one.
        ("https://www.themoviedb.org/list/8204231", "8204231"),
        ("https://www.themoviedb.org/list/8204231/my-list-name", "8204231"),
        ("http://themoviedb.org/list/8204231/", "8204231"),
        ("themoviedb.org/list/8204231", "8204231"),
    ],
)
def test_tmdb_normalizes_real_list_ids(supplied, expected):
    """Bare IDs and genuine TMDb list URLs resolve to the numeric ID."""
    assert tmdb._normalize_tmdb_list_id(supplied) == expected


def test_tmdb_url_with_slug_uses_the_id_not_the_slug():
    """A pasted ``/list/<id>/<slug>`` URL must not send the slug as the ID.

    Taking the last path segment turned every real TMDb list URL into a
    request for a list named after the human-readable slug, which the API
    answers with 404 — so a correctly configured group failed to sync.
    """
    with patch(
        "tmdb._fetch_tmdb_page", return_value={"items": [], "total_pages": 1}
    ) as fetch:
        tmdb.fetch_tmdb_list(
            "https://www.themoviedb.org/list/8204231/my-list-name", "key"
        )

    assert fetch.call_args.args[0] == "8204231"


@pytest.mark.parametrize(
    "supplied",
    [
        "https://evil.example/themoviedb.org/list/123",  # foreign host, path mention
        "https://themoviedb.org.evil.tld/list/1",  # lookalike host
        "https://www.themoviedb.org/list/",  # no ID at all
        "not a list id",
    ],
)
def test_tmdb_rejects_non_tmdb_list_urls(supplied):
    """Only a real TMDb host with a numeric list ID is accepted."""
    with pytest.raises(ValueError, match="Invalid TMDb list"):
        tmdb._normalize_tmdb_list_id(supplied)


@pytest.mark.parametrize("supplied", ["", "   "])
def test_tmdb_blank_list_id_is_reported_as_missing(supplied):
    """A blank ID is "missing", not a URL error; it must not reach the API."""
    with (
        patch("tmdb.network.get") as mock_get,
        pytest.raises(ValueError, match="A TMDb List ID is required"),
    ):
        tmdb.fetch_tmdb_list(supplied, "key")

    assert mock_get.call_count == 0


def test_tmdb_rejected_url_fails_before_any_request():
    """A rejected URL must not reach the network."""
    with (
        patch("tmdb.network.get") as mock_get,
        pytest.raises(ValueError, match="Invalid TMDb list URL"),
    ):
        tmdb.fetch_tmdb_list("https://evil.example/themoviedb.org/list/123", "key")

    assert mock_get.call_count == 0


# --- mal.fetch_mal_list ---------------------------------------------------


def test_mal_list_tolerates_non_object_payload():
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = [{"node": {"id": 1}}]

    with patch("mal.network.get", return_value=resp):
        assert mal.fetch_mal_list("user", "client") == []


def test_mal_list_tolerates_non_dict_entries():
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {
        "data": ["junk", {"node": "not a dict"}, {"node": {"id": 2}}],
        "paging": {},
    }

    with patch("mal.network.get", return_value=resp):
        assert mal.fetch_mal_list("user", "client") == [2]


def test_mal_list_stops_on_non_string_next_url():
    """A numeric/None ``paging.next`` must not be requested as a URL."""
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"data": [{"node": {"id": 1}}], "paging": {"next": 42}}

    with patch("mal.network.get", return_value=resp) as mock_get:
        assert mal.fetch_mal_list("user", "client") == [1]

    assert mock_get.call_count == 1


# --- anilist --------------------------------------------------------------


def test_anilist_invalid_json_raises_runtime_error():
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.side_effect = ValueError("not json")

    with (
        patch("anilist.network.post", return_value=resp),
        pytest.raises(RuntimeError, match="Invalid JSON response from AniList"),
    ):
        anilist.fetch_anilist_list("user")


def test_anilist_skips_boolean_media_ids():
    payload = {
        "data": {
            "MediaListCollection": {
                "lists": [
                    {"entries": [{"mediaId": True}, {"mediaId": 99}]},
                    "junk",
                ]
            }
        }
    }

    assert anilist._extract_media_ids(payload) == [99]


def test_anilist_tolerates_non_list_lists_field():
    payload = {"data": {"MediaListCollection": {"lists": "junk"}}}

    assert anilist._extract_media_ids(payload) == []


def test_anilist_tolerates_non_object_data_and_collection():
    assert anilist._extract_media_ids({"data": "junk"}) == []
    assert anilist._extract_media_ids({"data": {"MediaListCollection": []}}) == []


def test_anilist_rejects_non_object_payload():
    """A bare list body must not escape as ``AttributeError``."""
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = [{"mediaId": 1}]

    with (
        patch("anilist.network.post", return_value=resp),
        pytest.raises(RuntimeError, match="Unexpected AniList API response shape"),
    ):
        anilist.fetch_anilist_list("user")


def test_malformed_provider_body_fails_one_group_only(tmp_path):
    """A bad TMDb body must not take the rest of the run down with it."""
    config = {
        "jellyfin_url": "http://jellyfin.invalid",
        "api_key": "key",
        "target_path": str(tmp_path / "virtual"),
        "tmdb_api_key": "tmdb-key",
        "groups": [
            {
                "name": "Broken",
                "source_type": "tmdb_list",
                "source_value": "1",
                "sort_order": "SortName",
            },
            {
                "name": "Empty",
                "source_type": "tmdb_list",
                "source_value": "2",
                "sort_order": "SortName",
            },
        ],
    }

    with patch(
        "sync.fetch_tmdb_list",
        side_effect=[
            RuntimeError(
                "Unexpected TMDb API response shape for list '1': "
                "expected a JSON object, got list"
            ),
            [],
        ],
    ):
        results = sync.run_sync(config, dry_run=True)

    assert results[0]["group"] == "Broken"
    assert "Unexpected TMDb API response shape" in results[0]["error"]
    assert results[1]["group"] == "Empty"
    assert "error" not in results[1]


def test_anilist_skips_non_dict_entries_and_lists():
    payload = {
        "data": {
            "MediaListCollection": {
                "lists": [
                    {"entries": ["junk", {"mediaId": 3}]},
                    {"entries": "not a list"},
                ]
            }
        }
    }

    assert anilist._extract_media_ids(payload) == [3]


def test_anilist_rejects_unknown_status():
    with pytest.raises(ValueError, match="Unknown AniList status"):
        anilist.fetch_anilist_list("user", status="nonsense")


def test_anilist_sends_normalized_status_and_custom_url():
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"data": {"MediaListCollection": {"lists": []}}}

    with patch("anilist.network.post", return_value=resp) as mock_post:
        anilist.fetch_anilist_list(
            "user",
            status="watching",
            api_url="https://anilist.example/graphql",
        )

    args, kwargs = mock_post.call_args
    assert args[0] == "https://anilist.example/graphql"
    assert kwargs["json"]["variables"] == {
        "userName": "user",
        "status": "CURRENT",
    }


def test_anilist_request_error_raises_runtime_error():
    with (
        patch("anilist.network.post", side_effect=requests.RequestException("boom")),
        pytest.raises(RuntimeError, match="Failed to fetch AniList list"),
    ):
        anilist.fetch_anilist_list("user")


# --- trakt ----------------------------------------------------------------


def test_trakt_wrong_shape_raises_handled_error_type():
    """``TypeError`` escaped sync.py's handler; it must surface as RuntimeError."""
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.headers = {}
    resp.json.return_value = {"error": "not a list"}

    with (
        patch("trakt.network.get", return_value=resp),
        pytest.raises(RuntimeError, match="Unexpected Trakt API response"),
    ):
        trakt.fetch_trakt_list("user/list-slug", "client")


def test_trakt_total_pages_header_fallback():
    """A non-numeric page-count header must not fail the page fetch."""
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.headers = {"X-Pagination-Page-Count": "many"}
    resp.json.return_value = [{"type": "movie", "movie": {"ids": {"imdb": "tt1"}}}]

    with patch("trakt.network.get", return_value=resp):
        items, total_pages = trakt._fetch_trakt_page("u", "s", 1, {})

    assert total_pages == 1
    assert len(items) == 1


def test_trakt_skips_unhashable_imdb_id():
    """A non-string IMDb id raised ``TypeError: unhashable type`` out of the fetch.

    ``imdb_id not in seen`` runs before any type check, so an object or a list
    in ``ids.imdb`` propagated as ``TypeError``, which ``_fetch_and_resolve``
    does not catch — one malformed entry aborted the entire sync run.
    """
    ids: list[str] = []
    seen: set[str] = set()

    trakt._extract_imdb_ids_from_page(
        [
            {"type": "movie", "movie": {"ids": {"imdb": {"bad": 1}}}},
            {"type": "movie", "movie": {"ids": {"imdb": ["tt0"]}}},
            {"type": "movie", "movie": {"ids": {"imdb": 12345}}},
            {"type": "movie", "movie": {"ids": {"imdb": "  tt0111161  "}}},
        ],
        ids,
        seen,
    )

    assert ids == ["tt0111161"]


def test_trakt_unhashable_imdb_id_does_not_abort_group():
    """The group reports no error, and the sync run continues."""
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.headers = {}
    resp.json.return_value = [
        {"type": "movie", "movie": {"ids": {"imdb": {"bad": 1}}}},
        {"type": "movie", "movie": {"ids": {"imdb": "tt1"}}},
    ]

    with (
        patch("trakt.network.get", return_value=resp),
        patch("sync._fetch_full_library", return_value=([], None, 200)),
    ):
        items, error, status = sync._fetch_items_for_trakt_group(
            "g",
            "https://trakt.tv/users/a/lists/b",
            "SortName",
            "http://jellyfin.invalid",
            "key",
            "client",
        )

    assert error is None
    assert status == 200
    assert items == []


def test_tmdb_skips_object_and_list_ids():
    """A non-scalar ``id`` must not become the provider id ``"{'a': 1}"``."""
    ids: list[str] = []
    seen: set[str] = set()

    tmdb._collect_tmdb_ids_from_page(
        {"items": [{"id": {"a": 1}}, {"id": [1]}, {"id": 7}, {"id": "8"}]},
        ids,
        seen,
    )

    assert ids == ["7", "8"]


# --- imdb -----------------------------------------------------------------


def test_imdb_rejects_prefix_only_list_id():
    """``ls`` alone is not a list id and must not be requested."""
    with (
        patch("imdb.network.get") as mock_get,
        pytest.raises(ValueError, match="Invalid IMDb list ID"),
    ):
        imdb.fetch_imdb_list("ls")

    assert mock_get.call_count == 0


def test_imdb_rejects_non_numeric_list_id():
    with (
        patch("imdb.network.get") as mock_get,
        pytest.raises(ValueError, match="Invalid IMDb list ID"),
    ):
        imdb.fetch_imdb_list("lsabc")

    assert mock_get.call_count == 0


def test_imdb_warns_when_page_cap_truncates(caplog):
    """Hitting the cap is reported, so a truncated list is not silent."""
    endless = '<a class="next-page" href="/list/ls1/?page=2">Next</a>'

    with (
        patch("imdb.network.get") as mock_get,
        caplog.at_level("WARNING", logger="imdb"),
    ):
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.text = f'<a href="/title/tt0000001/"></a>{endless}'
        mock_get.return_value = resp

        ids = imdb.fetch_imdb_list("ls1")

    assert ids == ["tt0000001"]
    assert mock_get.call_count == imdb._MAX_PAGES
    assert "safety limit" in caplog.text


def test_imdb_http_error_raises_runtime_error():
    with (
        patch("imdb.network.get", side_effect=requests.RequestException("boom")),
        pytest.raises(RuntimeError, match="Failed to fetch IMDb list page 1"),
    ):
        imdb.fetch_imdb_list("ls1")


def test_trakt_page_cap_logs_warning(caplog):
    """Hitting the Trakt page cap must be reported, not silent."""
    page_items = [{"type": "movie", "movie": {"ids": {"imdb": "tt1"}}}]

    with (
        patch("trakt._fetch_trakt_page", return_value=(page_items, 9_999)),
        caplog.at_level("WARNING", logger="trakt"),
    ):
        ids = trakt.fetch_trakt_list("user/list-slug", "client")

    assert ids == ["tt1"]
    assert "safety limit" in caplog.text


def test_tmdb_page_cap_logs_warning(caplog):
    """Hitting the TMDb page cap must be reported, not silent."""
    with (
        patch(
            "tmdb._fetch_tmdb_page",
            return_value={"items": [{"id": 1}], "total_pages": 9_999},
        ),
        caplog.at_level("WARNING", logger="tmdb"),
    ):
        ids = tmdb.fetch_tmdb_list("123", "key")

    assert ids == ["1"]
    assert "safety limit" in caplog.text


# --- user-supplied list identifiers ---------------------------------------
# A list identifier comes from a group's ``value`` in ``config.json``. It is
# pasted into a request URL, so it has to be recognised exactly: a fuzzy match
# turns a typo into a request for some other list, and a substring host check
# lets a non-Letterboxd host be fetched on the server's behalf.


@pytest.mark.parametrize(
    ("supplied", "expected"),
    [
        ("ls000024390", "ls000024390"),
        ("  ls000024390  ", "ls000024390"),
        ("https://www.imdb.com/list/ls000024390/", "ls000024390"),
        ("https://www.imdb.com/list/ls000024390/?sort=list_order,asc", "ls000024390"),
        ("imdb.com/list/ls000024390", "ls000024390"),
    ],
)
def test_imdb_accepts_real_list_ids(supplied, expected):
    """Bare IDs and genuine IMDb list URLs resolve to the bare ID."""
    assert imdb._normalize_list_id(supplied) == expected


@pytest.mark.parametrize(
    "supplied",
    [
        "ls123abc",  # trailing junk would be truncated to ls123
        "garbage-ls123",  # an unanchored search found ls123 anywhere
        "https://evil.example/list/ls999/",  # ID on a non-IMDb host
        "ls",
        "",
    ],
)
def test_imdb_rejects_ids_it_would_have_guessed(supplied):
    """Anything that is not an exact ID or IMDb URL is refused.

    The old parsing searched the whole input for ``ls\\d+``, so ``"ls123abc"``
    became ``ls123`` and the sync fetched a *different* list than the one the
    user named.
    """
    with pytest.raises(ValueError, match="Invalid IMDb list ID"):
        imdb._normalize_list_id(supplied)


def test_imdb_rejects_mangled_id_before_any_request():
    """A rejected ID must not reach the network."""
    with (
        patch("imdb.network.get") as mock_get,
        pytest.raises(ValueError, match="Invalid IMDb list ID"),
    ):
        imdb.fetch_imdb_list("garbage-ls123")

    assert mock_get.call_count == 0


@pytest.mark.parametrize(
    "supplied",
    [
        "https://evil.example/?r=letterboxd.com",  # substring match passed before
        "https://letterboxd.com.evil.tld/u/list/x/",  # lookalike host
        "letterboxd.comevil/u/list/x",  # suffix without a dot boundary
        "/u/list/x",
        "",
    ],
)
def test_letterboxd_rejects_non_letterboxd_hosts(supplied):
    """Only a real Letterboxd host may be fetched.

    The old check was ``"letterboxd.com" in list_url``, so a URL on any host
    that merely mentioned Letterboxd in its query string was requested by the
    server — a request-forgery primitive driven by config.
    """
    with pytest.raises(ValueError, match="Invalid Letterboxd URL"):
        letterboxd._validate_list_url(supplied)


def test_letterboxd_rejects_foreign_host_before_any_request():
    """A foreign host must be refused without a single HTTP call."""
    with (
        patch("letterboxd.network.get") as mock_get,
        pytest.raises(ValueError, match="Invalid Letterboxd URL"),
    ):
        letterboxd.fetch_letterboxd_list("https://evil.example/?next=letterboxd.com")

    assert mock_get.call_count == 0


@pytest.mark.parametrize(
    ("supplied", "expected"),
    [
        ("https://letterboxd.com/u/list/x/", "https://letterboxd.com/u/list/x"),
        ("https://www.letterboxd.com/u/list/x", "https://www.letterboxd.com/u/list/x"),
        ("letterboxd.com/u/list/x", "https://letterboxd.com/u/list/x"),
    ],
)
def test_letterboxd_accepts_real_list_urls(supplied, expected):
    """Real Letterboxd URLs and scheme-less input keep working."""
    assert letterboxd._validate_list_url(supplied) == expected


# --- Trakt list identifiers ----------------------------------------------
# The Trakt parse searched the raw input for ``trakt.tv/users/…``, so a URL
# on an unrelated host that merely mentioned that path (in a query string)
# was accepted and its username/slug were then fetched from the Trakt API.


@pytest.mark.parametrize(
    ("supplied", "expected"),
    [
        (
            "https://trakt.tv/users/jane/lists/my-list",
            ("jane", "my-list"),
        ),
        (
            "https://www.trakt.tv/users/jane/lists/my-list/",
            ("jane", "my-list"),
        ),
        # Pasted from a chat client as Markdown link syntax.
        (
            "[my list](https://trakt.tv/users/jane/lists/my-list)",
            ("jane", "my-list"),
        ),
        # Scheme-less URL keeps working.
        ("trakt.tv/users/jane/lists/my-list", ("jane", "my-list")),
        # Shorthand, including a username with a dot.
        ("jane/my-list", ("jane", "my-list")),
        ("jane.doe/my-list", ("jane.doe", "my-list")),
    ],
)
def test_trakt_accepts_real_list_references(supplied, expected):
    assert trakt._parse_trakt_list_url(supplied) == expected


@pytest.mark.parametrize(
    "supplied",
    [
        "https://evil.example/?u=trakt.tv/users/jane/lists/my-list",
        "https://trakt.tv.evil.tld/users/jane/lists/my-list",
        "not-trakt.tv/users/jane/lists/my-list",
        "https://trakt.tv/users/jane/lists/",
        "",
        "invalid-url",
    ],
)
def test_trakt_rejects_references_that_name_no_trakt_list(supplied):
    """A non-Trakt host or a path-less URL is refused, not guessed at."""
    with pytest.raises(ValueError, match="Invalid Trakt list URL"):
        trakt._parse_trakt_list_url(supplied)


def test_trakt_rejected_reference_fails_before_any_request():
    """A rejected reference must not reach the network."""
    with (
        patch("trakt.network.get") as mock_get,
        pytest.raises(ValueError, match="Invalid Trakt list URL"),
    ):
        trakt.fetch_trakt_list(
            "https://evil.example/?u=trakt.tv/users/jane/lists/my-list",
            "client_id",
        )

    assert mock_get.call_count == 0
