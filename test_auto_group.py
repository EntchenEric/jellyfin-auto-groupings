import unittest
from unittest.mock import MagicMock, patch
import os
import tempfile
import json
from auto_group import (
    load_config,
    clean_title,
    extract_base_title,
    group_items,
    create_collection,
    add_to_collection,
    get_libraries,
    get_library_items,
)

class TestAutoGroup(unittest.TestCase):

    def test_clean_title(self):
        self.assertEqual(clean_title(" Matrix, The "), "Matrix, The")
        self.assertEqual(clean_title("Matrix (1999)"), "Matrix")
        self.assertEqual(clean_title("Matrix [1080p]"), "Matrix")
        self.assertEqual(clean_title("Matrix: Reloaded"), "Matrix Reloaded")
        self.assertEqual(clean_title("Matrix - Revolutions"), "Matrix Revolutions")

    def test_extract_base_title(self):
        patterns = [
            r'^(.*?)\s+Part\s+\d+',
            r'^(.*?)\s+\d+$',
            r'^(.*?):.*$'
        ]
        self.assertEqual(extract_base_title("Harry Potter Part 1", patterns), "Harry Potter")
        self.assertEqual(extract_base_title("Star Wars 2", patterns), "Star Wars")
        self.assertEqual(extract_base_title("Avatar: The Way of Water", patterns), "Avatar")
        self.assertEqual(extract_base_title("Unique Movie", patterns), "Unique Movie")

    def test_group_items(self):
        items = [
            {"Id": "1", "Name": "Harry Potter 1"},
            {"Id": "2", "Name": "Harry Potter 2"},
            {"Id": "3", "Name": "Unique Movie"}
        ]
        patterns = [r'^(.*?)\s+\d+$']
        groups = group_items(items, patterns, min_group_size=2)
        self.assertIn("Harry Potter", groups)
        self.assertEqual(len(groups["Harry Potter"]), 2)
        self.assertNotIn("Unique Movie", groups)

    def test_load_config_env_vars(self):
        with patch.dict(os.environ, {
            "JELLYFIN_URL": "http://env-jellyfin:8096",
            "JELLYFIN_API_KEY": "env_key_123",
            "DRY_RUN": "true",
            "MIN_GROUP_SIZE": "3"
        }):
            config = load_config("non_existent_config.json")
            self.assertEqual(config["JELLYFIN_URL"], "http://env-jellyfin:8096")
            self.assertEqual(config["JELLYFIN_API_KEY"], "env_key_123")
            self.assertTrue(config["DRY_RUN"])
            self.assertEqual(config["MIN_GROUP_SIZE"], 3)

    def test_load_config_json_file(self):
        config_data = {
            "JELLYFIN_URL": "http://file-jellyfin:8096",
            "JELLYFIN_API_KEY": "file_key",
            "DRY_RUN": False,
            "MIN_GROUP_SIZE": 2
        }
        with tempfile.NamedTemporaryFile('w', delete=False) as f:
            json.dump(config_data, f)
            temp_path = f.name
        try:
            config = load_config(temp_path)
            self.assertEqual(config["JELLYFIN_URL"], "http://file-jellyfin:8096")
            self.assertEqual(config["JELLYFIN_API_KEY"], "file_key")
            self.assertFalse(config["DRY_RUN"])
        finally:
            os.remove(temp_path)

    @patch('requests.get')
    def test_get_libraries(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"Items": [{"Name": "Movies", "Id": "lib1"}]}
        mock_get.return_value = mock_response

        libs = get_libraries("http://localhost:8096", "key")
        self.assertEqual(len(libs), 1)
        self.assertEqual(libs[0]["Name"], "Movies")

    @patch('requests.post')
    def test_create_collection(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"Id": "coll123"}
        mock_post.return_value = mock_response

        coll_id = create_collection("http://localhost:8096", "key", "Matrix Collection", ["1", "2"])
        self.assertEqual(coll_id, "coll123")

if __name__ == '__main__':
    unittest.main()
