"""Tests for API route handlers with mocked Jellyfin client."""

from unittest.mock import MagicMock, patch

import requests as requests_lib

TEST_URL = "http://localhost:8096"
TEST_API_KEY = "test-key"


class TestServerConnection:
    """Tests for /api/test-server endpoint."""

    def test_test_server_success(self, client):
        """Test that /api/test-server returns success with valid params."""
        with patch("routes.network.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_get.return_value = mock_resp

            resp = client.post("/api/test-server", json={
                "jellyfin_url": TEST_URL,
                "api_key": TEST_API_KEY,
            })
            data = resp.get_json()
            assert resp.status_code == 200
            assert data["status"] == "success"

    def test_test_server_missing_params(self, client):
        """Test that missing URL or API key returns error."""
        resp = client.post("/api/test-server", json={"jellyfin_url": ""})
        data = resp.get_json()
        assert data["status"] == "error"

        resp = client.post("/api/test-server", json={"api_key": "k"})
        data = resp.get_json()
        assert data["status"] == "error"

    def test_test_server_auth_failure(self, client):
        """Test that invalid API key returns error."""
        with patch("routes.network.get") as mock_get:
            mock_get.side_effect = requests_lib.exceptions.RequestException("Unauthorized")

            resp = client.post("/api/test-server", json={
                "jellyfin_url": TEST_URL,
                "api_key": "bad-key",
            })
            data = resp.get_json()
            assert data["status"] == "error"


class TestMetadataEndpoints:
    """Tests for /api/jellyfin/metadata endpoint."""

    def test_metadata_requires_valid_connection(self, client):
        """Test metadata endpoint returns error when Jellyfin is unreachable."""
        with patch("routes.fetch_jellyfin_items") as mock_fetch:
            mock_fetch.side_effect = Exception("Connection refused")
            resp = client.get("/api/jellyfin/metadata")
            data = resp.get_json()
            assert data["status"] == "error"

    def test_metadata_returns_categories(self, client):
        """Test successful metadata response has expected categories."""
        with patch("routes.load_config") as mock_load, \
                patch("routes.network.get") as mock_get:
            mock_load.return_value = {
                "jellyfin_url": TEST_URL,
                "api_key": TEST_API_KEY,
            }

            def mock_jellyfin(url, **kwargs):
                m = MagicMock()
                if "Genres" in url:
                    m.json.return_value = {"Items": [{"Name": "Action"}, {"Name": "Thriller"}], "TotalRecordCount": 2}
                elif "Studios" in url:
                    m.json.return_value = {"Items": [{"Name": "Studio A"}], "TotalRecordCount": 1}
                elif "Persons" in url:
                    m.json.return_value = {"Items": [{"Name": "Actor One"}], "TotalRecordCount": 1}
                elif "Tags" in url:
                    m.json.return_value = {"Items": [{"Name": "4K"}], "TotalRecordCount": 1}
                else:
                    m.json.return_value = {"Items": [], "TotalRecordCount": 0}
                m.raise_for_status = MagicMock()
                return m

            mock_get.side_effect = mock_jellyfin

            resp = client.get("/api/jellyfin/metadata")
            data = resp.get_json()
            assert data["status"] == "success"
            assert "metadata" in data
            meta = data["metadata"]
            for cat in ["genre", "studio", "tag", "actor"]:
                assert cat in meta, f"Missing metadata category: {cat}"


class TestPreviewEndpoint:
    """Tests for /api/grouping/preview endpoint."""

    def test_preview_missing_params(self, client):
        """Preview requires type and value."""
        resp = client.post("/api/grouping/preview", json={})
        data = resp.get_json()
        assert data["status"] == "error"

    def test_preview_with_valid_params(self, client):
        """Preview with genre type returns item count."""
        with patch("routes.load_config") as mock_load, \
                patch("routes.preview_group") as mock_preview:
            mock_load.return_value = {
                "jellyfin_url": TEST_URL,
                "api_key": TEST_API_KEY,
            }
            mock_preview.return_value = (
                [
                    {"Name": "Action Film", "Genres": ["Action"], "ProductionYear": 2024},
                    {"Name": "Thriller Film", "Genres": ["Thriller"], "ProductionYear": 2023},
                ],
                None,
                200,
            )

            resp = client.post("/api/grouping/preview", json={
                "type": "genre",
                "value": "Action",
                "watch_state": "",
            })
            data = resp.get_json()
            assert data["status"] == "success"
            assert isinstance(data.get("count"), int)
            assert isinstance(data.get("preview_items"), list)
