import logging

import pytest
import requests

from jellyfin import (
    add_virtual_folder,
    delete_virtual_folder,
    fetch_jellyfin_items,
    get_libraries,
    get_library_id,
    get_user_recent_items,
    get_users,
    set_virtual_folder_image,
)

pytestmark = pytest.mark.exhaustive

TEST_API_KEY = "test_key"


@pytest.fixture
def jellyfin_url(virtual_jellyfin):
    return virtual_jellyfin

# 1. Authentication & Network Failures


def test_401_unauthorized(jellyfin_url):
    with pytest.raises(RuntimeError) as excinfo:
        fetch_jellyfin_items(jellyfin_url, "BAD_KEY")
    assert excinfo.value.__cause__.response.status_code == 401


def test_timeout(jellyfin_url):
    with pytest.raises(RuntimeError) as excinfo:
        # The endpoint sleeps for 3s, timeout is 1s
        fetch_jellyfin_items(jellyfin_url, "TIMEOUT_KEY", timeout=1)
    assert isinstance(excinfo.value.__cause__, requests.exceptions.Timeout)


def test_connection_error():
    # Attempt connecting to an invalid port/host
    with pytest.raises(RuntimeError) as excinfo:
        fetch_jellyfin_items("http://localhost:12345", TEST_API_KEY, timeout=1)
    assert isinstance(excinfo.value.__cause__, requests.exceptions.ConnectionError)

# 2. fetch_jellyfin_items Exhaustive


def test_fetch_empty_items(jellyfin_url):
    items = fetch_jellyfin_items(jellyfin_url, "EMPTY_ITEMS_KEY")
    assert items == []


def test_fetch_missing_items_list(jellyfin_url):
    items = fetch_jellyfin_items(jellyfin_url, "MISSING_ITEMS_KEY")
    assert items == []


def test_fetch_malformed_json(jellyfin_url):
    with pytest.raises(RuntimeError, match="Invalid JSON response"):
        fetch_jellyfin_items(jellyfin_url, "MALFORMED_JSON_KEY")


def test_fetch_extra_query_params(jellyfin_url):
    # The server ignores it, but we test requests is passing it
    items = fetch_jellyfin_items(jellyfin_url, TEST_API_KEY, extra_params={"IncludeItemTypes": "Movie"})
    assert len(items) >= 2

# 3. get_libraries Exhaustive


def test_get_libraries_500(jellyfin_url):
    with pytest.raises(RuntimeError) as excinfo:
        get_libraries(jellyfin_url, "LIB_GET_500")
    assert excinfo.value.__cause__.response.status_code == 500


def test_get_libraries_missing_name(jellyfin_url):
    libs = get_libraries(jellyfin_url, "LIB_GET_MISSING_NAME")
    # Missing/empty names are filtered out
    assert libs == []


def test_get_libraries_empty(jellyfin_url):
    libs = get_libraries(jellyfin_url, "LIB_GET_EMPTY")
    assert libs == []

# 4. add_virtual_folder Exhaustive


def test_add_virtual_folder_409_conflict(jellyfin_url):
    # Movies already exists, add_virtual_folder silent recovery (returns 409 but caught in 200 checks for path/refresh)
    # The current code in add_virtual_folder expects 409 to not be raised, and proceed
    add_virtual_folder(jellyfin_url, TEST_API_KEY, "Movies", ["/tmp/safe"])
    # If no exception, it passes


def test_add_virtual_folder_500_create(jellyfin_url):
    with pytest.raises(RuntimeError) as excinfo:
        add_virtual_folder(jellyfin_url, TEST_API_KEY, "FAIL_CREATE", ["/tmp/safe"])
    assert "Failed to create virtual folder 'FAIL_CREATE'" in str(excinfo.value)


def test_add_virtual_folder_400_paths(jellyfin_url):
    with pytest.raises(RuntimeError) as excinfo:
        add_virtual_folder(jellyfin_url, TEST_API_KEY, "NewLibPath", ["/tmp/FAIL_PATH"])
    assert "Failed to add path" in str(excinfo.value)
    assert "Status 400" in str(excinfo.value)


def test_add_virtual_folder_502_refresh(jellyfin_url):
    with pytest.raises(RuntimeError) as excinfo:
        add_virtual_folder(jellyfin_url, "FAIL_REFRESH_KEY", "RefreshLib", ["/tmp/safe"])
    assert "Failed to trigger library refresh" in str(excinfo.value)
    assert "Status 502" in str(excinfo.value)


