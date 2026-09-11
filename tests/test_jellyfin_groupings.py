import unittest
from unittest.mock import MagicMock, patch
import requests
from jellyfin_groupings import JellyfinClient, process_groupings


class TestJellyfinGroupings(unittest.TestCase):

    def test_process_groupings_dry_run(self):
        client = MagicMock()
        client.get_collections.return_value = [{'Id': 'col1', 'Name': 'Star Wars'}]
        client.get_collection_items.return_value = [
            {'Id': 'm2', 'Name': 'Empire Strikes Back', 'PremiereDate': '1980-05-21', 'ForcedSortName': ''},
            {'Id': 'm1', 'Name': 'A New Hope', 'PremiereDate': '1977-05-25', 'ForcedSortName': ''}
        ]

        changes = process_groupings(client, dry_run=True)

        self.assertEqual(len(changes), 2)
        self.assertEqual(changes[0], ('m1', 'A New Hope', 'Star Wars 01'))
        self.assertEqual(changes[1], ('m2', 'Empire Strikes Back', 'Star Wars 02'))
        client.update_item_sort_name.assert_not_called()

    def test_process_groupings_apply_changes(self):
        client = MagicMock()
        client.get_collections.return_value = [{'Id': 'col1', 'Name': 'Star Wars'}]
        client.get_collection_items.return_value = [
            {'Id': 'm1', 'Name': 'A New Hope', 'PremiereDate': '1977-05-25', 'ForcedSortName': ''}
        ]

        changes = process_groupings(client, dry_run=False)

        self.assertEqual(len(changes), 1)
        client.update_item_sort_name.assert_called_once_with('m1', 'Star Wars 01')

    def test_process_groupings_no_change_needed(self):
        client = MagicMock()
        client.get_collections.return_value = [{'Id': 'col1', 'Name': 'Star Wars'}]
        client.get_collection_items.return_value = [
            {'Id': 'm1', 'Name': 'A New Hope', 'PremiereDate': '1977-05-25', 'ForcedSortName': 'Star Wars 01'}
        ]

        changes = process_groupings(client, dry_run=False)

        self.assertEqual(len(changes), 0)
        client.update_item_sort_name.assert_not_called()

    @patch('requests.get')
    def test_client_get_collections(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {'Items': [{'Id': 'col1', 'Name': 'Collection 1'}]}
        mock_get.return_value = mock_response

        client = JellyfinClient('http://localhost:8096', 'fake-key')
        collections = client.get_collections()

        self.assertEqual(len(collections), 1)
        self.assertEqual(collections[0]['Name'], 'Collection 1')
        mock_get.assert_called_once_with(
            'http://localhost:8096/Items?IncludeItemTypes=BoxSet&Recursive=true',
            headers={'X-Emby-Token': 'fake-key', 'Content-Type': 'application/json'}
        )


if __name__ == '__main__':
    unittest.main()
