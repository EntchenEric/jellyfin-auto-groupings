import pytest
import os
import requests
from unittest.mock import patch, MagicMock
from config import save_config


@pytest.mark.usefixtures("temp_config")
def test_get_config(client):
    response = client.get('/api/config')
    assert response.status_code == 200
    data = response.get_json()
    assert "jellyfin_url" in data


@pytest.mark.usefixtures("temp_config")
def test_update_config(client):
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
    assert "successfully" in response.get_json()["message"]


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


@patch('routes.requests.get')
@pytest.mark.usefixtures("temp_config")
def test_get_jellyfin_metadata(mock_get, client):
    save_config({"jellyfin_url": "http://test", "api_key": "key"})

    def mock_genres(url, **kwargs):
        m = MagicMock()
        if "Genres" in url:
            m.json.return_value = {"Items": [{"Name": "Action"}, {"Name": "Comedy"}]}
        elif "Studios" in url:
            m.json.return_value = {"Items": [{"Name": "Studio A"}]}
        elif "Persons" in url:
            m.json.return_value = {"Items": [{"Name": "Actor A"}]}
        elif "Tags" in url:
            m.json.return_value = {"Items": [{"Name": "4K"}]}
        else:
            m.json.return_value = {"Items": []}
        m.raise_for_status = MagicMock()
        return m

    mock_get.side_effect = mock_genres

    response = client.get('/api/jellyfin/metadata')
    assert response.status_code == 200
    data = response.get_json()
    assert "Action" in data["metadata"]["genre"]
    assert "Comedy" in data["metadata"]["genre"]
    assert "Actor A" in data["metadata"]["actor"]
    assert "Studio A" in data["metadata"]["studio"]
    assert "4K" in data["metadata"]["tag"]


@patch('routes.run_sync')
@pytest.mark.usefixtures("temp_config")
def test_api_sync(mock_sync, client):
    mock_sync.return_value = [{"group": "G1", "links": 5}]
    response = client.post('/api/sync')
    assert response.status_code == 200
    data = response.get_json()
    assert data["results"][0]["group"] == "G1"


def test_upload_cover_security_check(client):
    # Test with massive payload
    large_data = "data:image/jpeg;base64," + "a" * (5 * 1024 * 1024)  # 5MB
    response = client.post('/api/upload_cover', json={"group_name": "G", "image": large_data})
    assert response.status_code == 413


@patch('routes.get_cover_path')
def test_upload_cover_success(mock_get_path, client, tmp_path):
    mock_get_path.return_value = str(tmp_path / "test.jpg")
    # Base64 for a tiny transparent pixel
    img_data = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    response = client.post('/api/upload_cover', json={"group_name": "Test Group", "image": img_data})
    assert response.status_code == 200
    assert os.path.exists(tmp_path / "test.jpg")


@pytest.mark.usefixtures("temp_config")
def test_save_config_route(client):
    new_cfg = {"jellyfin_url": "http://new", "api_key": "new_key"}
    response = client.post('/api/config', json=new_cfg)
    assert response.status_code == 200
    assert response.get_json()["config"]["jellyfin_url"] == "http://new"


@patch('routes.fetch_jellyfin_items')
@pytest.mark.usefixtures("temp_config")
def test_auto_detect_paths(mock_fetch, client):
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
@pytest.mark.usefixtures("temp_config")
def test_preview_grouping(mock_preview, client):
    save_config({"jellyfin_url": "http://test", "api_key": "key"})
    mock_preview.return_value = ([{"Name": "M1"}], None, 200)

    # Simple
    response = client.post('/api/grouping/preview', json={"type": "genre", "value": "Action"})
    assert response.status_code == 200
    assert response.get_json()["count"] == 1


@patch('routes.run_sync')
@pytest.mark.usefixtures("temp_config")
def test_preview_all_sync(mock_sync, client):
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
@pytest.mark.usefixtures("temp_config")
def test_update_config_scheduler_fail(mock_sched, client):
    mock_sched.side_effect = Exception("Fail")
    response = client.post('/api/config', json={"jellyfin_url": "http://jf"})
    assert response.status_code == 200  # Should not fail the whole request
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


@pytest.mark.usefixtures("temp_config")
def test_get_jellyfin_metadata_no_config(client):
    # Config is empty by default in temp_config if we don't save anything
    response = client.get('/api/jellyfin/metadata')
    assert response.status_code == 400


