"""Tests for external metadata providers (Anilist, Trakt, Mal, TMDB, Letterboxd, IMDB)."""
from unittest.mock import MagicMock, patch

import pytest

import anilist
import mal
import trakt


def test_anilist_fetch():
    with patch("anilist.network.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": {
                "MediaListCollection": {
                    "lists": [
                        {
                            "name": "Completed",
                            "entries": [{"mediaId": 12345}]
                        }
                    ]
                }
            }
        }
        mock_post.return_value = mock_resp
        res = anilist.fetch_anilist_list("testuser")
        assert res == [12345]

def test_trakt_get_headers():
    headers = trakt._build_trakt_headers("test_client_id")
    assert headers.get("trakt-api-key") == "test_client_id"

def test_mal_fetch():
    with patch("mal.network.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": [{"node": {"id": 1, "title": "Test Anime"}}],
            "paging": {}
        }
        mock_get.return_value = mock_resp
        res = mal.fetch_mal_list("testuser", "test_client_id")
        assert res == [1]

# --- _common.py tests ---
import _common


def test_normalize_group_relpath():
    assert _common.normalize_group_relpath("Anime/Action") == "Anime/Action"
    assert _common.normalize_group_relpath("  Anime // Action  ") == "Anime/Action"
    assert _common.normalize_group_relpath("Anime\\Action") == "Anime/Action"
    assert _common.normalize_group_relpath("../outside") is None
    assert _common.normalize_group_relpath(".") is None
    assert _common.normalize_group_relpath("C:\\Windows\\System32") is None
    assert _common.normalize_group_relpath("") is None
    assert _common.normalize_group_relpath(None) is None
    assert _common.normalize_group_relpath("Test\x00Null") is None

# --- tmdb.py tests ---
import tmdb


def test_tmdb_fetch_list():
    with patch("tmdb.network.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "items": [{"id": 101}, {"id": 102}],
            "total_pages": 1
        }
        mock_get.return_value = mock_resp
        ids = tmdb.fetch_tmdb_list("12345", "fake_api_key")
        assert ids == ["101", "102"]

def test_tmdb_fetch_list_validation():
    with pytest.raises(ValueError):
        tmdb.fetch_tmdb_list("12345", "")
    with pytest.raises(ValueError):
        tmdb.fetch_tmdb_list("", "fake_key")

def test_tmdb_recommendations():
    with patch("tmdb.network.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": [{"id": 201}, {"id": 202}]
        }
        mock_get.return_value = mock_resp
        recs = tmdb.get_tmdb_recommendations([("101", "movie")], "fake_api_key")
        assert recs == ["201", "202"]

# --- imdb.py tests ---
import imdb


def test_imdb_fetch_list():
    with patch("imdb.network.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '<html><a href="/title/tt1234567/">Movie</a></html>'
        mock_get.return_value = mock_resp
        ids = imdb.fetch_imdb_list("ls0000000")
        assert ids == ["tt1234567"]

def test_imdb_fetch_list_invalid():
    with pytest.raises(ValueError):
        imdb.fetch_imdb_list("")

# --- letterboxd.py tests ---
import letterboxd


def test_letterboxd_fetch_list():
    with patch("letterboxd.network.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '<html><div data-film-slug="test-movie"></div></html>'
        mock_get.return_value = mock_resp
        res = letterboxd.fetch_letterboxd_list("https://letterboxd.com/user/list/test-list/")
        assert res == ["test-movie"]

