"""Unit tests for jellyfin_groupings module."""

import unittest
from unittest.mock import MagicMock, patch

from jellyfin_groupings import (
    JellyfinClient,
    group_items_by_director,
    group_items_by_genre,
    group_items_by_studio,
)


class TestJellyfinGroupings(unittest.TestCase):
    def setUp(self):
        self.sample_items = [
            {
                "Id": "1",
                "Name": "Item One",
                "Genres": ["Action", "Sci-Fi"],
                "Studios": [{"Name": "Studio A"}],
                "People": [{"Name": "Director X", "Type": "Director"}],
            },
            {
                "Id": "2",
                "Name": "Item Two",
                "Genres": ["Action"],
                "Studios": [{"Name": "Studio A"}],
                "People": [{"Name": "Director X", "Type": "Director"}],
            },
            {
                "Id": "3",
                "Name": "Item Three",
                "Genres": ["Action", "Comedy"],
                "Studios": [{"Name": "Studio A"}, {"Name": "Studio B"}],
                "People": [{"Name": "Director Y", "Type": "Director"}],
            },
        ]

    def test_group_items_by_genre(self):
        groups = group_items_by_genre(self.sample_items, min_count=2)
        self.assertIn("Action", groups)
        self.assertEqual(len(groups["Action"]), 3)
        self.assertNotIn("Sci-Fi", groups)

    def test_group_items_by_studio(self):
        groups = group_items_by_studio(self.sample_items, min_count=2)
        self.assertIn("Studio A", groups)
        self.assertEqual(groups["Studio A"], ["1", "2", "3"])
        self.assertNotIn("Studio B", groups)

    def test_group_items_by_director(self):
        groups = group_items_by_director(self.sample_items, min_count=2)
        self.assertIn("Director X", groups)
        self.assertEqual(groups["Director X"], ["1", "2"])
        self.assertNotIn("Director Y", groups)

    @patch("requests.Session.get")
    def test_jellyfin_client_get_items(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {"Items": [{"Id": "123", "Name": "Test"}]}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        client = JellyfinClient("http://localhost:8096", "test_token")
        items = client.get_items()

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["Id"], "123")

    @patch("requests.Session.post")
    def test_jellyfin_client_create_collection(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"Id": "col123"}
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        client = JellyfinClient("http://localhost:8096", "test_token")
        col_id = client.create_collection("Test Collection", ["1", "2"])

        self.assertEqual(col_id, "col123")

    def test_create_collection_empty_items(self):
        client = JellyfinClient("http://localhost:8096", "test_token")
        col_id = client.create_collection("Empty Collection", [])
        self.assertIsNone(col_id)


if __name__ == "__main__":
    unittest.main()
