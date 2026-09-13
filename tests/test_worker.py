import unittest
from unittest.mock import patch, MagicMock
import worker

class TestWorker(unittest.TestCase):
    @patch('worker.JellyfinClient')
    @patch.dict('os.environ', {"JELLYFIN_URL": "http://localhost:8096", "JELLYFIN_API_KEY": "test"})
    def test_worker_run(self, mock_client_cls):
        mock_client = mock_client_cls.return_value
        mock_client.get_collections.return_value = []
        # Just verify worker module imports and functions exist
        self.assertTrue(hasattr(worker, 'main'))

if __name__ == '__main__':
    unittest.main()
