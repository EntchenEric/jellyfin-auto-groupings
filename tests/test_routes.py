"""Tests for all Flask route handlers in routes.py.

Covers config CRUD, Jellyfin API proxy endpoints, sync/preview,
cleanup, file browsing, path auto-detection, authentication,
CSRF protection, and error handling — all with mocked dependencies.
"""

import os
from datetime import UTC
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests
from werkzeug.exceptions import BadRequest, HTTPException

from config import save_config
from routes import (
    MAX_B64_SIZE,
    _compute_common_root,
    _fetch_jellyfin_endpoint,
    _get_jellyfin_config,
    _handle_http_error,
)


@pytest.mark.usefixtures("temp_config")
def test_get_config(client) -> None:
    response = client.get("/api/config")
    assert response.status_code == 200
    data = response.get_json()
    assert "jellyfin_url" in data


@pytest.mark.usefixtures("temp_config")
def test_get_config_masks_secrets(client) -> None:
    from config import save_config

    save_config(
        {
            "jellyfin_url": "http://jf",
            "api_key": "secret-key",
            "trakt_client_id": "trakt-id",
            "tmdb_api_key": "tmdb-key",
            "mal_client_id": "mal-id",
            "groups": [],
        },
    )
    response = client.get("/api/config")
    data = response.get_json()
    assert data["api_key"] == "****"
    assert data["trakt_client_id"] == "****"
    assert data["tmdb_api_key"] == "****"
    assert data["mal_client_id"] == "****"


@patch("routes.run_sync", return_value=[])
def test_sync_rate_limit(mock_run_sync, client) -> None:
    first = client.post("/api/sync", headers={"X-Requested-With": "XMLHttpRequest"})
    assert first.status_code == 200
    second = client.post("/api/sync", headers={"X-Requested-With": "XMLHttpRequest"})
    assert second.status_code == 429
    mock_run_sync.assert_called_once()


@pytest.mark.usefixtures("temp_config")
def test_update_config(client) -> None:
    new_cfg = {"jellyfin_url": "http://new-url", "api_key": "new-key"}
    response = client.post("/api/config", json=new_cfg)
    assert response.status_code == 200

    # Verify it was saved
    response = client.get("/api/config")
    data = response.get_json()
    assert data["jellyfin_url"] == "http://new-url"


@patch("routes.network.get")
def test_test_server_success(mock_get, client) -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_get.return_value = mock_response

    response = client.post(
        "/api/test-server",
        json={"jellyfin_url": "http://test", "api_key": "key"},
    )
    assert response.status_code == 200
    assert response.get_json()["status"] == "success"
    assert "successfully" in response.get_json()["message"]


@patch("routes.network.get")
def test_test_server_failure(mock_get, client) -> None:
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_get.return_value = mock_response

    response = client.post(
        "/api/test-server",
        json={"jellyfin_url": "http://test", "api_key": "wrong"},
    )
    assert response.status_code == 400
    assert response.get_json()["status"] == "error"


def test_browse_directory(client) -> None:
    # Test with home directory
    response = client.get("/api/browse")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "success"
    assert "dirs" in data


@patch("routes.network.get")
@pytest.mark.usefixtures("temp_config")
def test_get_jellyfin_metadata(mock_get, client) -> None:
    save_config({"jellyfin_url": "http://test", "api_key": "key"})

    def mock_genres(url, **kwargs):
        m = MagicMock()
        if "Genres" in url:
            m.json.return_value = {
                "Items": [{"Name": "Action"}, {"Name": "Comedy"}],
                "TotalRecordCount": 2,
            }
        elif "Studios" in url:
            m.json.return_value = {
                "Items": [{"Name": "Studio A"}],
                "TotalRecordCount": 1,
            }
        elif "Persons" in url:
            m.json.return_value = {
                "Items": [{"Name": "Actor A"}],
                "TotalRecordCount": 1,
            }
        elif "Tags" in url:
            m.json.return_value = {"Items": [{"Name": "4K"}], "TotalRecordCount": 1}
        else:
            m.json.return_value = {"Items": [], "TotalRecordCount": 0}
        m.raise_for_status = MagicMock()
        return m

    mock_get.side_effect = mock_genres

    response = client.get("/api/jellyfin/metadata")
    assert response.status_code == 200
    data = response.get_json()
    assert "Action" in data["metadata"]["genre"]
    assert "Comedy" in data["metadata"]["genre"]
    assert "Actor A" in data["metadata"]["actor"]
    assert "Studio A" in data["metadata"]["studio"]
    assert "4K" in data["metadata"]["tag"]


@patch("routes.run_sync")
@pytest.mark.usefixtures("temp_config")
def test_api_sync(mock_sync, client) -> None:
    mock_sync.return_value = [{"group": "G1", "links": 5}]
    response = client.post("/api/sync")
    assert response.status_code == 200
    data = response.get_json()
    assert data["results"][0]["group"] == "G1"


def test_upload_cover_security_check(client) -> None:
    # Test with payload exceeding MAX_B64_SIZE
    large_data = "data:image/jpeg;base64," + "a" * (MAX_B64_SIZE + 1024 * 1024)
    response = client.post(
        "/api/upload_cover",
        json={"group_name": "G", "image": large_data},
    )
    assert response.status_code == 413


@patch("routes._get_cover_path")
def test_upload_cover_success(mock_get_path, client, tmp_path) -> None:
    mock_get_path.return_value = str(tmp_path / "test.jpg")
    # Base64 for a tiny transparent pixel
    img_data = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    response = client.post(
        "/api/upload_cover",
        json={"group_name": "Test Group", "image": img_data},
    )
    assert response.status_code == 200
    assert (tmp_path / "test.jpg").exists()


@pytest.mark.usefixtures("temp_config")
def test_save_config_route(client) -> None:
    new_cfg = {"jellyfin_url": "http://new", "api_key": "new_key"}
    response = client.post("/api/config", json=new_cfg)
    assert response.status_code == 200
    assert response.get_json()["config"]["jellyfin_url"] == "http://new"


@patch("routes.fetch_jellyfin_items")
@pytest.mark.usefixtures("temp_config")
def test_auto_detect_paths(mock_fetch, client) -> None:
    save_config({"jellyfin_url": "http://test", "api_key": "key"})
    mock_fetch.return_value = [{"Path": "/data/Movies/M1.mkv"}]

    with patch("os.walk") as mock_walk:
        mock_walk.return_value = [
            ("/home/user/Movies", [], ["M1.mkv"]),
        ]
        response = client.post("/api/jellyfin/auto-detect-paths")
        assert response.status_code == 200
        data = response.get_json()
        assert data["detected"]["media_path_on_host"] == "/home/user"


@patch("routes.preview_group")
@pytest.mark.usefixtures("temp_config")
def test_preview_grouping(mock_preview, client) -> None:
    save_config({"jellyfin_url": "http://test", "api_key": "key"})
    mock_preview.return_value = ([{"Name": "M1"}], None, 200)

    # Simple
    response = client.post(
        "/api/grouping/preview",
        json={"type": "genre", "value": "Action"},
    )
    assert response.status_code == 200
    assert response.get_json()["count"] == 1


@patch("routes.run_sync")
@pytest.mark.usefixtures("temp_config")
def test_preview_all_sync(mock_sync, client) -> None:
    mock_sync.return_value = [{"group": "G1", "links": 5}]
    response = client.post("/api/sync/preview_all")
    assert response.status_code == 200
    assert "Preview" in response.get_json()["message"]


def test_index(client) -> None:
    response = client.get("/")
    assert response.status_code == 200


def test_browse_security(client) -> None:
    # Test disallowed path
    response = client.get("/api/browse?path=/etc")
    assert response.status_code == 403


def test_update_config_non_dict(client) -> None:
    response = client.post(
        "/api/config",
        data="not json",
        content_type="application/json",
    )
    assert response.status_code == 400


@patch("routes.update_scheduler_jobs")
@pytest.mark.usefixtures("temp_config")
def test_update_config_scheduler_fail(mock_sched, client) -> None:
    mock_sched.side_effect = RuntimeError("Fail")
    response = client.post("/api/config", json={"jellyfin_url": "http://jf"})
    assert response.status_code == 500
    data = response.get_json()
    assert data["status"] == "error"
    assert "scheduler could not be updated" in data["message"]
    assert "config" in data


def test_test_server_invalid_body(client) -> None:
    response = client.post("/api/test-server", data="not json")
    assert response.status_code == 400


def test_test_server_missing_fields(client) -> None:
    response = client.post("/api/test-server", json={"url": "missing key"})
    assert response.status_code == 400


def test_test_server_null_fields(client) -> None:
    response = client.post(
        "/api/test-server",
        json={"jellyfin_url": None, "api_key": None},
    )
    assert response.status_code == 400


