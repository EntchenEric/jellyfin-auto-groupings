import pytest
import os
import requests
from unittest.mock import patch, MagicMock
from config import save_config

def test_get_config(client, temp_config):
    response = client.get('/api/config')
    assert response.status_code == 200
    data = response.get_json()
    assert "jellyfin_url" in data

def test_update_config(client, temp_config):
    new_cfg = {"jellyfin_url": "http://new-url", "api_key": "new-key"}
    response = client.post('/api/config', json=new_cfg)
    assert response.status_code == 200
    
    # Verify it was saved
    response = client.get('/api/config')
    data = response.get_json()
    assert data["jellyfin_url"] == "http://new-url"

@patch('routes.requests.get')
def test_test_server_success(mock_get, client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_get.return_value = mock_response
    
    response = client.post('/api/test-server', json={"jellyfin_url": "http://test", "api_key": "key"})
    assert response.status_code == 200
    assert response.get_json()["status"] == "success"

@patch('routes.requests.get')
def test_test_server_failure(mock_get, client):
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_get.return_value = mock_response
    
    response = client.post('/api/test-server', json={"jellyfin_url": "http://test", "api_key": "wrong"})
    assert response.status_code == 400
    assert response.get_json()["status"] == "error"

def test_browse_directory(client):
    # Test with home directory
    response = client.get('/api/browse')
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "success"
    assert "dirs" in data

@patch('routes.fetch_jellyfin_items')
def test_get_jellyfin_metadata(mock_fetch, client, temp_config):
    save_config({"jellyfin_url": "http://test", "api_key": "key"})
    mock_fetch.return_value = [
        {"Genres": ["Action"], "People": [{"Name": "Actor A", "Type": "Actor"}]}
    ]
    response = client.get('/api/jellyfin/metadata')
    assert response.status_code == 200
    data = response.get_json()
    assert "Action" in data["metadata"]["genre"]
    assert "Actor A" in data["metadata"]["actor"]

@patch('routes.run_sync')
def test_api_sync(mock_sync, client, temp_config):
    mock_sync.return_value = [{"group": "G1", "links": 5}]
    response = client.post('/api/sync')
    assert response.status_code == 200
    data = response.get_json()
    assert data["results"][0]["group"] == "G1"

def test_upload_cover_security_check(client):
    # Test with massive payload
    large_data = "data:image/jpeg;base64," + "a" * (5 * 1024 * 1024) # 5MB
    response = client.post('/api/upload_cover', json={"group_name": "G", "image": large_data})
    assert response.status_code == 413

@patch('routes.get_cover_path')
def test_upload_cover_success(mock_get_path, client, tmp_path):
    mock_get_path.return_value = str(tmp_path / "test.jpg")
    # Base64 for a tiny transparent pixel
    img_data = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    response = client.post('/api/upload_cover', json={"group_name": "Test Group", "image": img_data})
    assert response.status_code == 200
    assert os.path.exists(tmp_path / "test.jpg")

def test_save_config_route(client, temp_config):
    new_cfg = {"jellyfin_url": "http://new", "api_key": "new_key"}
    response = client.post('/api/config', json=new_cfg)
    assert response.status_code == 200
    assert response.get_json()["config"]["jellyfin_url"] == "http://new"

@patch('routes.requests.get')
def test_server_route(mock_get, client):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_get.return_value = mock_resp
    
    response = client.post('/api/test-server', json={"jellyfin_url": "http://jf", "api_key": "key"})
    assert response.status_code == 200
    assert "successfully" in response.get_json()["message"]

@patch('routes.fetch_jellyfin_items')
def test_auto_detect_paths(mock_fetch, client, temp_config):
    save_config({"jellyfin_url": "http://test", "api_key": "key"})
    mock_fetch.return_value = [{"Path": "/data/Movies/M1.mkv"}]
    
    with patch('os.walk') as mock_walk:
        mock_walk.return_value = [
            ('/home/user/Movies', [], ['M1.mkv'])
        ]
        response = client.post('/api/jellyfin/auto-detect-paths')
        assert response.status_code == 200
        data = response.get_json()
        assert data["detected"]["media_path_on_host"] == "/home/user"

@patch('routes.preview_group')
def test_preview_grouping(mock_preview, client, temp_config):
    save_config({"jellyfin_url": "http://test", "api_key": "key"})
    mock_preview.return_value = ([{"Name": "M1"}], None, 200)
    
    # Simple
    response = client.post('/api/grouping/preview', json={"type": "genre", "value": "Action"})
    assert response.status_code == 200
    assert response.get_json()["count"] == 1
    
@patch('routes.run_sync')
def test_preview_all_sync(mock_sync, client, temp_config):
    mock_sync.return_value = [{"group": "G1", "links": 5}]
    response = client.post('/api/sync/preview_all')
    assert response.status_code == 200
    assert "Preview" in response.get_json()["message"]

def test_index(client):
    response = client.get('/')
    assert response.status_code == 200

def test_browse_security(client):
    # Test disallowed path
    response = client.get('/api/browse?path=/etc')
    assert response.status_code == 403

def test_update_config_non_dict(client):
    response = client.post('/api/config', data="not json", content_type='application/json')
    assert response.status_code == 400

@patch('routes.update_scheduler_jobs')
def test_update_config_scheduler_fail(mock_sched, client, temp_config):
    mock_sched.side_effect = Exception("Fail")
    response = client.post('/api/config', json={"jellyfin_url": "http://jf"})
    assert response.status_code == 200 # Should not fail the whole request
    assert response.get_json()["status"] == "success"

@patch('routes.requests.get')
def test_test_server_unexpected_error(mock_get, client):
    mock_get.side_effect = Exception("Big fail")
    response = client.post('/api/test-server', json={"jellyfin_url": "http://jf", "api_key": "k"})
    assert response.status_code == 500
    assert "Server error" in response.get_json()["message"]

def test_test_server_invalid_body(client):
    response = client.post('/api/test-server', data="not json")
    assert response.status_code == 400

def test_test_server_missing_fields(client):
    response = client.post('/api/test-server', json={"url": "missing key"})
    assert response.status_code == 400

@patch('routes.requests.get')
def test_test_server_exception(mock_get, client):
    mock_get.side_effect = requests.exceptions.ConnectionError("Failed")
    response = client.post('/api/test-server', json={"jellyfin_url": "http://test", "api_key": "key"})
    assert response.status_code == 400
    assert "Connection error" in response.get_json()["message"]

def test_get_jellyfin_metadata_no_config(client, temp_config):
    # Config is empty by default in temp_config if we don't save anything
    response = client.get('/api/jellyfin/metadata')
    assert response.status_code == 400

@patch('routes.fetch_jellyfin_items')
def test_get_jellyfin_metadata_error(mock_fetch, client, temp_config):
    save_config({"jellyfin_url": "http://test", "api_key": "key"})
    mock_fetch.side_effect = Exception("Fetch failed")
    response = client.get('/api/jellyfin/metadata')
    assert response.status_code == 400

def test_upload_cover_invalid_json(client):
    response = client.post('/api/upload_cover', data="bad")
    assert response.status_code == 400

def test_upload_cover_bad_format(client):
    response = client.post('/api/upload_cover', json={"group_name": "G", "image": "not-data-uri"})
    assert response.status_code == 400

@patch('routes.save_config')
def test_update_config_error(mock_save, client, temp_config):
    mock_save.side_effect = OSError("Disk full")
    response = client.post('/api/config', json={"jellyfin_url": "http://u"})
    assert response.status_code == 500

def test_preview_grouping_missing_type(client, temp_config):
    save_config({"jellyfin_url": "http://t", "api_key": "k"})
    response = client.post('/api/grouping/preview', json={"value": "V"})
    assert response.status_code == 400

def test_preview_grouping_invalid_type(client, temp_config):
    save_config({"jellyfin_url": "http://t", "api_key": "k"})
    response = client.post('/api/grouping/preview', json={"type": "invalid", "value": "V"})
    assert response.status_code == 400

@patch('routes.preview_group')
def test_preview_grouping_error(mock_preview, client, temp_config):
    save_config({"jellyfin_url": "http://t", "api_key": "k"})
    mock_preview.return_value = ([], "Error occurred", 500)
    response = client.post('/api/grouping/preview', json={"type": "genre", "value": "Action"})
    assert response.status_code == 500

@patch('routes.fetch_jellyfin_items')
def test_auto_detect_no_media(mock_fetch, client, temp_config):
    save_config({"jellyfin_url": "http://t", "api_key": "k"})
    mock_fetch.return_value = []
    response = client.post('/api/jellyfin/auto-detect-paths')
    assert response.status_code == 400

@patch('os.listdir')
def test_browse_directory_oserror(mock_listdir, client):
    mock_listdir.side_effect = OSError("IO Error")
    response = client.get('/api/browse')
    assert response.status_code == 400
