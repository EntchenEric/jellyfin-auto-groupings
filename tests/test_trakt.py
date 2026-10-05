import unittest
from unittest.mock import patch, MagicMock
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import trakt

class TestTrakt(unittest.TestCase):
    @patch('network.get')
    def test_fetch_trakt_list_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"type": "movie", "movie": {"ids": {"imdb": "tt0111161"}}},
            {"type": "show", "show": {"ids": {"imdb": "tt0903747"}}},
            {"type": "movie", "movie": {"ids": {"imdb": "tt0111161"}}},
            {"type": "movie", "movie": {"ids": {}}},
            "malformed_entry"
        ]
        mock_response.headers = {"X-Pagination-Page-Count": "1"}
        mock_get.return_value = mock_response

        ids = trakt.fetch_trakt_list("[https://trakt.tv/users/jane/lists/my-list](https://trakt.tv/users/jane/lists/my-list)", "client_id_123")
        self.assertEqual(ids, ["tt0111161", "tt0903747"])

    def test_fetch_trakt_list_missing_client_id(self):
        with self.assertRaises(ValueError):
            trakt.fetch_trakt_list("username/list-slug", "")

    def test_parse_trakt_list_url_invalid(self):
        with self.assertRaises(ValueError):
            trakt._parse_trakt_list_url("invalid-url")

if __name__ == '__main__':
    unittest.main()