@patch("routes.network.get")
def test_test_server_exception(mock_get, client) -> None:
    mock_get.side_effect = requests.exceptions.ConnectionError("Failed")
    response = client.post(
        "/api/test-server",
        json={"jellyfin_url": "http://test", "api_key": "key"},
    )
    assert response.status_code == 400
    assert "Connection error" in response.get_json()["message"]


@pytest.mark.usefixtures("temp_config")
def test_get_jellyfin_metadata_no_config(client) -> None:
    # Config is empty by default in temp_config if we don't save anything
    response = client.get("/api/jellyfin/metadata")
    assert response.status_code == 400


@patch("routes.network.get")
@pytest.mark.usefixtures("temp_config")
def test_get_jellyfin_metadata_error(mock_get, client) -> None:
    save_config({"jellyfin_url": "http://test", "api_key": "key"})
    mock_get.side_effect = requests.exceptions.ConnectionError("Fetch failed")
    response = client.get("/api/jellyfin/metadata")
    assert response.status_code == 400


def test_upload_cover_invalid_json(client) -> None:
    response = client.post("/api/upload_cover", data="bad")
    assert response.status_code == 400


def test_upload_cover_bad_format(client) -> None:
    response = client.post(
        "/api/upload_cover",
        json={"group_name": "G", "image": "not-data-uri"},
    )
    assert response.status_code == 400


@patch("routes.save_config")
@pytest.mark.usefixtures("temp_config")
def test_update_config_error(mock_save, client) -> None:
    mock_save.side_effect = OSError("Disk full")
    response = client.post("/api/config", json={"jellyfin_url": "http://u"})
    assert response.status_code == 500


@pytest.mark.usefixtures("temp_config")
def test_preview_grouping_missing_type(client) -> None:
    save_config({"jellyfin_url": "http://t", "api_key": "k"})
    response = client.post("/api/grouping/preview", json={"value": "V"})
    assert response.status_code == 400


@pytest.mark.usefixtures("temp_config")
def test_preview_grouping_invalid_type(client) -> None:
    save_config({"jellyfin_url": "http://t", "api_key": "k"})
    response = client.post(
        "/api/grouping/preview",
        json={"type": "invalid", "value": "V"},
    )
    assert response.status_code == 400


@patch("routes.preview_group")
@pytest.mark.usefixtures("temp_config")
def test_preview_grouping_error(mock_preview, client) -> None:
    save_config({"jellyfin_url": "http://t", "api_key": "k"})
    mock_preview.return_value = ([], "Error occurred", 500)
    response = client.post(
        "/api/grouping/preview",
        json={"type": "genre", "value": "Action"},
    )
    assert response.status_code == 500


@patch("routes.fetch_jellyfin_items")
@pytest.mark.usefixtures("temp_config")
def test_auto_detect_no_media(mock_fetch, client) -> None:
    save_config({"jellyfin_url": "http://t", "api_key": "k"})
    mock_fetch.return_value = []
    response = client.post("/api/jellyfin/auto-detect-paths")
    assert response.status_code == 400


@patch("routes.Path.iterdir")
def test_browse_directory_oserror(mock_iterdir, client) -> None:
    mock_iterdir.side_effect = OSError("IO Error")
    response = client.get("/api/browse")
    assert response.status_code == 400


def test_update_config_invalid_cron(client) -> None:
    response = client.post(
        "/api/config",
        json={
            "scheduler": {"global_enabled": True, "global_schedule": "invalid"},
        },
    )
    assert response.status_code == 400
    data = response.get_json()
    assert data["status"] == "error"
    assert "Invalid cron" in data["message"]


def test_update_config_invalid_group_cron(client) -> None:
    response = client.post(
        "/api/config",
        json={
            "groups": [
                {"name": "Test", "schedule_enabled": True, "schedule": "* * * * * *"},
            ],
        },
    )
    assert response.status_code == 400
    data = response.get_json()
    assert data["status"] == "error"


# ---------------------------------------------------------------------------
# get_jellyfin_users
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("temp_config")
def test_get_jellyfin_users_no_config(client) -> None:
    response = client.get("/api/jellyfin/users")
    assert response.status_code == 400


@patch("routes.get_users")
@pytest.mark.usefixtures("temp_config")
def test_get_jellyfin_users_success(mock_get_users, client) -> None:
    save_config({"jellyfin_url": "http://test", "api_key": "key"})
    mock_get_users.return_value = [{"Id": "1", "Name": "User A"}]
    response = client.get("/api/jellyfin/users")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "success"
    assert data["users"][0]["name"] == "User A"


@patch("routes.get_users")
@pytest.mark.usefixtures("temp_config")
def test_get_jellyfin_users_exception(mock_get_users, client) -> None:
    save_config({"jellyfin_url": "http://test", "api_key": "key"})
    mock_get_users.side_effect = RuntimeError("Jellyfin down")
    response = client.get("/api/jellyfin/users")
    assert response.status_code == 400
    assert response.get_json()["status"] == "error"


# Invalid configuration format (line 278)
@patch("routes.load_config")
def test_get_jellyfin_metadata_invalid_config(mock_load, client) -> None:
    mock_load.return_value = "bad"
    response = client.get("/api/jellyfin/metadata")
    assert response.status_code == 500
    assert "Invalid configuration format" in response.get_json()["message"]


# Invalid configuration format (line 336)
@patch("routes.load_config")
def test_get_jellyfin_users_invalid_config(mock_load, client) -> None:
    mock_load.return_value = "bad"
    response = client.get("/api/jellyfin/users")
    assert response.status_code == 500
    assert "Invalid configuration format" in response.get_json()["message"]


# ---------------------------------------------------------------------------
# upload_cover edge cases
# ---------------------------------------------------------------------------


def test_upload_cover_missing_fields(client) -> None:
    response = client.post("/api/upload_cover", json={"group_name": "G"})
    assert response.status_code == 400


def test_upload_cover_invalid_image_data(client) -> None:
    response = client.post(
        "/api/upload_cover",
        json={"group_name": "G", "image": "plain-text"},
    )
    assert response.status_code == 400


def test_upload_cover_malformed_data_url(client) -> None:
    # Starts with data:image/ but has no comma -> ValueError from split
    response = client.post(
        "/api/upload_cover",
        json={"group_name": "G", "image": "data:image/png;base64_NO_COMMA"},
    )
    assert response.status_code == 400
    assert "Malformed image data" in response.get_json()["message"]


def test_upload_cover_invalid_base64(client) -> None:
    # Invalid base64 characters trigger binascii.Error
    response = client.post(
        "/api/upload_cover",
        json={"group_name": "G", "image": "data:image/png;base64,!!!invalid!!!"},
    )
    assert response.status_code == 400
    assert "Malformed image data" in response.get_json()["message"]


@patch("routes._get_cover_path")
def test_upload_cover_server_error(mock_get_cover, client) -> None:
    mock_get_cover.side_effect = OSError("Disk full")
    img_data = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    response = client.post(
        "/api/upload_cover",
        json={"group_name": "G", "image": img_data},
    )
    assert response.status_code == 500
    assert response.get_json()["status"] == "error"


@patch("routes._get_cover_path")
def test_upload_cover_unresolvable_path(mock_get_cover, client) -> None:
    mock_get_cover.return_value = None
    img_data = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    response = client.post(
        "/api/upload_cover",
        json={"group_name": "G", "image": img_data},
    )
    assert response.status_code == 500
    assert "Could not resolve cover storage path" in response.get_json()["message"]


def test_upload_cover_unsupported_mime(client) -> None:
    """Upload with an unsupported MIME type returns 400."""
    response = client.post(
        "/api/upload_cover",
        json={
            "group_name": "G",
            "image": "data:image/bmp;base64,AAAA",
        },
    )
    assert response.status_code == 400
    data = response.get_json()
    assert "Unsupported image type" in data["message"]
    assert "image/bmp" in data["message"]


def test_upload_cover_mime_extension_mapping(client, tmp_path) -> None:
    """Upload with a non-JPEG MIME type uses the correct file extension."""
    from config import save_config
    from routes import _get_cover_path

    save_config({"target_path": str(tmp_path)})
    img_data = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    response = client.post(
        "/api/upload_cover",
        json={"group_name": "TestGroup", "image": img_data},
    )
    assert response.status_code == 200
    # Verify the file was saved with .png extension
    cover_path = _get_cover_path(
        "TestGroup", str(tmp_path), check_exists=False, ext="png"
    )
    assert cover_path is not None
    assert Path(cover_path).exists()
    assert cover_path.endswith(".png")


# ---------------------------------------------------------------------------
# health_check edge cases
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("temp_config")
def test_health_check_error_path(client) -> None:
    """Health check returns 500 with generic error when config loading fails."""
    with patch("routes.load_config", side_effect=RuntimeError("config corrupt")):
        response = client.get("/api/health")
    assert response.status_code == 500
    data = response.get_json()
    assert data["status"] == "error"
    assert data["healthcheck"]["ok"] is False
    # Must not leak internal exception text
    assert data["healthcheck"]["error"] == "internal_error"


