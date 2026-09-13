import unittest
from unittest.mock import patch, MagicMock
from utils.jellyfin_client import JellyfinClient

class TestJellyfinClient(unittest.TestCase):
    @patch('utils.jellyfin_client.requests.Session')
    def test_client_initialization(self, mock_session):
        client = JellyfinClient(server_url="http://localhost:8096", api_key="test_key")
        self.assertEqual(client.server_url, "http://localhost:8096")
        self.assertEqual(client.api_key, "test_key")
        self.assertIn("X-Emby-Token", client.session.headers)

    @patch('utils.jellyfin_client.requests.Session')
    def test_get_collections(self, mock_session_cls):
        mock_session = mock_session_cls.return_value
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"Items": [{"Id": "1", "Name": "Action"}]}
        mock_session.get.return_value = mock_response

        client = JellyfinClient("http://localhost:8096", "test_key")
        collections = client.get_collections()
        self.assertEqual(len(collections), 1)
        self.assertEqual(collections[0]["Name"], "Action")

if __name__ == '__main__':
    unittest.main()