@patch('routes.requests.get')
@pytest.mark.usefixtures("temp_config")
def test_get_jellyfin_metadata_error(mock_get, client):
    save_config({"jellyfin_url": "http://test", "api_key": "key"})
    mock_get.side_effect = requests.exceptions.ConnectionError("Fetch failed")
    response = client.get('/api/jellyfin/metadata')
    assert response.status_code == 400


def test_upload_cover_invalid_json(client):
    response = client.post('/api/upload_cover', data="bad")
    assert response.status_code == 400


def test_upload_cover_bad_format(client):
    response = client.post('/api/upload_cover', json={"group_name": "G", "image": "not-data-uri"})
    assert response.status_code == 400


@patch('routes.save_config')
@pytest.mark.usefixtures("temp_config")
def test_update_config_error(mock_save, client):
    mock_save.side_effect = OSError("Disk full")
    response = client.post('/api/config', json={"jellyfin_url": "http://u"})
    assert response.status_code == 500


@pytest.mark.usefixtures("temp_config")
def test_preview_grouping_missing_type(client):
    save_config({"jellyfin_url": "http://t", "api_key": "k"})
    response = client.post('/api/grouping/preview', json={"value": "V"})
    assert response.status_code == 400


@pytest.mark.usefixtures("temp_config")
def test_preview_grouping_invalid_type(client):
    save_config({"jellyfin_url": "http://t", "api_key": "k"})
    response = client.post('/api/grouping/preview', json={"type": "invalid", "value": "V"})
    assert response.status_code == 400


@patch('routes.preview_group')
@pytest.mark.usefixtures("temp_config")
def test_preview_grouping_error(mock_preview, client):
    save_config({"jellyfin_url": "http://t", "api_key": "k"})
    mock_preview.return_value = ([], "Error occurred", 500)
    response = client.post('/api/grouping/preview', json={"type": "genre", "value": "Action"})
    assert response.status_code == 500


@patch('routes.fetch_jellyfin_items')
@pytest.mark.usefixtures("temp_config")
def test_auto_detect_no_media(mock_fetch, client):
    save_config({"jellyfin_url": "http://t", "api_key": "k"})
    mock_fetch.return_value = []
    response = client.post('/api/jellyfin/auto-detect-paths')
    assert response.status_code == 400


@patch('os.listdir')
def test_browse_directory_oserror(mock_listdir, client):
    mock_listdir.side_effect = OSError("IO Error")
    response = client.get('/api/browse')
    assert response.status_code == 400


def test_update_config_invalid_cron(client):
    response = client.post('/api/config', json={
        "scheduler": {"global_enabled": True, "global_schedule": "invalid"},
    })
    assert response.status_code == 400
    data = response.get_json()
    assert data["status"] == "error"
    assert "Invalid cron" in data["message"]


def test_update_config_invalid_group_cron(client):
    response = client.post('/api/config', json={
        "groups": [{"name": "Test", "schedule_enabled": True, "schedule": "* * * * * *"}],
    })
    assert response.status_code == 400
    data = response.get_json()
    assert data["status"] == "error"


# ---------------------------------------------------------------------------
# get_jellyfin_users
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("temp_config")
def test_get_jellyfin_users_no_config(client):
    response = client.get('/api/jellyfin/users')
    assert response.status_code == 400


@patch('routes.get_users')
@pytest.mark.usefixtures("temp_config")
def test_get_jellyfin_users_success(mock_get_users, client):
    save_config({"jellyfin_url": "http://test", "api_key": "key"})
    mock_get_users.return_value = [{"Id": "1", "Name": "User A"}]
    response = client.get('/api/jellyfin/users')
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "success"
    assert data["users"][0]["name"] == "User A"


@patch('routes.get_users')
@pytest.mark.usefixtures("temp_config")
def test_get_jellyfin_users_exception(mock_get_users, client):
    save_config({"jellyfin_url": "http://test", "api_key": "key"})
    mock_get_users.side_effect = Exception("Jellyfin down")
    response = client.get('/api/jellyfin/users')
    assert response.status_code == 400
    assert response.get_json()["status"] == "error"


# ---------------------------------------------------------------------------
# upload_cover edge cases
# ---------------------------------------------------------------------------