@pytest.mark.usefixtures("temp_config")
def test_health_check_scheduler_running(client) -> None:
    """Health check includes scheduler info when scheduler is running."""
    from unittest.mock import PropertyMock

    from apscheduler.job import Job

    mock_job = MagicMock(spec=Job)
    mock_job.id = "sync_job_1"
    mock_job.name = "sync_groups"
    mock_job.next_run_time = None

    with (
        patch("routes._scheduler") as mock_sched,
        patch("routes.network.get") as mock_get,
    ):
        type(mock_sched).running = PropertyMock(return_value=True)
        mock_sched.get_jobs.return_value = [mock_job]
        mock_get.return_value.status_code = 200

        response = client.get("/api/health")

    assert response.status_code == 200
    data = response.get_json()
    assert data["scheduler"]["running"] is True
    assert data["scheduler"]["job_count"] == 1
    assert len(data["scheduler"]["next_run_times"]) == 1
    assert data["scheduler"]["next_run_times"][0]["id"] == "sync_job_1"
    assert data["scheduler"]["next_run_times"][0]["name"] == "sync_groups"
    assert "next_run" not in data["scheduler"]["next_run_times"][0]


@pytest.mark.usefixtures("temp_config")
def test_health_check_scheduler_job_exception_skipped(client) -> None:
    """Health check skips jobs that raise during attribute access."""
    from unittest.mock import PropertyMock

    from apscheduler.job import Job

    good_job = MagicMock(spec=Job)
    good_job.id = "good_job"
    good_job.name = "good"
    good_job.next_run_time = None

    # A job whose .next_run_time.isoformat() raises
    class BadJob:
        @property
        def id(self):
            return "bad_job"

        @property
        def name(self):
            return "bad"

        @property
        def next_run_time(self):
            class BadTime:
                def isoformat(self):
                    msg = "isoformat error"
                    raise RuntimeError(msg)

            return BadTime()

    bad_job = BadJob()

    with (
        patch("routes._scheduler") as mock_sched,
        patch("routes.network.get") as mock_get,
    ):
        type(mock_sched).running = PropertyMock(return_value=True)
        mock_sched.get_jobs.return_value = [good_job, bad_job]
        mock_get.return_value.status_code = 200

        response = client.get("/api/health")

    assert response.status_code == 200
    data = response.get_json()
    assert data["scheduler"]["running"] is True
    assert data["scheduler"]["job_count"] == 2
    # Only the good job should appear in next_run_times
    assert len(data["scheduler"]["next_run_times"]) == 1
    assert data["scheduler"]["next_run_times"][0]["id"] == "good_job"


@pytest.mark.usefixtures("temp_config")
def test_health_check_scheduler_job_with_next_run(client) -> None:
    """Health check includes next_run_time when job has one."""
    from datetime import datetime
    from unittest.mock import PropertyMock

    from apscheduler.job import Job

    mock_job = MagicMock(spec=Job)
    mock_job.id = "sync_job_2"
    mock_job.name = "nightly_sync"
    mock_job.next_run_time = datetime(2026, 6, 16, 2, 0, 0, tzinfo=UTC)

    with (
        patch("routes._scheduler") as mock_sched,
        patch("routes.network.get") as mock_get,
    ):
        type(mock_sched).running = PropertyMock(return_value=True)
        mock_sched.get_jobs.return_value = [mock_job]
        mock_get.return_value.status_code = 200

        response = client.get("/api/health")

    assert response.status_code == 200
    data = response.get_json()
    assert data["scheduler"]["running"] is True
    assert (
        data["scheduler"]["next_run_times"][0]["next_run"]
        == "2026-06-16T02:00:00+00:00"
    )


@pytest.mark.usefixtures("temp_config")
def test_health_check_scheduler_not_running(client) -> None:
    """Health check reports scheduler not running when scheduler is off."""
    from unittest.mock import PropertyMock

    with (
        patch("routes._scheduler") as mock_sched,
        patch("routes.network.get") as mock_get,
    ):
        type(mock_sched).running = PropertyMock(return_value=False)
        mock_get.return_value.status_code = 200

        response = client.get("/api/health")

    assert response.status_code == 200
    data = response.get_json()
    assert data["scheduler"]["running"] is False
    assert data["scheduler"]["job_count"] == 0


@pytest.mark.usefixtures("temp_config")
def test_health_check_scheduler_exception(client) -> None:
    """Health check gracefully handles scheduler exception."""
    with (
        patch("routes._scheduler") as mock_sched,
        patch("routes.network.get") as mock_get,
    ):
        mock_sched.get_jobs.side_effect = RuntimeError("scheduler error")
        mock_get.return_value.status_code = 200

        response = client.get("/api/health")

    assert response.status_code == 200
    data = response.get_json()
    # The scheduler block is entered (hasattr succeeds on MagicMock),
    # running is set to True, then get_jobs() raises, so job_count stays 0
    assert data["scheduler"]["running"] is True
    assert data["scheduler"]["job_count"] == 0


@pytest.mark.usefixtures("temp_config")
def test_health_check_jellyfin_reachable(client) -> None:
    """Health check reports Jellyfin reachable when ping succeeds."""
    save_config({"jellyfin_url": "http://jellyfin:8096", "api_key": "test"})
    with patch("routes.network.get") as mock_get:
        mock_get.return_value.status_code = 200
        response = client.get("/api/health")

    assert response.status_code == 200
    data = response.get_json()
    assert data["jellyfin"]["reachable"] is True


@pytest.mark.usefixtures("temp_config")
def test_health_check_jellyfin_unreachable(client) -> None:
    """Health check reports Jellyfin unreachable when ping fails."""
    save_config({"jellyfin_url": "http://jellyfin:8096", "api_key": "test"})
    with patch("routes.network.get", side_effect=requests.RequestException("timeout")):
        response = client.get("/api/health")

    assert response.status_code == 200
    data = response.get_json()
    assert data["jellyfin"]["reachable"] is False


@pytest.mark.usefixtures("temp_config")
def test_health_check_jellyfin_no_url(client) -> None:
    """Health check returns None for reachable when no URL configured."""
    save_config({"jellyfin_url": "", "api_key": "", "target_path": ""})
    response = client.get("/api/health")

    assert response.status_code == 200
    data = response.get_json()
    assert data["jellyfin"]["reachable"] is None
    assert data["healthcheck"]["configured"] is False


# ---------------------------------------------------------------------------
# get_cleanup_items
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("temp_config")
def test_get_cleanup_items_no_target_path(client) -> None:
    save_config({"target_path": ""})
    response = client.get("/api/cleanup")
    assert response.status_code == 200
    assert response.get_json()["items"] == []


@pytest.mark.usefixtures("temp_config")
def test_get_cleanup_items_with_groups(client, tmp_path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / "Action").mkdir()
    (target / ".hidden").mkdir()
    save_config(
        {
            "target_path": str(target),
            "groups": [{"name": "Action"}],
        },
    )
    response = client.get("/api/cleanup")
    assert response.status_code == 200
    data = response.get_json()
    assert len(data["items"]) == 1
    assert data["items"][0]["name"] == "Action"
    assert data["items"][0]["is_configured"] is True


