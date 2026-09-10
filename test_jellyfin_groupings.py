import unittest
from unittest.mock import MagicMock, patch
import jellyfin_groupings

class TestJellyfinGroupings(unittest.TestCase):
    def test_sanitize_name(self):
        self.assertEqual(jellyfin_groupings.sanitize_name("  Marvel's   The Avengers!  "), "marvels the avengers")
        self.assertEqual(jellyfin_groupings.sanitize_name("Batman: The Dark Knight"), "batman the dark knight")
        self.assertEqual(jellyfin_groupings.sanitize_name(""), "")

    def test_group_items_by_collection(self):
        items = [
            {"Id": "1", "Name": "Iron Man", "SeriesName": "Marvel"},
            {"Id": "2", "Name": "Thor", "SeriesName": "Marvel"},
            {"Id": "3", "Name": "Batman", "SeriesName": "DC"},
            {"Id": "4", "Name": "Standalone Movie"}
        ]
        groups = jellyfin_groupings.group_items_by_collection(items)
        self.assertIn("Marvel", groups)
        self.assertIn("DC", groups)
        self.assertNotIn("Standalone Movie", groups)
        self.assertEqual(len(groups["Marvel"]), 2)
        self.assertEqual(len(groups["DC"]), 1)

    @patch("jellyfin_groupings.requests.get")
    def test_get_library_items_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"Items": [{"Id": "101", "Name": "Test Movie"}]}
        mock_get.return_value = mock_resp

        items = jellyfin_groupings.get_library_items("http://localhost:8096", "test-api-key", "user-123")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["Name"], "Test Movie")

    @patch("jellyfin_groupings.requests.post")
    def test_create_collection_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"Id": "col-1"}
        mock_post.return_value = mock_resp

        col_id = jellyfin_groupings.create_collection("http://localhost:8096", "test-api-key", "Marvel Collection", ["1", "2"])
        self.assertEqual(col_id, "col-1")

if __name__ == "__main__":
    unittest.main()