def test_upload_cover_missing_fields(client):
    response = client.post('/api/upload_cover', json={"group_name": "G"})
    assert response.status_code == 400


def test_upload_cover_invalid_image_data(client):
    response = client.post('/api/upload_cover', json={"group_name": "G", "image": "plain-text"})
    assert response.status_code == 400


@patch('routes.get_cover_path')
def test_upload_cover_server_error(mock_get_cover, client):
    mock_get_cover.side_effect = Exception("Disk full")
    img_data = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    response = client.post('/api/upload_cover', json={"group_name": "G", "image": img_data})
    assert response.status_code == 500
    assert response.get_json()["status"] == "error"


# ---------------------------------------------------------------------------
# get_cleanup_items
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("temp_config")
def test_get_cleanup_items_no_target_path(client):
    save_config({"target_path": ""})
    response = client.get('/api/cleanup')
    assert response.status_code == 200
    assert response.get_json()["items"] == []


@pytest.mark.usefixtures("temp_config")
def test_get_cleanup_items_with_groups(client, tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    (target / "Action").mkdir()
    (target / ".hidden").mkdir()
    save_config({
        "target_path": str(target),
        "groups": [{"name": "Action"}]
    })
    response = client.get('/api/cleanup')
    assert response.status_code == 200
    data = response.get_json()
    assert len(data["items"]) == 1
    assert data["items"][0]["name"] == "Action"
    assert data["items"][0]["is_configured"] is True


@patch('os.listdir')
@pytest.mark.usefixtures("temp_config")
def test_get_cleanup_items_oserror(mock_listdir, client, tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    save_config({"target_path": str(target)})
    mock_listdir.side_effect = OSError("Permission denied")
    response = client.get('/api/cleanup')
    assert response.status_code == 500


# ---------------------------------------------------------------------------
# perform_cleanup
# ---------------------------------------------------------------------------

def test_perform_cleanup_invalid_json(client):
    response = client.post('/api/cleanup', data="not json")
    assert response.status_code == 400


def test_perform_cleanup_folders_not_list(client):
    response = client.post('/api/cleanup', json={"folders": "bad"})
    assert response.status_code == 400


@pytest.mark.usefixtures("temp_config")
def test_perform_cleanup_no_target_path(client):
    response = client.post('/api/cleanup', json={"folders": ["Action"]})
    assert response.status_code == 404


@pytest.mark.usefixtures("temp_config")
def test_perform_cleanup_invalid_folder_name(client, tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    save_config({"target_path": str(target)})
    response = client.post('/api/cleanup', json={"folders": ["../etc", 123, ""]})
    assert response.status_code == 207
    data = response.get_json()
    assert data["status"] == "partial_success"
    assert len(data["errors"]) == 3


@pytest.mark.usefixtures("temp_config")
def test_perform_cleanup_success(client, tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    (target / "Action").mkdir()
    save_config({"target_path": str(target)})
    response = client.post('/api/cleanup', json={"folders": ["Action"]})
    assert response.status_code == 200
    assert response.get_json()["deleted"] == 1


# ---------------------------------------------------------------------------
# auto_detect_paths error paths
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("temp_config")
def test_auto_detect_paths_no_config(client):
    response = client.post('/api/jellyfin/auto-detect-paths')
    assert response.status_code == 400


@patch('routes.fetch_jellyfin_items')
@pytest.mark.usefixtures("temp_config")
def test_auto_detect_paths_fetch_error(mock_fetch, client):
    save_config({"jellyfin_url": "http://test", "api_key": "key"})
    mock_fetch.side_effect = Exception("Connection refused")
    response = client.post('/api/jellyfin/auto-detect-paths')
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# browse_directory edge cases
# ---------------------------------------------------------------------------

def test_browse_directory_file_fallback(client):
    # When path is a file, fall back to its parent directory
    home = os.path.expanduser("~")
    response = client.get(f'/api/browse?path={home}/somefile.txt')
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "success"
    assert data["current"] == home


@patch('os.listdir')
def test_browse_directory_permission_error(mock_listdir, client):
    mock_listdir.side_effect = PermissionError("No access")
    response = client.get('/api/browse')
    assert response.status_code == 200
    assert response.get_json()["dirs"] == []


# ---------------------------------------------------------------------------
# get_test_results
# ---------------------------------------------------------------------------

def test_get_test_results(client):
    response = client.get('/api/test/results')
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "success"
    assert "results" in data


# ---------------------------------------------------------------------------
# run_tests
# ---------------------------------------------------------------------------

def test_run_tests_production_mode(client):
    response = client.post('/api/test/run')
    assert response.status_code == 403
    assert response.get_json()["status"] == "error"


# ---------------------------------------------------------------------------
# index / test_dashboard
# ---------------------------------------------------------------------------

def test_index_html(client):
    response = client.get('/')
    assert response.status_code == 200
    assert b"html" in response.data.lower()


def test_test_dashboard(client):
    response = client.get('/test')
    assert response.status_code == 200
    assert b"html" in response.data.lower()


# ---------------------------------------------------------------------------
# routes.py coverage improvements
# ---------------------------------------------------------------------------

# CSRF check (lines 47-48)
def test_csrf_protection_non_testing(client):
    from flask import current_app
    old_testing = current_app.testing
    current_app.testing = False
    try:
        response = client.post('/api/config', json={"jellyfin_url": "http://test"})
        assert response.status_code == 403
        assert "CSRF" in response.get_json()["message"]
    finally:
        current_app.testing = old_testing


# Cleanup schedule validation (lines 121-123)
def test_update_config_invalid_cleanup_cron(client):
    response = client.post('/api/config', json={
        "scheduler": {"cleanup_enabled": True, "cleanup_schedule": "bad"},
    })
    assert response.status_code == 400
    data = response.get_json()
    assert "Cleanup schedule" in data["errors"][0]


# _fetch_jellyfin_endpoint partial data break (line 250)
@patch('routes.requests.get')
@pytest.mark.usefixtures("temp_config")
def test_fetch_jellyfin_endpoint_partial_data(mock_get, client):
    from routes import _fetch_jellyfin_endpoint
    resp1 = MagicMock()
    resp1.status_code = 200
    resp1.json.return_value = {"Items": [{"Name": "G1"}]}
    resp1.raise_for_status = MagicMock()

    resp2 = MagicMock()
    resp2.raise_for_status.side_effect = requests.exceptions.ConnectionError("fail")

    mock_get.side_effect = [resp1, resp2]
    result = _fetch_jellyfin_endpoint("http://jf", "key", "Genres")
    assert len(result) == 1


# _fetch_jellyfin_endpoint pagination (line 259)
@patch('routes.requests.get')
@pytest.mark.usefixtures("temp_config")
def test_fetch_jellyfin_endpoint_pagination(mock_get, client):
    from routes import _fetch_jellyfin_endpoint
    resp1 = MagicMock()
    resp1.status_code = 200
    resp1.json.return_value = {"Items": [{"Name": f"G{i}"} for i in range(200)]}
    resp1.raise_for_status = MagicMock()

    resp2 = MagicMock()
    resp2.status_code = 200
    resp2.json.return_value = {"Items": [{"Name": "G200"}]}
    resp2.raise_for_status = MagicMock()

    mock_get.side_effect = [resp1, resp2]
    result = _fetch_jellyfin_endpoint("http://jf", "key", "Genres")
    assert len(result) == 201


# Metadata unexpected exception (lines 318-319)
@patch('routes.ThreadPoolExecutor')
@pytest.mark.usefixtures("temp_config")
def test_get_jellyfin_metadata_exception(mock_pool, client):
    save_config({"jellyfin_url": "http://test", "api_key": "key"})
    mock_pool.side_effect = Exception("Pool fail")
    response = client.get('/api/jellyfin/metadata')
    assert response.status_code == 400


# Sync ValueError (lines 438-439)
@patch('routes.run_sync')
@pytest.mark.usefixtures("temp_config")
def test_api_sync_value_error(mock_sync, client):
    mock_sync.side_effect = ValueError("Bad config")
    response = client.post('/api/sync')
    assert response.status_code == 400
    assert "Bad config" in response.get_json()["message"]


# Sync RuntimeError (lines 440-441)
@patch('routes.run_sync')
@pytest.mark.usefixtures("temp_config")
def test_api_sync_runtime_error(mock_sync, client):
    mock_sync.side_effect = RuntimeError("Sync failed")
    response = client.post('/api/sync')
    assert response.status_code == 500
    assert "Sync failed" in response.get_json()["message"]


# Preview_all ValueError (lines 465-466)
@patch('routes.run_sync')
@pytest.mark.usefixtures("temp_config")
def test_preview_all_value_error(mock_sync, client):
    mock_sync.side_effect = ValueError("Bad config")
    response = client.post('/api/sync/preview_all')
    assert response.status_code == 400
    assert "Bad config" in response.get_json()["message"]


# Preview_all RuntimeError (lines 467-468)
@patch('routes.run_sync')
@pytest.mark.usefixtures("temp_config")
def test_preview_all_runtime_error(mock_sync, client):
    mock_sync.side_effect = RuntimeError("Sync failed")
    response = client.post('/api/sync/preview_all')
    assert response.status_code == 500
    assert "Sync failed" in response.get_json()["message"]


# Preview grouping missing value (lines 485, 510, 514)
@pytest.mark.usefixtures("temp_config")
def test_preview_grouping_missing_value(client):
    save_config({"jellyfin_url": "http://t", "api_key": "k"})
    response = client.post('/api/grouping/preview', json={"type": "genre"})
    assert response.status_code == 400


@pytest.mark.usefixtures("temp_config")
def test_preview_grouping_value_not_string(client):
    save_config({"jellyfin_url": "http://t", "api_key": "k"})
    response = client.post('/api/grouping/preview', json={"type": "genre", "value": 123})
    assert response.status_code == 400


@pytest.mark.usefixtures("temp_config")
def test_preview_grouping_empty_value(client):
    save_config({"jellyfin_url": "http://t", "api_key": "k"})
    response = client.post('/api/grouping/preview', json={"type": "genre", "value": "   "})
    assert response.status_code == 400


# Preview grouping server not configured (lines 491-492)
@pytest.mark.usefixtures("temp_config")
def test_preview_grouping_no_config(client):
    response = client.post('/api/grouping/preview', json={"type": "genre", "value": "Action"})
    assert response.status_code == 400
    assert "Server settings not configured" in response.get_json()["message"]


# Preview grouping exceptions (lines 532-537)
@patch('routes.preview_group')
@pytest.mark.usefixtures("temp_config")
def test_preview_grouping_runtime_error(mock_preview, client):
    save_config({"jellyfin_url": "http://t", "api_key": "k"})
    mock_preview.side_effect = RuntimeError("Preview failed")
    response = client.post('/api/grouping/preview', json={"type": "genre", "value": "Action"})
    assert response.status_code == 500


@patch('routes.preview_group')
@pytest.mark.usefixtures("temp_config")
def test_preview_grouping_unexpected_error(mock_preview, client):
    save_config({"jellyfin_url": "http://t", "api_key": "k"})
    mock_preview.side_effect = TypeError("Unexpected")
    response = client.post('/api/grouping/preview', json={"type": "genre", "value": "Action"})
    assert response.status_code == 500


# Cleanup with auto_create_libraries (lines 601-609)
@patch('routes.delete_virtual_folder')
@patch('routes.os.path.exists')
@pytest.mark.usefixtures("temp_config")
def test_perform_cleanup_with_auto_create(mock_exists, mock_delete, client, tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    (target / "Action").mkdir()
    save_config({
        "target_path": str(target),
        "auto_create_libraries": True,
        "jellyfin_url": "http://jf",
        "api_key": "key"
    })
    mock_exists.return_value = True
    response = client.post('/api/cleanup', json={"folders": ["Action"]})
    assert response.status_code == 200
    mock_delete.assert_called_once()


# Auto-detect: item with no Path (line 683)
@patch('routes.fetch_jellyfin_items')
@pytest.mark.usefixtures("temp_config")
def test_auto_detect_no_path(mock_fetch, client):
    save_config({"jellyfin_url": "http://test", "api_key": "key"})
    mock_fetch.return_value = [{"Id": "1", "Name": "NoPath"}]
    response = client.post('/api/jellyfin/auto-detect-paths')
    assert response.status_code == 200
    data = response.get_json()
    assert data["detected"]["media_path_in_jellyfin"] is None


# Auto-detect: root not a directory (line 693)
@patch('routes.fetch_jellyfin_items')
@patch('routes.os.path.isdir')
@pytest.mark.usefixtures("temp_config")
def test_auto_detect_root_not_dir(mock_isdir, mock_fetch, client):
    save_config({"jellyfin_url": "http://test", "api_key": "key"})
    mock_fetch.return_value = [{"Path": "/media/movies/M1.mkv"}]
    mock_isdir.return_value = False
    response = client.post('/api/jellyfin/auto-detect-paths')
    assert response.status_code == 200


# Auto-detect: mount point skip (lines 697-698)
@patch('routes.fetch_jellyfin_items')
@patch('routes.os.path.ismount')
@patch('routes.os.path.isdir')
@patch('routes.os.walk')
@pytest.mark.usefixtures("temp_config")
def test_auto_detect_mount_skip(mock_walk, mock_isdir, mock_ismount, mock_fetch, client):
    save_config({"jellyfin_url": "http://test", "api_key": "key"})
    mock_fetch.return_value = [{"Path": "/media/movies/M1.mkv"}]
    mock_isdir.return_value = True
    mock_ismount.return_value = True
    mock_walk.return_value = [("/home", ["sub"], ["M1.mkv"])]
    response = client.post('/api/jellyfin/auto-detect-paths')
    assert response.status_code == 200


# Auto-detect: timeout (lines 701-703)
@patch('routes.fetch_jellyfin_items')
@patch('routes.time.time')
@patch('routes.os.walk')
@patch('routes.os.path.isdir')
@pytest.mark.usefixtures("temp_config")
def test_auto_detect_timeout(mock_isdir, mock_walk, mock_time, mock_fetch, client):
    save_config({"jellyfin_url": "http://test", "api_key": "key"})
    mock_fetch.return_value = [{"Path": "/media/movies/M1.mkv"}]
    mock_isdir.return_value = True
    mock_time.side_effect = [0, 0, 100]
    mock_walk.return_value = [("/home", ["sub"], ["M1.mkv"])]
    response = client.post('/api/jellyfin/auto-detect-paths')
    assert response.status_code == 200


# Auto-detect: file limit (lines 707-709)
@patch('routes.fetch_jellyfin_items')
@patch('routes.os.walk')
@patch('routes.os.path.isdir')
@pytest.mark.usefixtures("temp_config")
def test_auto_detect_file_limit(mock_isdir, mock_walk, mock_fetch, client):
    save_config({"jellyfin_url": "http://test", "api_key": "key"})
    mock_fetch.return_value = [{"Path": "/media/movies/M1.mkv"}]
    mock_isdir.return_value = True
    mock_walk.return_value = [("/home", ["sub"], ["f"])]
    response = client.post('/api/jellyfin/auto-detect-paths')
    assert response.status_code == 200


# Auto-detect: depth limit (lines 715-716)
@patch('routes.fetch_jellyfin_items')
@patch('routes.os.walk')
@patch('routes.os.path.isdir')
@pytest.mark.usefixtures("temp_config")
def test_auto_detect_depth_limit(mock_isdir, mock_walk, mock_fetch, client):
    save_config({"jellyfin_url": "http://test", "api_key": "key"})
    mock_fetch.return_value = [{"Path": "/media/movies/M1.mkv"}]
    mock_isdir.return_value = True
    deep_path = "/a/b/c/d/e/f/g"
    mock_walk.return_value = [(deep_path, [], ["M1.mkv"])]
    response = client.post('/api/jellyfin/auto-detect-paths')
    assert response.status_code == 200


# Test results file read error (lines 821-825)
@patch('routes.os.path.exists')
@patch('builtins.open')
def test_get_test_results_read_error(mock_open, mock_exists, client):
    mock_exists.return_value = True
    mock_open.side_effect = IOError("Read error")
    response = client.get('/api/test/results')
    assert response.status_code == 200
    data = response.get_json()
    assert "Error reading file." in data["results"].values()


# run_tests production mode (line 838-845)
@patch('flask.current_app')
def test_run_tests_production(mock_app, client):
    mock_app.debug = False
    response = client.post('/api/test/run')
    assert response.status_code == 403
    assert "Not available" in response.get_json()["message"]


# run_tests subprocess exception (lines 843-845)
@patch('flask.current_app')
@patch('subprocess.run')
def test_run_tests_subprocess_exception(mock_subprocess, mock_app, client):
    mock_app.debug = True
    mock_subprocess.side_effect = OSError("Subprocess fail")
    response = client.post('/api/test/run')
    assert response.status_code == 500
    assert "Subprocess fail" in response.get_json()["message"]