@patch("routes.Path.iterdir")
@pytest.mark.usefixtures("temp_config")
def test_get_cleanup_items_oserror(mock_iterdir, client, tmp_path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    save_config({"target_path": str(target)})
    mock_iterdir.side_effect = OSError("Permission denied")
    response = client.get("/api/cleanup")
    assert response.status_code == 500


# ---------------------------------------------------------------------------
# perform_cleanup
# ---------------------------------------------------------------------------


def test_perform_cleanup_invalid_json(client) -> None:
    response = client.post("/api/cleanup", data="not json")
    assert response.status_code == 400


def test_perform_cleanup_folders_not_list(client) -> None:
    response = client.post("/api/cleanup", json={"folders": "bad"})
    assert response.status_code == 400


@pytest.mark.usefixtures("temp_config")
def test_perform_cleanup_no_target_path(client) -> None:
    response = client.post("/api/cleanup", json={"folders": ["Action"]})
    assert response.status_code == 404


@pytest.mark.usefixtures("temp_config")
def test_perform_cleanup_invalid_folder_name(client, tmp_path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    save_config({"target_path": str(target)})
    response = client.post("/api/cleanup", json={"folders": ["../etc", 123, ""]})
    assert response.status_code == 207
    data = response.get_json()
    assert data["status"] == "partial_success"
    assert len(data["errors"]) == 3


@pytest.mark.usefixtures("temp_config")
def test_perform_cleanup_dedup(client, tmp_path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / "Action").mkdir()
    save_config({"target_path": str(target)})
    response = client.post("/api/cleanup", json={"folders": ["Action", "Action"]})
    assert response.status_code == 200
    assert response.get_json()["deleted"] == 1


@pytest.mark.usefixtures("temp_config")
def test_perform_cleanup_success(client, tmp_path) -> None:
    """Test successful folder deletion."""
    target = tmp_path / "target"
    target.mkdir()
    (target / "Action").mkdir()
    save_config({"target_path": str(target)})
    response = client.post(
        "/api/cleanup",
        json={"folders": ["Action"]},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert response.status_code == 200
    assert response.get_json()["deleted"] == 1


# perform_cleanup rmtree OSError (lines 608-609)
@patch("shutil.rmtree")
@pytest.mark.usefixtures("temp_config")
def test_perform_cleanup_rmtree_error(mock_rmtree, client, tmp_path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / "Action").mkdir()
    save_config({"target_path": str(target)})
    mock_rmtree.side_effect = OSError("Permission denied")
    response = client.post("/api/cleanup", json={"folders": ["Action"]})
    assert response.status_code == 207
    data = response.get_json()
    assert data["status"] == "partial_success"
    assert "Permission denied" in data["errors"][0]


# ---------------------------------------------------------------------------
# auto_detect_paths error paths
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("temp_config")
def test_auto_detect_paths_no_config(client) -> None:
    response = client.post("/api/jellyfin/auto-detect-paths")
    assert response.status_code == 400


@patch("routes.fetch_jellyfin_items")
@pytest.mark.usefixtures("temp_config")
def test_auto_detect_paths_fetch_error(mock_fetch, client) -> None:
    save_config({"jellyfin_url": "http://test", "api_key": "key"})
    mock_fetch.side_effect = RuntimeError("Connection refused")
    response = client.post("/api/jellyfin/auto-detect-paths")
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# browse_directory edge cases
# ---------------------------------------------------------------------------


def test_browse_directory_file_fallback(client) -> None:
    # When path is a file, fall back to its parent directory
    home = str(Path("~").expanduser())
    response = client.get(f"/api/browse?path={home}/somefile.txt")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "success"
    assert data["current"] == home


@patch("routes.Path.iterdir")
def test_browse_directory_permission_error(mock_iterdir, client) -> None:
    mock_iterdir.side_effect = PermissionError("No access")
    response = client.get("/api/browse")
    assert response.status_code == 200
    assert response.get_json()["dirs"] == []


# ---------------------------------------------------------------------------
# get_test_results
# ---------------------------------------------------------------------------


def test_get_test_results(client) -> None:
    response = client.get("/api/test/results")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "success"
    assert "results" in data


# ---------------------------------------------------------------------------
# index
# ---------------------------------------------------------------------------


def test_index_html(client) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert b"html" in response.data.lower()


def test_test_dashboard_removed(client) -> None:
    """The /test route was removed along with the stale test.html artifact."""
    response = client.get("/test")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# routes.py coverage improvements
# ---------------------------------------------------------------------------


# CSRF check (lines 47-48)
def test_csrf_protection_non_testing(client) -> None:
    from flask import current_app

    old_testing = current_app.testing
    current_app.testing = False
    try:
        response = client.post("/api/config", json={"jellyfin_url": "http://test"})
        assert response.status_code == 403
        assert "CSRF" in response.get_json()["message"]
    finally:
        current_app.testing = old_testing


# Cleanup schedule validation (lines 121-123)
def test_update_config_invalid_cleanup_cron(client) -> None:
    response = client.post(
        "/api/config",
        json={
            "scheduler": {"cleanup_enabled": True, "cleanup_schedule": "bad"},
        },
    )
    assert response.status_code == 400
    data = response.get_json()
    assert "Cleanup schedule" in data["errors"][0]


# _fetch_jellyfin_endpoint partial data break (line 250)
@patch("jellyfin.network.get")
@pytest.mark.usefixtures("temp_config")
def test_fetch_jellyfin_endpoint_partial_data(mock_get, client) -> None:
    resp1 = MagicMock()
    resp1.status_code = 200
    resp1.json.return_value = {
        "Items": [{"Name": f"G{i}"} for i in range(200)],
        "TotalRecordCount": 201,
    }
    resp1.raise_for_status = MagicMock()

    resp2 = MagicMock()
    resp2.raise_for_status.side_effect = requests.exceptions.ConnectionError("fail")

    mock_get.side_effect = [resp1, resp2]
    result = _fetch_jellyfin_endpoint("http://jf", "key", "Genres")
    assert len(result) == 200


# _fetch_jellyfin_endpoint pagination (line 259)
@patch("jellyfin.network.get")
@pytest.mark.usefixtures("temp_config")
def test_fetch_jellyfin_endpoint_pagination(mock_get, client) -> None:
    resp1 = MagicMock()
    resp1.status_code = 200
    resp1.json.return_value = {
        "Items": [{"Name": f"G{i}"} for i in range(200)],
        "TotalRecordCount": 201,
    }
    resp1.raise_for_status = MagicMock()

    resp2 = MagicMock()
    resp2.status_code = 200
    resp2.json.return_value = {"Items": [{"Name": "G200"}], "TotalRecordCount": 201}
    resp2.raise_for_status = MagicMock()

    mock_get.side_effect = [resp1, resp2]
    result = _fetch_jellyfin_endpoint("http://jf", "key", "Genres")
    assert len(result) == 201


# Metadata unexpected exception (lines 318-319)
@patch("routes.ThreadPoolExecutor")
@pytest.mark.usefixtures("temp_config")
def test_get_jellyfin_metadata_exception(mock_pool, client) -> None:
    save_config({"jellyfin_url": "http://test", "api_key": "key"})
    mock_pool.side_effect = RuntimeError("Pool fail")
    response = client.get("/api/jellyfin/metadata")
    assert response.status_code == 500


# Sync ValueError (lines 438-439)
@patch("routes.run_sync")
@pytest.mark.usefixtures("temp_config")
def test_api_sync_value_error(mock_sync, client) -> None:
    mock_sync.side_effect = ValueError("Bad config")
    response = client.post("/api/sync")
    assert response.status_code == 400
    assert "Bad config" in response.get_json()["message"]


# Sync RuntimeError (lines 440-441)
@patch("routes.run_sync")
@pytest.mark.usefixtures("temp_config")
def test_api_sync_runtime_error(mock_sync, client) -> None:
    mock_sync.side_effect = RuntimeError("Sync failed")
    response = client.post("/api/sync")
    assert response.status_code == 500
    assert "Sync failed" in response.get_json()["message"]


# Preview_all ValueError (lines 465-466)
@patch("routes.run_sync")
@pytest.mark.usefixtures("temp_config")
def test_preview_all_value_error(mock_sync, client) -> None:
    mock_sync.side_effect = ValueError("Bad config")
    response = client.post("/api/sync/preview_all")
    assert response.status_code == 400
    assert "Bad config" in response.get_json()["message"]


# Preview_all RuntimeError (lines 467-468)
@patch("routes.run_sync")
@pytest.mark.usefixtures("temp_config")
def test_preview_all_runtime_error(mock_sync, client) -> None:
    mock_sync.side_effect = RuntimeError("Sync failed")
    response = client.post("/api/sync/preview_all")
    assert response.status_code == 500
    assert "Sync failed" in response.get_json()["message"]


# Preview grouping missing value (lines 485, 510, 514)
@pytest.mark.usefixtures("temp_config")
def test_preview_grouping_missing_value(client) -> None:
    save_config({"jellyfin_url": "http://t", "api_key": "k"})
    response = client.post("/api/grouping/preview", json={"type": "genre"})
    assert response.status_code == 400


@pytest.mark.usefixtures("temp_config")
def test_preview_grouping_value_not_string(client) -> None:
    save_config({"jellyfin_url": "http://t", "api_key": "k"})
    response = client.post(
        "/api/grouping/preview",
        json={"type": "genre", "value": 123},
    )
    assert response.status_code == 400


@pytest.mark.usefixtures("temp_config")
def test_preview_grouping_empty_value(client) -> None:
    save_config({"jellyfin_url": "http://t", "api_key": "k"})
    response = client.post(
        "/api/grouping/preview",
        json={"type": "genre", "value": "   "},
    )
    assert response.status_code == 400


# Preview grouping invalid body (line 485)
@pytest.mark.usefixtures("temp_config")
def test_preview_grouping_invalid_body(client) -> None:
    save_config({"jellyfin_url": "http://t", "api_key": "k"})
    response = client.post("/api/grouping/preview", data="not json")
    assert response.status_code == 400
    assert "Request body must be JSON" in response.get_json()["message"]


@patch("routes.preview_group")
@pytest.mark.usefixtures("temp_config")
def test_preview_grouping_imdb_list(mock_preview, client) -> None:
    """Preview with imdb_list type is accepted and forwards correctly."""
    mock_preview.return_value = ([{"Name": "M1"}], None, 200)
    save_config({"jellyfin_url": "http://t", "api_key": "k"})
    response = client.post(
        "/api/grouping/preview",
        json={"type": "imdb_list", "value": "ls000000001"},
    )
    assert response.status_code == 200
    assert response.get_json()["count"] == 1
    mock_preview.assert_called_once()
    args, _kwargs = mock_preview.call_args
    # type_name and val are positional args in preview_group()
    assert args[0] == "imdb_list"
    assert args[1] == "ls000000001"


@patch("routes.preview_group")
@pytest.mark.usefixtures("temp_config")
def test_preview_grouping_trakt_list(mock_preview, client) -> None:
    """Preview with trakt_list type forwards trakt_client_id."""
    mock_preview.return_value = ([{"Name": "M1"}], None, 200)
    save_config(
        {
            "jellyfin_url": "http://t",
            "api_key": "k",
            "trakt_client_id": "test_client_id",
        }
    )
    response = client.post(
        "/api/grouping/preview",
        json={"type": "trakt_list", "value": "https://trakt.tv/users/foo/lists/bar"},
    )
    assert response.status_code == 200
    assert response.get_json()["count"] == 1
    mock_preview.assert_called_once()
    args, kwargs = mock_preview.call_args
    assert args[0] == "trakt_list"
    assert args[1] == "https://trakt.tv/users/foo/lists/bar"
    assert kwargs["trakt_client_id"] == "test_client_id"
    assert kwargs["tmdb_api_key"] == ""
    assert kwargs["mal_client_id"] == ""


@patch("routes.preview_group")
@pytest.mark.usefixtures("temp_config")
def test_preview_grouping_tmdb_list(mock_preview, client) -> None:
    """Preview with tmdb_list type forwards tmdb_api_key."""
    mock_preview.return_value = ([{"Name": "M1"}], None, 200)
    save_config(
        {
            "jellyfin_url": "http://t",
            "api_key": "k",
            "tmdb_api_key": "test_key",
        }
    )
    response = client.post(
        "/api/grouping/preview",
        json={"type": "tmdb_list", "value": "12345"},
    )
    assert response.status_code == 200
    assert response.get_json()["count"] == 1
    mock_preview.assert_called_once()
    _, kwargs = mock_preview.call_args
    assert kwargs["tmdb_api_key"] == "test_key"


@patch("routes.preview_group")
@pytest.mark.usefixtures("temp_config")
def test_preview_grouping_anilist_list(mock_preview, client) -> None:
    """Preview with anilist_list type is accepted."""
    mock_preview.return_value = ([{"Name": "M1"}], None, 200)
    save_config({"jellyfin_url": "http://t", "api_key": "k"})
    response = client.post(
        "/api/grouping/preview",
        json={"type": "anilist_list", "value": "12345"},
    )
    assert response.status_code == 200
    assert response.get_json()["count"] == 1
    mock_preview.assert_called_once()
    args, _kwargs = mock_preview.call_args
    assert args[0] == "anilist_list"
    assert args[1] == "12345"


@patch("routes.preview_group")
@pytest.mark.usefixtures("temp_config")
def test_preview_grouping_mal_list(mock_preview, client) -> None:
    """Preview with mal_list type forwards mal_client_id."""
    mock_preview.return_value = ([{"Name": "M1"}], None, 200)
    save_config(
        {
            "jellyfin_url": "http://t",
            "api_key": "k",
            "mal_client_id": "test_client",
        }
    )
    response = client.post(
        "/api/grouping/preview",
        json={"type": "mal_list", "value": "12345"},
    )
    assert response.status_code == 200
    assert response.get_json()["count"] == 1
    mock_preview.assert_called_once()
    args, kwargs = mock_preview.call_args
    assert args[0] == "mal_list"
    assert kwargs["mal_client_id"] == "test_client"


@patch("routes.preview_group")
@pytest.mark.usefixtures("temp_config")
def test_preview_grouping_letterboxd_list(mock_preview, client) -> None:
    """Preview with letterboxd_list type is accepted."""
    mock_preview.return_value = ([{"Name": "M1"}], None, 200)
    save_config({"jellyfin_url": "http://t", "api_key": "k"})
    response = client.post(
        "/api/grouping/preview",
        json={
            "type": "letterboxd_list",
            "value": "https://letterboxd.com/user/list/foo/",
        },
    )
    assert response.status_code == 200
    assert response.get_json()["count"] == 1
    mock_preview.assert_called_once()
    args, _kwargs = mock_preview.call_args
    assert args[0] == "letterboxd_list"
    assert args[1] == "https://letterboxd.com/user/list/foo/"


@patch("routes.preview_group")
@pytest.mark.usefixtures("temp_config")
def test_preview_grouping_recommendations(mock_preview, client) -> None:
    """Preview with recommendations type forwards tmdb_api_key."""
    mock_preview.return_value = ([{"Name": "M1"}], None, 200)
    save_config(
        {
            "jellyfin_url": "http://t",
            "api_key": "k",
            "tmdb_api_key": "test_key",
        }
    )
    response = client.post(
        "/api/grouping/preview",
        json={"type": "recommendations", "value": "tt1234567"},
    )
    assert response.status_code == 200
    assert response.get_json()["count"] == 1
    mock_preview.assert_called_once()
    args, kwargs = mock_preview.call_args
    assert args[0] == "recommendations"
    assert kwargs["tmdb_api_key"] == "test_key"


# Preview grouping server not configured (lines 491-492)
@pytest.mark.usefixtures("temp_config")
def test_preview_grouping_no_config(client) -> None:
    response = client.post(
        "/api/grouping/preview",
        json={"type": "genre", "value": "Action"},
    )
    assert response.status_code == 400
    assert "Server settings not configured" in response.get_json()["message"]


# Preview grouping exceptions (lines 532-537)
@patch("routes.preview_group")
@pytest.mark.usefixtures("temp_config")
def test_preview_grouping_runtime_error(mock_preview, client) -> None:
    save_config({"jellyfin_url": "http://t", "api_key": "k"})
    mock_preview.side_effect = RuntimeError("Preview failed")
    response = client.post(
        "/api/grouping/preview",
        json={"type": "genre", "value": "Action"},
    )
    assert response.status_code == 500


# Cleanup with auto_create_libraries (lines 601-609)
@patch("routes.delete_virtual_folder")
@patch("routes.os.path.exists")
@pytest.mark.usefixtures("temp_config")
def test_perform_cleanup_with_auto_create(
    mock_exists,
    mock_delete,
    client,
    tmp_path,
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / "Action").mkdir()
    save_config(
        {
            "target_path": str(target),
            "auto_create_libraries": True,
            "jellyfin_url": "http://jf",
            "api_key": "key",
        },
    )
    mock_exists.return_value = True
    response = client.post("/api/cleanup", json={"folders": ["Action"]})
    assert response.status_code == 200
    mock_delete.assert_called_once()


# Cleanup delete_virtual_folder error (lines 606-609)
@patch("routes.delete_virtual_folder")
@patch("routes.os.path.exists")
@pytest.mark.usefixtures("temp_config")
def test_perform_cleanup_delete_virtual_folder_error(
    mock_exists,
    mock_delete,
    client,
    tmp_path,
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / "Action").mkdir()
    save_config(
        {
            "target_path": str(target),
            "auto_create_libraries": True,
            "jellyfin_url": "http://jf",
            "api_key": "key",
        },
    )
    mock_exists.return_value = True
    mock_delete.side_effect = RuntimeError("Jellyfin error")
    response = client.post("/api/cleanup", json={"folders": ["Action"]})
    assert response.status_code == 200
    assert response.get_json()["deleted"] == 1


# Auto-detect: item with no Path (line 683)
@patch("routes.fetch_jellyfin_items")
@pytest.mark.usefixtures("temp_config")
def test_auto_detect_no_path(mock_fetch, client) -> None:
    save_config({"jellyfin_url": "http://test", "api_key": "key"})
    mock_fetch.return_value = [{"Id": "1", "Name": "NoPath"}]
    response = client.post("/api/jellyfin/auto-detect-paths")
    assert response.status_code == 200
    data = response.get_json()
    assert data["detected"]["media_path_in_jellyfin"] is None


# Auto-detect: root not a directory (line 693)
@patch("routes.fetch_jellyfin_items")
@pytest.mark.usefixtures("temp_config")
def test_auto_detect_root_not_dir(mock_fetch, client) -> None:
    save_config({"jellyfin_url": "http://test", "api_key": "key"})
    mock_fetch.return_value = [{"Path": "/media/movies/M1.mkv"}]
    response = client.post("/api/jellyfin/auto-detect-paths")
    assert response.status_code == 200


def test_search_filesystem_skip_nonexistent_root() -> None:
    """_search_local_filesystem skips a root that doesn't exist as a directory (line 745)."""
    from routes import _search_local_filesystem

    result = _search_local_filesystem(
        "anyfile.mkv",
        ["/nonexistent-dir-for-testing-only"],
    )
    assert result is None


# Auto-detect: mount point skip (lines 697-698)
@patch("routes.fetch_jellyfin_items")
@patch("routes.os.path.ismount")
@patch("routes.os.path.isdir")
@patch("routes.os.walk")
@pytest.mark.usefixtures("temp_config")
def test_auto_detect_mount_skip(
    mock_walk,
    mock_isdir,
    mock_ismount,
    mock_fetch,
    client,
) -> None:
    save_config({"jellyfin_url": "http://test", "api_key": "key"})
    mock_fetch.return_value = [{"Path": "/media/movies/M1.mkv"}]
    mock_isdir.return_value = True
    mock_ismount.return_value = True
    mock_walk.return_value = [("/home", ["sub"], ["M1.mkv"])]
    response = client.post("/api/jellyfin/auto-detect-paths")
    assert response.status_code == 200


# Auto-detect: mount subdirectory skip (line 745: child mount point > root)
@patch("routes.fetch_jellyfin_items")
@patch("routes.os.path.ismount")
@patch("routes.os.path.isdir")
@patch("routes.os.walk")
@pytest.mark.usefixtures("temp_config")
def test_auto_detect_mount_subdir_skip(
    mock_walk,
    mock_isdir,
    mock_ismount,
    mock_fetch,
    client,
) -> None:
    """Auto-detect prunes subdirectories that are mount points."""
    save_config({"jellyfin_url": "http://test", "api_key": "key"})
    mock_fetch.return_value = [{"Path": "/media/movies/M1.mkv"}]
    mock_isdir.return_value = True

    # Root /media is not a mount, but /media/subvol is
    def _ismount_side_effect(path):
        return path == "/media/subvol"

    mock_ismount.side_effect = _ismount_side_effect
    # Walk yields root, then a subdir that is a mount point
    mock_walk.return_value = [
        ("/media", ["movies", "subvol"], []),
        ("/media/subvol", [], ["M1.mkv"]),
    ]
    response = client.post("/api/jellyfin/auto-detect-paths")
    assert response.status_code == 200


# Auto-detect: timeout (lines 701-703)
@patch("routes.fetch_jellyfin_items")
@patch("routes.time.monotonic")
@patch("routes.os.walk")
@patch("routes.os.path.isdir")
@patch("routes.os.path.ismount")
@pytest.mark.usefixtures("temp_config")
def test_auto_detect_timeout(
    mock_ismount,
    mock_isdir,
    mock_walk,
    mock_time,
    mock_fetch,
    client,
) -> None:
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
    response = client.post("/api/jellyfin/auto-detect-paths")
    assert response.status_code == 200
    assert mock_time.call_count >= 3


# Auto-detect: file limit (lines 707-709)
@patch("routes.fetch_jellyfin_items")
@patch("routes.os.walk")
@patch("routes.os.path.isdir")
@patch("routes.os.path.ismount")
@pytest.mark.usefixtures("temp_config")
def test_auto_detect_file_limit(
    mock_ismount,
    mock_isdir,
    mock_walk,
    mock_fetch,
    client,
) -> None:
    save_config({"jellyfin_url": "http://test", "api_key": "key"})
    mock_fetch.return_value = [{"Path": "/media/movies/M1.mkv"}]
    mock_isdir.return_value = True
    mock_ismount.return_value = False
    # 50_001 files to exceed the 50_000 limit; target filename not present
    mock_walk.return_value = [("/home", ["sub"], ["f"] * 50001)]
    response = client.post("/api/jellyfin/auto-detect-paths")
    assert response.status_code == 200


# Auto-detect: depth limit (lines 715-716)
@patch("routes.fetch_jellyfin_items")
@patch("routes.os.walk")
@patch("routes.os.path.isdir")
@patch("routes.os.path.ismount")
@pytest.mark.usefixtures("temp_config")
def test_auto_detect_depth_limit(
    mock_ismount,
    mock_isdir,
    mock_walk,
    mock_fetch,
    client,
) -> None:
    save_config({"jellyfin_url": "http://test", "api_key": "key"})
    mock_fetch.return_value = [{"Path": "/media/movies/M1.mkv"}]
    mock_isdir.return_value = True
    mock_ismount.return_value = False
    deep_path = "/a/b/c/d/e/f/g"
    # target filename not present so depth check is reached before match
    mock_walk.return_value = [(deep_path, [], ["other.mkv"])]
    response = client.post("/api/jellyfin/auto-detect-paths")
    assert response.status_code == 200


# Test results file read error (lines 821-825)
@patch("routes.Path.exists")
@patch("routes.Path.open")
def test_get_test_results_read_error(mock_open, mock_exists, client) -> None:
    mock_exists.return_value = True
    mock_open.side_effect = OSError("Read error")
    response = client.get("/api/test/results")
    assert response.status_code == 200
    data = response.get_json()
    assert "Error reading file." in data["results"].values()


# Test results successful read (line 823)
@patch("routes.Path.exists")
@patch("routes.Path.open")
def test_get_test_results_success(mock_open, mock_exists, client) -> None:
    mock_exists.return_value = True
    mock_file = MagicMock()
    mock_file.read.return_value = "test output"
    mock_open.return_value.__enter__ = MagicMock(return_value=mock_file)
    mock_open.return_value.__exit__ = MagicMock(return_value=False)
    response = client.get("/api/test/results")
    assert response.status_code == 200
    data = response.get_json()
    assert "test output" in data["results"].values()


def test_handle_http_error_bad_request_json() -> None:
    """Test that a concrete HTTPException produces a proper JSON response."""
    from flask import Flask

    from routes import _handle_http_error

    app = Flask(__name__)
    with app.test_request_context("/"):
        response, status = _handle_http_error(
            BadRequest(description="bad request"),
        )
    assert status == 400
    assert response.get_json() == {
        "status": "error",
        "message": "bad request",
    }


def test_handle_http_error_non_http_attr_error() -> None:
    """Passing a non-HTTPException to _handle_http_error raises AttributeError.

    The function signature now accepts only HTTPException, so passing
    a plain Exception is a type error at runtime. This is intentional
    — the blueprint error handler only dispatches HTTPException subclasses.
    """
    from routes import _handle_http_error

    with pytest.raises(AttributeError):
        _handle_http_error(Exception("not http"))


def test_handle_http_error_http_none_code() -> None:
    exc = HTTPException()
    exc.code = None
    with pytest.raises(HTTPException):
        _handle_http_error(exc)


# --- Remaining branch coverage for routes.py ---


def test_csrf_exempted_endpoint_skips_csrf_without_header(
    app,
    client,
    monkeypatch,
) -> None:
    """Endpoints listed in _ALLOWED_NON_CSRF_REQUESTS bypass the CSRF check."""
    import routes as routes_module

    old_allowed = routes_module._ALLOWED_NON_CSRF_REQUESTS
    old_testing = app.config.get("TESTING")
    app.config["TESTING"] = False

    # Mock the outbound network call so the test doesn't hit a real server.
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {}
    monkeypatch.setattr(routes_module.network, "get", MagicMock(return_value=mock_resp))

    try:
        # Exempt a real POST endpoint from CSRF
        routes_module._ALLOWED_NON_CSRF_REQUESTS = frozenset({"main.test_server"})
        response = client.post(
            "/api/test-server",
            json={"jellyfin_url": "http://jf:8096", "api_key": "abc123"},
        )
        # Should NOT get 403 (CSRF failure) — instead we get whatever the view returns
        assert response.status_code != 403, (
            "CSRF exemption should have allowed the request without X-Requested-With header"
        )
        assert not response.is_json or "CSRF" not in response.get_json().get(
            "message",
            "",
        )
    finally:
        routes_module._ALLOWED_NON_CSRF_REQUESTS = old_allowed
        app.config["TESTING"] = old_testing


def test_csrf_protection_with_header(client) -> None:
    from flask import current_app

    old_testing = current_app.testing
    current_app.testing = False
    try:
        response = client.post(
            "/api/config",
            json={"jellyfin_url": "http://test"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        # CSRF passes, so we get the normal handler response (200), not 403
        assert response.status_code == 200
    finally:
        current_app.testing = old_testing


def test_csrf_allowed_endpoints_env_var(monkeypatch) -> None:
    """ALLOWED_NON_CSRF_ENDPOINTS env var populates _ALLOWED_NON_CSRF_REQUESTS correctly."""
    import importlib

    import routes as routes_module

    # Capture original env value so we can restore it later
    orig = os.environ.get("ALLOWED_NON_CSRF_ENDPOINTS")

    # Reload the module with a specific env var
    monkeypatch.setenv("ALLOWED_NON_CSRF_ENDPOINTS", "main.foo,main.bar")
    importlib.reload(routes_module)
    assert (
        frozenset({"main.foo", "main.bar"}) == routes_module._ALLOWED_NON_CSRF_REQUESTS
    )

    # Empty env var should result in empty frozenset
    monkeypatch.delenv("ALLOWED_NON_CSRF_ENDPOINTS")
    importlib.reload(routes_module)
    assert frozenset() == routes_module._ALLOWED_NON_CSRF_REQUESTS

    # Restore original env var and re-read to avoid leaking test state
    if orig is not None:
        monkeypatch.setenv("ALLOWED_NON_CSRF_ENDPOINTS", orig)
    else:
        monkeypatch.delenv("ALLOWED_NON_CSRF_ENDPOINTS", raising=False)
    importlib.reload(routes_module)


@pytest.mark.usefixtures("temp_config")
def test_update_config_valid_cron(client) -> None:
    response = client.post(
        "/api/config",
        json={
            "scheduler": {
                "global_enabled": True,
                "global_schedule": "0 0 * * *",
                "cleanup_enabled": True,
                "cleanup_schedule": "0 1 * * *",
            },
            "groups": [
                {"name": "Test", "schedule_enabled": True, "schedule": "0 2 * * *"},
            ],
        },
    )
    assert response.status_code == 200


@pytest.mark.usefixtures("temp_config")
def test_update_config_group_schedule_disabled(client) -> None:
    response = client.post(
        "/api/config",
        json={
            "groups": [{"name": "Test", "schedule_enabled": False, "schedule": "bad"}],
        },
    )
    assert response.status_code == 200


@pytest.mark.usefixtures("temp_config")
def test_perform_cleanup_folder_not_found(client, tmp_path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    save_config({"target_path": str(target)})
    response = client.post("/api/cleanup", json={"folders": ["NonExistent"]})
    assert response.status_code == 200
    data = response.get_json()
    assert data["deleted"] == 0


@patch("routes.os.path.exists")
@pytest.mark.usefixtures("temp_config")
def test_perform_cleanup_auto_create_missing_settings(
    mock_exists,
    client,
    tmp_path,
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / "Action").mkdir()
    save_config(
        {
            "target_path": str(target),
            "auto_create_libraries": True,
            "jellyfin_url": "",
            "api_key": "",
        },
    )
    mock_exists.return_value = True
    response = client.post("/api/cleanup", json={"folders": ["Action"]})
    assert response.status_code == 200
    assert response.get_json()["deleted"] == 1


@patch("routes.fetch_jellyfin_items")
@patch("routes.os.walk")
@patch("routes.os.path.isdir")
@patch("routes.os.path.ismount")
@pytest.mark.usefixtures("temp_config")
def test_auto_detect_no_common_path(
    mock_ismount,
    mock_isdir,
    mock_walk,
    mock_fetch,
    client,
) -> None:
    save_config({"jellyfin_url": "http://test", "api_key": "key"})
    # Jellyfin path has a matching filename but no real common prefix
    mock_fetch.return_value = [{"Path": "/jf/unique/movie.mkv"}]
    mock_isdir.return_value = True
    mock_ismount.return_value = False
    # Walk finds the same filename — at minimum the basename matches,
    # so common_count is at least 1. This still exercises the path
    # translation logic with a minimal common prefix.
    mock_walk.return_value = [("/home", [], ["movie.mkv"])]
    response = client.post("/api/jellyfin/auto-detect-paths")
    assert response.status_code == 200
    data = response.get_json()
    # Basename match means common_count=1, so j_root loses just the basename
    assert data["detected"]["media_path_in_jellyfin"] == "/jf/unique"


def test_compute_common_root_no_match() -> None:
    assert _compute_common_root("/a/b/c", "/x/y/z") == (None, None)


def test_compute_common_root_single_match() -> None:
    assert _compute_common_root("/a/b/c", "/x/b/c") == ("/a", "/x")


def test_compute_common_root_full_match() -> None:
    assert _compute_common_root("/a/b/c", "/a/b/c") == (os.sep, os.sep)


@patch("routes.load_config")
def test_get_jellyfin_config_null_values(mock_load_config) -> None:
    mock_load_config.return_value = {"jellyfin_url": None, "api_key": None}
    with pytest.raises(HTTPException) as excinfo:
        _get_jellyfin_config()
    assert excinfo.value.code == 400


# ---------------------------------------------------------------------------
# auth coverage — _check_auth returning 401 response (via application context)
# ---------------------------------------------------------------------------


def test_check_auth_no_password_set(client) -> None:
    """When APP_PASSWORD is empty, all requests pass through."""
    response = client.get("/api/config")
    assert response.status_code == 200


def test_check_auth_static_path_allowed(app, monkeypatch) -> None:
    """Static paths bypass auth even when APP_PASSWORD is set (covers line 138)."""
    import routes as routes_mod

    monkeypatch.setattr(routes_mod, "_APP_PASSWORD", "secret")
    if hasattr(routes_mod._check_auth, "cache_clear"):
        routes_mod._check_auth.cache_clear()

    # /static/ paths should bypass the password check
    response = app.test_client().get("/static/css/variables.css")
    # Without auth header, a password-protected endpoint would 401,
    # but static paths are excluded
    assert response.status_code == 200


def test_check_auth_protected_endpoint_missing_auth(app, monkeypatch) -> None:
    """Protected endpoint returns 401 when no auth header is sent."""
    # By directly setting the module-level variable, we simulate auth protection
    import routes as routes_mod

    monkeypatch.setattr(routes_mod, "_APP_PASSWORD", "secret")
    routes_mod._check_auth.cache_clear() if hasattr(
        routes_mod._check_auth,
        "cache_clear",
    ) else None

    response = app.test_client().get("/api/config")
    assert response.status_code == 401


def test_check_auth_with_wrong_password(app, monkeypatch) -> None:
    """Protected endpoint returns 401 when wrong password is sent."""
    import routes as routes_mod

    monkeypatch.setattr(routes_mod, "_APP_PASSWORD", "secret")
    if hasattr(routes_mod._check_auth, "cache_clear"):
        routes_mod._check_auth.cache_clear()

    response = app.test_client().get(
        "/api/config",
        headers={
            "Authorization": "Basic dXNlcjp3cm9uZ3Bhc3M=",
        },
    )
    assert response.status_code == 401


def test_check_auth_with_no_password(app, monkeypatch) -> None:
    """When APP_PASSWORD is empty, all requests pass through (line 138 coverage)."""
    import routes as routes_mod

    monkeypatch.setattr(routes_mod, "_APP_PASSWORD", "")
    if hasattr(routes_mod._check_auth, "cache_clear"):
        routes_mod._check_auth.cache_clear()

    # This should pass without auth even for protected endpoints
    response = app.test_client().get(
        "/api/config",
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    # When _APP_PASSWORD is empty, auth check returns None early (line 138)
    # and the request proceeds normally. The endpoint needs X-Requested-With
    # for POST, but GET endpoints don't need it. /api/config is GET so it works.
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# _delete_folder: path-traversal checks (lines 741, 746-749)
# ---------------------------------------------------------------------------


def test_delete_folder_invalid_name() -> None:
    """_delete_folder rejects folder names with path separators (line 741)."""
    from routes import _delete_folder

    deleted, err = _delete_folder("../etc", "/tmp/base", False, "", "")
    assert deleted is False
    assert err == "Invalid folder name: ../etc"

    deleted, err = _delete_folder("sub/dir", "/tmp/base", False, "", "")
    assert deleted is False
    assert err == "Invalid folder name: sub/dir"


def test_delete_folder_path_traversal_via_symlink(tmp_path) -> None:
    """_delete_folder detects path traversal when resolved path escapes target_base (line 749)."""
    from routes import _delete_folder

    target_base = str(tmp_path / "target")
    (tmp_path / "target").mkdir()
    # Create a real directory outside target_base
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    # Create a symlink in target that points outside
    link = tmp_path / "target" / "escape_link"
    link.symlink_to(outside_dir, target_is_directory=True)

    deleted, err = _delete_folder(
        "escape_link",
        target_base,
        False,
        "",
        "",
    )
    assert deleted is False
    assert "Path traversal detected" in err


def test_delete_folder_resolve_oserror(monkeypatch, tmp_path) -> None:
    """_delete_folder handles Path.resolve() OSError gracefully (lines 746-747)."""
    from pathlib import Path

    from routes import _delete_folder

    target_base = str(tmp_path / "target")
    (tmp_path / "target").mkdir()
    (tmp_path / "target" / "safe").mkdir()

    perm_denied = "Permission denied"

    def _broken_resolve(self):
        raise OSError(perm_denied)

    monkeypatch.setattr(Path, "resolve", _broken_resolve)

    # OSError caught, resolved = path (unresolved), then target_base IS in
    # str(resolved.parent) because path hasn't resolved outside -> falls
    # through to exists check then deletes normally
    deleted, err = _delete_folder("safe", target_base, False, "", "")
    assert deleted is True
    assert err is None


# ---------------------------------------------------------------------------
# _search_local_filesystem: OSError from ismount (lines 844-847)
# ---------------------------------------------------------------------------


@patch("routes.os.path.ismount")
def test_search_filesystem_ismount_oserror(mock_ismount) -> None:
    """_search_local_filesystem skips directories when os.path.ismount() raises OSError (lines 844-847)."""
    import tempfile

    from routes import _search_local_filesystem

    with tempfile.TemporaryDirectory() as tmp:
        test_dir = Path(tmp) / "test"
        test_dir.mkdir()
        (test_dir / "movie.mkv").touch()

        mock_ismount.side_effect = OSError("Permission denied")

        result = _search_local_filesystem("movie.mkv", [str(test_dir)])
        # ismount OSError on the root causes continue before checking filenames,
        # so the file is never found
        assert result is None


@patch("routes.os.path.ismount")
def test_search_filesystem_mount_point_finds_file(mock_ismount) -> None:
    """_search_local_filesystem finds a file inside a mount-point subdirectory (lines 962-963)."""
    import tempfile

    from routes import _search_local_filesystem

    with tempfile.TemporaryDirectory() as tmp:
        root_dir = Path(tmp) / "root"
        mount_dir = root_dir / "mount"
        mount_dir.mkdir(parents=True)
        target_file = mount_dir / "movie.mkv"
        target_file.touch()

        # Make ismount return True ONLY for the mount subdir (not root)
        def _fake_ismount(path: str) -> bool:
            p = Path(path)
            return p == mount_dir and p != root_dir

        mock_ismount.side_effect = _fake_ismount

        result = _search_local_filesystem("movie.mkv", [str(root_dir)])
        assert result == str(target_file)


@patch("routes.os.path.ismount")
def test_search_filesystem_mount_point_file_not_found(mock_ismount) -> None:
    """_search_local_filesystem prunes mount-point subdirectories when file is not found there (lines 962-963)."""
    import tempfile

    from routes import _search_local_filesystem

    with tempfile.TemporaryDirectory() as tmp:
        root_dir = Path(tmp) / "root"
        mount_dir = root_dir / "mount"
        mount_dir.mkdir(parents=True)
        # Create a different file so the target is NOT in the mount dir
        mount_dir / "other.mkv"
        # Target file is in a deeper sub-directory of the mount
        deep_dir = mount_dir / "sub"
        deep_dir.mkdir()
        target_file = deep_dir / "movie.mkv"
        target_file.touch()

        def _fake_ismount(path: str) -> bool:
            p = Path(path)
            return p == mount_dir and p != root_dir

        mock_ismount.side_effect = _fake_ismount

        # Should NOT find the file because mount dir's subdirectories are pruned
        result = _search_local_filesystem("movie.mkv", [str(root_dir)])
        assert result is None


# ---------------------------------------------------------------------------
# Preview grouping: year type, complex query, invalid source_type (Issue #791)
# ---------------------------------------------------------------------------


@patch("routes.preview_group")
@pytest.mark.usefixtures("temp_config")
def test_preview_grouping_year_type(mock_preview, client) -> None:
    """Preview with year type returns proper results."""
    save_config({"jellyfin_url": "http://t", "api_key": "k"})
    mock_preview.return_value = (
        [{"Name": "Movie 1", "ProductionYear": 2020}],
        None,
        200,
    )
    response = client.post(
        "/api/grouping/preview",
        json={"type": "year", "value": "2020"},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["count"] == 1
    assert data["preview_items"][0]["Year"] == 2020


@patch("routes.preview_group")
@pytest.mark.usefixtures("temp_config")
def test_preview_grouping_complex_query(mock_preview, client) -> None:
    """Preview with complex query type returns properly."""
    save_config({"jellyfin_url": "http://t", "api_key": "k"})
    mock_preview.return_value = (
        [
            {"Name": "HorrorComedy", "ProductionYear": 2023},
        ],
        None,
        200,
    )
    response = client.post(
        "/api/grouping/preview",
        json={"type": "complex", "value": "Horror AND Comedy"},
    )
    assert response.status_code == 200
    assert response.get_json()["count"] == 1


@patch("routes.preview_group")
@pytest.mark.usefixtures("temp_config")
def test_preview_grouping_watch_state(mock_preview, client) -> None:
    """Preview with watch_state filter works."""
    save_config({"jellyfin_url": "http://t", "api_key": "k"})
    mock_preview.return_value = ([{"Name": "M1"}], None, 200)
    response = client.post(
        "/api/grouping/preview",
        json={"type": "genre", "value": "Action", "watch_state": "unwatched"},
    )
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Cleanup: empty target dir, permission denied (Issue #792)
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("temp_config")
def test_get_cleanup_empty_target_dir(client, tmp_path) -> None:
    """Empty target directory returns no items."""
    target = tmp_path / "empty_target"
    target.mkdir()
    save_config({"target_path": str(target)})
    response = client.get("/api/cleanup")
    assert response.status_code == 200
    data = response.get_json()
    assert data["items"] == []


@patch("routes.Path.iterdir")
@pytest.mark.usefixtures("temp_config")
def test_get_cleanup_permission_denied(mock_iterdir, client, tmp_path) -> None:
    """Permission denied reading target dir returns 500 error."""
    target = tmp_path / "secure"
    target.mkdir()
    save_config({"target_path": str(target)})
    mock_iterdir.side_effect = PermissionError("Permission denied")
    response = client.get("/api/cleanup")
    assert response.status_code == 500
    data = response.get_json()
    assert "Permission denied" in data["message"]


# ---------------------------------------------------------------------------
# test_server: ValueError / TypeError handling (lines 720-721)
# ---------------------------------------------------------------------------


@patch("routes.network.get")
def test_test_server_value_error(mock_get, client) -> None:
    """ValueError from network.get is caught and returns 400."""
    mock_get.side_effect = ValueError("malformed URL")
    response = client.post(
        "/api/test-server",
        json={"jellyfin_url": "not-a-url", "api_key": "key"},
    )
    assert response.status_code == 400
    data = response.get_json()
    assert "Invalid server URL" in data["message"]


@patch("routes.network.get")
def test_test_server_type_error(mock_get, client) -> None:
    """TypeError from network.get is caught and returns 400."""
    mock_get.side_effect = TypeError("unsupported operand type")
    response = client.post(
        "/api/test-server",
        json={"jellyfin_url": "http://test", "api_key": "valid-key"},
    )
    assert response.status_code == 400
    data = response.get_json()
    assert "Invalid server URL" in data["message"]


# ---------------------------------------------------------------------------
# _fetch_jellyfin_endpoint: requests.RequestException with partial data
# (lines 775-783)
# ---------------------------------------------------------------------------


@patch("jellyfin._get_json")
@pytest.mark.usefixtures("temp_config")
def test_fetch_jellyfin_endpoint_request_exception_partial(mock_get_json, client) -> None:
    """requests.RequestException after partial data returns partial results.

    Patches jellyfin._get_json so that the raw requests.RequestException
    flows through _paginate_jellyfin into _fetch_jellyfin_endpoint's
    except requests.RequestException handler (bypassing _get_json's
    conversion to RuntimeError).
    """
    from routes import _fetch_jellyfin_endpoint

    # First call returns a page of items
    mock_get_json.side_effect = [
        {"Items": [{"Name": f"G{i}"} for i in range(200)], "TotalRecordCount": 201},
        # Second call raises a raw requests.RequestException
        requests.exceptions.ConnectionError("fail"),
    ]
    result = _fetch_jellyfin_endpoint("http://jf", "key", "Genres")
    assert len(result) == 200


@patch("jellyfin._get_json")
@pytest.mark.usefixtures("temp_config")
def test_fetch_jellyfin_endpoint_request_exception_no_data(mock_get_json, client) -> None:
    """requests.RequestException with no data re-raises."""
    from routes import _fetch_jellyfin_endpoint

    mock_get_json.side_effect = requests.exceptions.ConnectionError("fail")
    with pytest.raises(requests.exceptions.ConnectionError):
        _fetch_jellyfin_endpoint("http://jf", "key", "Genres")


# ---------------------------------------------------------------------------
# Index: rendered wizard state present in HTML (Issue #797)
# ---------------------------------------------------------------------------


def test_index_contains_wizard_element(client) -> None:
    """Index page contains the wizard trigger element."""
    response = client.get("/")
    assert response.status_code == 200
    html = response.data.decode("utf-8")
    # The wizard button should be in the rendered HTML
    assert "wizard" in html.lower()
    assert "data-wizard" in html or 'id="wizard' in html or 'class="wizard' in html
