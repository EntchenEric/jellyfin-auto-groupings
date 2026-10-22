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
import mal
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
