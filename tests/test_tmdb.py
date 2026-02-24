import pytest
from unittest.mock import patch, MagicMock
from tmdb import fetch_tmdb_list, get_tmdb_recommendations
import requests

def test_fetch_tmdb_list_missing_args():
    with pytest.raises(ValueError, match="A TMDb API Key is required"):
        fetch_tmdb_list("123", "")
    with pytest.raises(ValueError, match="A TMDb List ID is required"):
        fetch_tmdb_list("", "api_key")

@patch('requests.get')
def test_fetch_tmdb_list_success(mock_get):
    mock_resp_1 = MagicMock()
    mock_resp_1.status_code = 200
    mock_resp_1.json.return_value = {
        "items": [{"id": 101}, {"id": 102}],
        "total_pages": 2
    }
    mock_resp_2 = MagicMock()
    mock_resp_2.status_code = 200
    mock_resp_2.json.return_value = {
        "items": [{"id": 103}],
        "total_pages": 2
    }
    mock_get.side_effect = [mock_resp_1, mock_resp_2]

    ids = fetch_tmdb_list("123", "test_key")
    assert ids == ["101", "102", "103"]
    assert mock_get.call_count == 2

@patch('requests.get')
def test_fetch_tmdb_list_url_parsing(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "items": [{"id": 101}],
        "total_pages": 1
    }
    mock_get.return_value = mock_resp

    ids = fetch_tmdb_list("https://www.themoviedb.org/list/456?language=en-US", "test_key")
    assert ids == ["101"]
    args, kwargs = mock_get.call_args
    assert "/list/456" in args[0]

@patch('requests.get')
def test_fetch_tmdb_list_failure(mock_get):
    mock_get.side_effect = requests.exceptions.RequestException("Network Error")
    with pytest.raises(RuntimeError, match="Failed to fetch TMDb list page 1"):
        fetch_tmdb_list("123", "test_key")

def test_get_tmdb_recommendations_missing_key():
    with pytest.raises(ValueError, match="A TMDb API Key is required"):
        get_tmdb_recommendations([("101", "movie")], "")

@patch('requests.get')
def test_get_tmdb_recommendations_success(mock_get):
    mock_resp_movie = MagicMock()
    mock_resp_movie.status_code = 200
    mock_resp_movie.json.return_value = {
        "results": [{"id": 201}, {"id": 202}]
    }
    
    mock_resp_tv = MagicMock()
    mock_resp_tv.status_code = 200
    mock_resp_tv.json.return_value = {
        "results": [{"id": 202}, {"id": 203}]
    }
    
    mock_get.side_effect = [mock_resp_movie, mock_resp_tv]
    
    # "movie" returns 201, 202
    # "tv" returns 202, 203
    # 202 gets score from both, so it should be the highest
    recs = get_tmdb_recommendations([("101", "movie"), ("102", "tv")], "test_key")
    
    # 201 score: 1.0/1 = 1.0
    # 202 score: 1.0/2 + 1.0/1 = 1.5
    # 203 score: 1.0/2 = 0.5
    assert recs == ["202", "201", "203"]

@patch('requests.get')
def test_get_tmdb_recommendations_failure_skipped(mock_get):
    mock_resp_movie = MagicMock()
    mock_resp_movie.status_code = 200
    mock_resp_movie.json.return_value = {
        "results": [{"id": 201}]
    }
    
    mock_get.side_effect = [requests.exceptions.RequestException("Error"), mock_resp_movie]
    
    recs = get_tmdb_recommendations([("error_id", "movie"), ("101", "movie")], "test_key")
    assert recs == ["201"]
