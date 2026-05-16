import pytest
import os
import requests
from unittest.mock import patch, MagicMock
from config import save_config
from routes import _compute_common_root, _fetch_jellyfin_endpoint, _handle_config_error, MAX_B64_SIZE
from werkzeug.exceptions import HTTPException


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
    # Test with payload exceeding MAX_B64_SIZE
    large_data = "data:image/jpeg;base64," + "a" * (MAX_B64_SIZE + 1024 * 1024)
    response = client.post('/api/upload_cover', json={"group_name": "G", "image": large_data})
    assert response.status_code == 413


@patch('routes._get_cover_path')
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
    mock_sched.side_effect = RuntimeError("Fail")
    response = client.post('/api/config', json={"jellyfin_url": "http://jf"})
    assert response.status_code == 500
    data = response.get_json()
    assert data["status"] == "error"
    assert "scheduler could not be updated" in data["message"]
    assert "config" in data


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
    mock_get_users.side_effect = requests.exceptions.RequestException("Jellyfin down")
    response = client.get('/api/jellyfin/users')
    assert response.status_code == 400
    assert response.get_json()["status"] == "error"


# Invalid configuration format (line 278)
@patch('routes.load_config')
def test_get_jellyfin_metadata_invalid_config(mock_load, client):
    mock_load.return_value = "bad"
    response = client.get('/api/jellyfin/metadata')
    assert response.status_code == 500
    assert "Invalid configuration format" in response.get_json()["message"]


# Invalid configuration format (line 336)
@patch('routes.load_config')
def test_get_jellyfin_users_invalid_config(mock_load, client):
    mock_load.return_value = "bad"
    response = client.get('/api/jellyfin/users')
    assert response.status_code == 500
    assert "Invalid configuration format" in response.get_json()["message"]


# ---------------------------------------------------------------------------
# upload_cover edge cases
# ---------------------------------------------------------------------------

def test_upload_cover_missing_fields(client):
    response = client.post('/api/upload_cover', json={"group_name": "G"})
    assert response.status_code == 400


def test_upload_cover_invalid_image_data(client):
    response = client.post('/api/upload_cover', json={"group_name": "G", "image": "plain-text"})
    assert response.status_code == 400


def test_upload_cover_malformed_data_url(client):
    # Starts with data:image/ but has no comma -> ValueError from split
    response = client.post('/api/upload_cover', json={"group_name": "G", "image": "data:image/png;base64_NO_COMMA"})
    assert response.status_code == 400
    assert "Malformed image data" in response.get_json()["message"]


def test_upload_cover_invalid_base64(client):
    # Invalid base64 characters trigger binascii.Error
    response = client.post('/api/upload_cover', json={"group_name": "G", "image": "data:image/png;base64,!!!invalid!!!"})
    assert response.status_code == 400
    assert "Malformed image data" in response.get_json()["message"]


@patch('routes._get_cover_path')
def test_upload_cover_server_error(mock_get_cover, client):
    mock_get_cover.side_effect = OSError("Disk full")
    img_data = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    response = client.post('/api/upload_cover', json={"group_name": "G", "image": img_data})
    assert response.status_code == 500
    assert response.get_json()["status"] == "error"


@patch('routes._get_cover_path')
def test_upload_cover_unresolvable_path(mock_get_cover, client):
    mock_get_cover.return_value = None
    img_data = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    response = client.post('/api/upload_cover', json={"group_name": "G", "image": img_data})
    assert response.status_code == 500
    assert "Could not resolve cover storage path" in response.get_json()["message"]


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