def test_add_virtual_folder_invalid_collection(jellyfin_url):
    # Mixed should omit collectionType parameter.
    add_virtual_folder(jellyfin_url, TEST_API_KEY, "MixedLib2", ["/tmp/safe"], collection_type="mixed")
    # if it doesn't fail, we consider it a success.


def test_add_virtual_folder_empty_paths(jellyfin_url):
    # Should not fail.
    add_virtual_folder(jellyfin_url, TEST_API_KEY, "EmptyLib", [])

# 5. delete_virtual_folder Exhaustive


def test_delete_virtual_folder_404(jellyfin_url, caplog):
    with pytest.raises(RuntimeError):
        delete_virtual_folder(jellyfin_url, TEST_API_KEY, "FAIL_DELETE_404")
    assert "Delete Virtual Folder Failed (404)" in caplog.text


def test_delete_virtual_folder_500(jellyfin_url):
    with pytest.raises(RuntimeError):
        delete_virtual_folder(jellyfin_url, TEST_API_KEY, "FAIL_DELETE_500")

# 6. get_library_id Exhaustive


def test_get_library_id_missing(jellyfin_url):
    lib_id = get_library_id(jellyfin_url, TEST_API_KEY, "DoesNotExist")
    assert lib_id is None


def test_get_library_id_missing_itemid_key(jellyfin_url):
    lib_id = get_library_id(jellyfin_url, "LIB_GET_MISSING_ID", "Movies")
    assert lib_id is None


def test_get_library_id_500(jellyfin_url):
    with pytest.raises(RuntimeError) as excinfo:
        get_library_id(jellyfin_url, "LIB_GET_500", "Movies")
    assert excinfo.value.__cause__.response.status_code == 500

# 7. set_virtual_folder_image Exhaustive


def test_set_virtual_folder_image_missing_id(jellyfin_url, tmp_path, caplog):
    caplog.set_level(logging.INFO)
    img_path = tmp_path / "test.jpg"
    img_path.write_bytes(b"data")
    set_virtual_folder_image(jellyfin_url, TEST_API_KEY, "DoesNotExist", str(img_path))
    assert "not found or ID unknown" in caplog.text


def test_set_virtual_folder_image_oserror(jellyfin_url, caplog):
    set_virtual_folder_image(jellyfin_url, TEST_API_KEY, "Movies", "/does/not/exist.jpg")
    assert "Failed to read image file" in caplog.text


def test_set_virtual_folder_image_unknown_mime(jellyfin_url, tmp_path, caplog):
    caplog.set_level(logging.INFO)
    img_path = tmp_path / "testfile"  # No extension
    img_path.write_bytes(b"data")
    # Standard call should work and fallback to application/octet-stream
    set_virtual_folder_image(jellyfin_url, TEST_API_KEY, "Movies", str(img_path))
    assert "Successfully updated cover image" in caplog.text


def test_set_virtual_folder_image_400(jellyfin_url, tmp_path, caplog):
    caplog.set_level(logging.INFO)
    img_path = tmp_path / "test.jpg"
    img_path.write_bytes(b"data")

    # We must mock get_library_id to return our magic ID since standard "Movies" returns "movies_id"
    import jellyfin
    original_get_id = jellyfin.get_library_id
    jellyfin.get_library_id = lambda *args, **kwargs: "FAIL_IMAGE_ID"

    try:
        set_virtual_folder_image(jellyfin_url, TEST_API_KEY, "Movies", str(img_path))
    finally:
        jellyfin.get_library_id = original_get_id

    assert "Failed to upload image for item" in caplog.text

# 8. get_users and get_user_recent_items Exhaustive


def test_get_users_500(jellyfin_url):
    with pytest.raises(RuntimeError) as excinfo:
        get_users(jellyfin_url, "USER_GET_500")
    assert excinfo.value.__cause__.response.status_code == 500


def test_get_user_recent_items_bad_user(jellyfin_url):
    items = get_user_recent_items(jellyfin_url, TEST_API_KEY, "BAD_USER")
    assert items == []


def test_get_user_recent_items_missing_data(jellyfin_url):
    items = get_user_recent_items(jellyfin_url, TEST_API_KEY, "MISSING_DATA_USER")
    assert items == []
