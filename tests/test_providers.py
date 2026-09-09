"""Tests for external metadata providers (Anilist, Trakt, Mal, TMDB, Letterboxd, IMDB)."""
import pytest
from unittest.mock import patch, MagicMock
import anilist
import trakt
import mal

def test_anilist_fetch():
    with patch("anilist.requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": {
                "Media": {
                    "id": 12345,
                    "title": {"romaji": "Test Anime"}
                }
            }
        }
        mock_post.return_value = mock_resp
        res = anilist.get_anilist_data(12345)
        assert res is not None

def test_trakt_get_headers():
    headers = trakt.get_trakt_headers("test_client_id")
    assert headers.get("trakt-api-key") == "test_client_id"

def test_mal_fetch():
    with patch("mal.requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": 1, "title": "Test Anime"}
        mock_get.return_value = mock_resp
        res = mal.get_mal_data(1, "test_client_id")
        assert res is not None
