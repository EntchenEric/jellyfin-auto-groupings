import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from jellyfin_auto_groupings.grouper import AutoGrouper
from jellyfin_auto_groupings.client import JellyfinClient

class TestAutoGrouperEdgeCases(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock(spec=JellyfinClient)
        self.grouper = AutoGrouper(client=self.client)

    def test_empty_collection_handling(self):
        self.client.get_items.return_value = []
        result = self.grouper.group_items([])
        self.assertEqual(result, 0)

    def test_invalid_rule_config(self):
        with self.assertRaises(Exception):
            self.grouper.apply_rules(None)

    def test_client_network_failure_handling(self):
        self.client.get_items.side_effect = Exception("Network error")
        with self.assertRaises(Exception):
            self.client.get_items()

if __name__ == '__main__':
    unittest.main()
