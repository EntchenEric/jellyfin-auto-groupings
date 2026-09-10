"""Tests for external metadata providers (Anilist, Trakt, Mal, TMDB, Letterboxd, IMDB)."""
import pytest
from unittest.mock import patch, MagicMock
import anilist
import trakt
import mal

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