# perform_cleanup rmtree OSError (lines 608-609)
@patch('shutil.rmtree')
@pytest.mark.usefixtures("temp_config")
def test_perform_cleanup_rmtree_error(mock_rmtree, client, tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    (target / "Action").mkdir()
    save_config({"target_path": str(target)})
    mock_rmtree.side_effect = OSError("Permission denied")
    response = client.post('/api/cleanup', json={"folders": ["Action"]})
    assert response.status_code == 207
    data = response.get_json()
    assert data["status"] == "partial_success"
    assert "Permission denied" in data["errors"][0]


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
    mock_fetch.side_effect = requests.exceptions.RequestException("Connection refused")
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
@patch('jellyfin.requests.get')
@pytest.mark.usefixtures("temp_config")
def test_fetch_jellyfin_endpoint_partial_data(mock_get, client):
    resp1 = MagicMock()
    resp1.status_code = 200
    resp1.json.return_value = {"Items": [{"Name": f"G{i}"} for i in range(200)]}
    resp1.raise_for_status = MagicMock()

    resp2 = MagicMock()
    resp2.raise_for_status.side_effect = requests.exceptions.ConnectionError("fail")

    mock_get.side_effect = [resp1, resp2]
    result = _fetch_jellyfin_endpoint("http://jf", "key", "Genres")
    assert len(result) == 200


# _fetch_jellyfin_endpoint pagination (line 259)
@patch('jellyfin.requests.get')
@pytest.mark.usefixtures("temp_config")
def test_fetch_jellyfin_endpoint_pagination(mock_get, client):
    resp1 = MagicMock()
    resp1.status_code = 200
    resp1.json.return_value = {"Items": [{"Name": f"G{i}"} for i in range(200)]}
    resp1.raise_for_status = MagicMock()

    resp2 = MagicMock()
    resp2.status_code = 200
    resp2.json.return_value = {"Items": [{"Name": "G200"}], "TotalRecordCount": 201}
    resp2.raise_for_status = MagicMock()

    mock_get.side_effect = [resp1, resp2]
    result = _fetch_jellyfin_endpoint("http://jf", "key", "Genres")
    assert len(result) == 201


# Metadata unexpected exception (lines 318-319)
@patch('routes.ThreadPoolExecutor')
@pytest.mark.usefixtures("temp_config")
def test_get_jellyfin_metadata_exception(mock_pool, client):
    save_config({"jellyfin_url": "http://test", "api_key": "key"})
    mock_pool.side_effect = RuntimeError("Pool fail")
    response = client.get('/api/jellyfin/metadata')
    assert response.status_code == 500


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


# Preview grouping invalid body (line 485)
@pytest.mark.usefixtures("temp_config")
def test_preview_grouping_invalid_body(client):
    save_config({"jellyfin_url": "http://t", "api_key": "k"})
    response = client.post('/api/grouping/preview', data="not json")
    assert response.status_code == 400
    assert "Request body must be JSON" in response.get_json()["message"]


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


# Cleanup delete_virtual_folder error (lines 606-609)
@patch('routes.delete_virtual_folder')
@patch('routes.os.path.exists')
@pytest.mark.usefixtures("temp_config")
def test_perform_cleanup_delete_virtual_folder_error(mock_exists, mock_delete, client, tmp_path):
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
    mock_delete.side_effect = requests.exceptions.RequestException("Jellyfin error")
    response = client.post('/api/cleanup', json={"folders": ["Action"]})
    assert response.status_code == 200
    assert response.get_json()["deleted"] == 1


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
@patch('routes.os.path.ismount')
@pytest.mark.usefixtures("temp_config")
def test_auto_detect_timeout(mock_ismount, mock_isdir, mock_walk, mock_time, mock_fetch, client):
    save_config({"jellyfin_url": "http://test", "api_key": "key"})
    mock_fetch.return_value = [{"Path": "/media/movies/M1.mkv"}]
    mock_isdir.return_value = True
    mock_ismount.return_value = False
    # walk_start=0, first tuple=0, second tuple=100 (triggers timeout), rest=0
    mock_time.side_effect = [0, 0, 100, 0, 0, 0, 0, 0, 0, 0]
    mock_walk.return_value = [
        ("/home", ["sub"], ["other.mkv"]),
        ("/home/sub", [], ["M1.mkv"]),
    ]
    response = client.post('/api/jellyfin/auto-detect-paths')
    assert response.status_code == 200
    assert mock_time.call_count >= 3


# Auto-detect: file limit (lines 707-709)
@patch('routes.fetch_jellyfin_items')
@patch('routes.os.walk')
@patch('routes.os.path.isdir')
@patch('routes.os.path.ismount')
@pytest.mark.usefixtures("temp_config")
def test_auto_detect_file_limit(mock_ismount, mock_isdir, mock_walk, mock_fetch, client):
    save_config({"jellyfin_url": "http://test", "api_key": "key"})
    mock_fetch.return_value = [{"Path": "/media/movies/M1.mkv"}]
    mock_isdir.return_value = True
    mock_ismount.return_value = False
    # 50_001 files to exceed the 50_000 limit; target filename not present
    mock_walk.return_value = [("/home", ["sub"], ["f"] * 50001)]
    response = client.post('/api/jellyfin/auto-detect-paths')
    assert response.status_code == 200


# Auto-detect: depth limit (lines 715-716)
@patch('routes.fetch_jellyfin_items')
@patch('routes.os.walk')
@patch('routes.os.path.isdir')
@patch('routes.os.path.ismount')
@pytest.mark.usefixtures("temp_config")
def test_auto_detect_depth_limit(mock_ismount, mock_isdir, mock_walk, mock_fetch, client):
    save_config({"jellyfin_url": "http://test", "api_key": "key"})
    mock_fetch.return_value = [{"Path": "/media/movies/M1.mkv"}]
    mock_isdir.return_value = True
    mock_ismount.return_value = False
    deep_path = "/a/b/c/d/e/f/g"
    # target filename not present so depth check is reached before match
    mock_walk.return_value = [(deep_path, [], ["other.mkv"])]
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


# Test results successful read (line 823)
@patch('routes.os.path.exists')
@patch('builtins.open')
def test_get_test_results_success(mock_open, mock_exists, client):
    mock_exists.return_value = True
    mock_file = MagicMock()
    mock_file.read.return_value = "test output"
    mock_open.return_value.__enter__ = MagicMock(return_value=mock_file)
    mock_open.return_value.__exit__ = MagicMock(return_value=False)
    response = client.get('/api/test/results')
    assert response.status_code == 200
    data = response.get_json()
    assert "test output" in data["results"].values()


def test_handle_config_error_non_http():
    with pytest.raises(Exception, match="not http"):
        _handle_config_error(Exception("not http"))


def test_handle_config_error_http_none_code():
    exc = HTTPException()
    exc.code = None
    with pytest.raises(HTTPException):
        _handle_config_error(exc)


# run_tests production mode (line 838-845)
@patch('routes.current_app')
def test_run_tests_production(mock_app, client):
    mock_app.debug = False
    response = client.post('/api/test/run')
    assert response.status_code == 403


# --- Remaining branch coverage for routes.py ---

def test_csrf_protection_with_header(client):
    from flask import current_app
    old_testing = current_app.testing
    current_app.testing = False
    try:
        response = client.post(
            '/api/config',
            json={"jellyfin_url": "http://test"},
            headers={"X-Requested-With": "XMLHttpRequest"}
        )
        # CSRF passes, so we get the normal handler response (200), not 403
        assert response.status_code == 200
    finally:
        current_app.testing = old_testing


@pytest.mark.usefixtures("temp_config")
def test_update_config_valid_cron(client):
    response = client.post('/api/config', json={
        "scheduler": {
            "global_enabled": True,
            "global_schedule": "0 0 * * *",
            "cleanup_enabled": True,
            "cleanup_schedule": "0 1 * * *",
        },
        "groups": [{"name": "Test", "schedule_enabled": True, "schedule": "0 2 * * *"}],
    })
    assert response.status_code == 200


@pytest.mark.usefixtures("temp_config")
def test_update_config_group_schedule_disabled(client):
    response = client.post('/api/config', json={
        "groups": [{"name": "Test", "schedule_enabled": False, "schedule": "bad"}],
    })
    assert response.status_code == 200


@pytest.mark.usefixtures("temp_config")
def test_perform_cleanup_folder_not_found(client, tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    save_config({"target_path": str(target)})
    response = client.post('/api/cleanup', json={"folders": ["NonExistent"]})
    assert response.status_code == 200
    data = response.get_json()
    assert data["deleted"] == 0


@patch('routes.os.path.exists')
@pytest.mark.usefixtures("temp_config")
def test_perform_cleanup_auto_create_missing_settings(mock_exists, client, tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    (target / "Action").mkdir()
    save_config({
        "target_path": str(target),
        "auto_create_libraries": True,
        "jellyfin_url": "",
        "api_key": "",
    })
    mock_exists.return_value = True
    response = client.post('/api/cleanup', json={"folders": ["Action"]})
    assert response.status_code == 200
    assert response.get_json()["deleted"] == 1


@patch('routes.fetch_jellyfin_items')
@patch('routes.os.walk')
@patch('routes.os.path.isdir')
@patch('routes.os.path.ismount')
@pytest.mark.usefixtures("temp_config")
def test_auto_detect_no_common_path(mock_ismount, mock_isdir, mock_walk, mock_fetch, client):
    save_config({"jellyfin_url": "http://test", "api_key": "key"})
    # Jellyfin path has a matching filename but no real common prefix
    mock_fetch.return_value = [{"Path": "/jf/unique/movie.mkv"}]
    mock_isdir.return_value = True
    mock_ismount.return_value = False
    # Walk finds the same filename — at minimum the basename matches,
    # so common_count is at least 1. This still exercises the path
    # translation logic with a minimal common prefix.
    mock_walk.return_value = [("/home", [], ["movie.mkv"])]
    response = client.post('/api/jellyfin/auto-detect-paths')
    assert response.status_code == 200
    data = response.get_json()
    # Basename match means common_count=1, so j_root loses just the basename
    assert data["detected"]["media_path_in_jellyfin"] == "/jf/unique"


# run_tests subprocess exception (lines 843-845)
@patch('routes.current_app')
@patch('subprocess.run')
def test_run_tests_subprocess_exception(mock_subprocess, mock_app, client):
    mock_app.debug = True
    mock_subprocess.side_effect = OSError("Subprocess fail")
    response = client.post('/api/test/run')
    assert response.status_code == 500
    assert "Subprocess fail" in response.get_json()["message"]


# run_tests success (line 842)
@patch('subprocess.run')
def test_run_tests_success(mock_run, client, app):
    app.debug = True
    response = client.post('/api/test/run')
    assert response.status_code == 200
    assert "Tests executed successfully." in response.get_json()["message"]


def test_compute_common_root_no_match():
    assert _compute_common_root("/a/b/c", "/x/y/z") == (None, None)


def test_compute_common_root_single_match():
    assert _compute_common_root("/a/b/c", "/x/b/c") == ("/a", "/x")


def test_compute_common_root_full_match():
    assert _compute_common_root("/a/b/c", "/a/b/c") == (os.sep, os.sep)
