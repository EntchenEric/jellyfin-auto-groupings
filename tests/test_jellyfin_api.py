import requests
import logging
from unittest.mock import patch, MagicMock
import pytest
from jellyfin import (
    get_libraries, add_virtual_folder, delete_virtual_folder,
    get_library_id, set_virtual_folder_image, get_users, get_user_recent_items,
    create_collection, find_collection_by_name, add_to_collection,
    remove_from_collection, delete_collection, set_collection_image,
)


@patch('requests.get')
def test_get_libraries(mock_get):
    mock_response = MagicMock()
    mock_response.json.return_value = [{"Name": "Movies"}, {"Name": "TV Shows"}]
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    libs = get_libraries("http://localhost:8096", "test_key")
    assert libs == ["Movies", "TV Shows"]
    mock_get.assert_called_with(
        "http://localhost:8096/Library/VirtualFolders",
        headers={"X-Emby-Token": "test_key"},
        timeout=30
    )


@patch('requests.post')
def test_add_virtual_folder_success(mock_post):
    mock_response = MagicMock()
    mock_response.ok = True
    mock_response.status_code = 200
    mock_post.return_value = mock_response

    add_virtual_folder("http://localhost:8096", "test_key", "NewLib", ["/path1"])

    # 1 for creation, 1 for path addition, 1 for refresh
    assert mock_post.call_count == 3


@patch('requests.post')
def test_add_virtual_folder_already_exists(mock_post):
    mock_response_409 = MagicMock()
    mock_response_409.ok = False
    mock_response_409.status_code = 409

    mock_response_200 = MagicMock()
    mock_response_200.ok = True
    mock_response_200.status_code = 200

    # 409 on create, then 200 on path and refresh
    mock_post.side_effect = [mock_response_409, mock_response_200, mock_response_200]

    add_virtual_folder("http://localhost:8096", "test_key", "Exists", ["/path1"])
    assert mock_post.call_count == 3


@patch('requests.post')
def test_add_virtual_folder_creation_failure(mock_post):
    mock_response = MagicMock()
    mock_response.ok = False
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"

    # We need to mock raise_for_status to raise an exception
    import requests
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_response)
    mock_post.return_value = mock_response

    with pytest.raises(RuntimeError) as excinfo:
        add_virtual_folder("http://localhost:8096", "test_key", "FailLib", ["/path1"])

    assert "Failed to create virtual folder 'FailLib'" in str(excinfo.value)
    assert "Status 500" in str(excinfo.value)
    assert "Internal Server Error" in str(excinfo.value)


@patch('requests.post')
def test_add_virtual_folder_path_failure(mock_post):
    mock_response_ok = MagicMock()
    mock_response_ok.ok = True
    mock_response_ok.status_code = 200

    mock_response_fail = MagicMock()
    mock_response_fail.ok = False
    mock_response_fail.status_code = 400
    mock_response_fail.text = "Invalid Path"

    import requests
    mock_response_fail.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_response_fail)

    # OK on create, Fail on path
    mock_post.side_effect = [mock_response_ok, mock_response_fail]

    with pytest.raises(RuntimeError) as excinfo:
        add_virtual_folder("http://localhost:8096", "test_key", "PathFail", ["/bad/path"])

    assert "Failed to add path '/bad/path' to library 'PathFail'" in str(excinfo.value)
    assert "Status 400" in str(excinfo.value)
    assert "Invalid Path" in str(excinfo.value)


@patch('requests.delete')
def test_delete_virtual_folder(mock_delete):
    mock_response = MagicMock()
    mock_response.ok = True
    mock_delete.return_value = mock_response

    delete_virtual_folder("http://localhost:8096", "test_key", "ToDelete")
    assert mock_delete.called
    mock_delete.assert_called_with(
        "http://localhost:8096/Library/VirtualFolders",
        params={"name": "ToDelete"},
        headers={"X-Emby-Token": "test_key"},
        timeout=30
    )


@patch('requests.post')
def test_add_virtual_folder_mixed(mock_post):
    mock_response = MagicMock()
    mock_response.ok = True
    mock_response.status_code = 200
    mock_post.return_value = mock_response

    add_virtual_folder("http://localhost:8096", "test_key", "MixedLib", ["/path1"], collection_type="mixed")

    # Check the first call (creation) parameters
    args, kwargs = mock_post.call_args_list[0]
    params = kwargs.get('params', {})

    assert "collectionType" not in params
    assert params["name"] == "MixedLib"
    assert params["refreshLibrary"] == "false"


@patch('requests.get')
def test_get_library_id(mock_get):
    mock_response = MagicMock()
    mock_response.json.return_value = [
        {"Name": "Movies", "ItemId": "12345"},
        {"Name": "TV Shows", "ItemId": "67890"},
        {"Name": "Orphans"}
    ]
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    item_id = get_library_id("http://localhost:8096", "test_key", "Movies")
    assert item_id == "12345"
    item_id_none = get_library_id("http://localhost:8096", "test_key", "NonExistent")
    assert item_id_none is None
    item_id_orphans = get_library_id("http://localhost:8096", "test_key", "Orphans")
    assert item_id_orphans is None


@patch('mimetypes.guess_type')
@patch('builtins.open')
@patch('requests.post')
@patch('jellyfin.get_library_id')
def test_set_virtual_folder_image(mock_get_library_id, mock_post, mock_open, mock_guess):
    mock_guess.return_value = ("image/jpeg", None)
    mock_get_library_id.return_value = "12345"
    mock_open.return_value.__enter__.return_value.read.return_value = b"image_data"

    mock_response = MagicMock()
    mock_response.ok = True
    mock_post.return_value = mock_response

    set_virtual_folder_image("http://localhost:8096", "test_key", "Movies", "/path/to/image.jpg")

    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == "http://localhost:8096/Items/12345/Images/Primary"
    assert kwargs["data"] == b"image_data"
    assert kwargs["headers"]["X-Emby-Token"] == "test_key"
    assert kwargs["headers"]["Content-Type"] == "image/jpeg"


@patch('requests.get')
def test_get_users(mock_get):
    mock_response = MagicMock()
    mock_response.json.return_value = [{"Id": "u1", "Name": "Alice"}, {"Id": "u2", "Name": "Bob"}]
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    users = get_users("http://localhost:8096", "test_key")
    assert len(users) == 2
    assert users[0]["Id"] == "u1"
    assert users[0]["Name"] == "Alice"

    mock_get.assert_called_once_with(
        "http://localhost:8096/Users",
        headers={"X-Emby-Token": "test_key"},
        timeout=30
    )


@patch('requests.get')
def test_get_user_recent_items(mock_get):
    mock_response = MagicMock()
    mock_response.json.return_value = {"Items": [{"Name": "Movie 1"}, {"Name": "Show 1"}]}
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    items = get_user_recent_items("http://localhost:8096", "test_key", "u1", limit=10)
    assert len(items) == 2
    assert items[0]["Name"] == "Movie 1"

    expected_params = {
        "Filters": "IsPlayed",
        "SortBy": "DatePlayed",
        "SortOrder": "Descending",
        "IncludeItemTypes": "Movie,Series",
        "Recursive": "true",
        "Limit": "10",
        "Fields": "ProviderIds",
    }
    mock_get.assert_called_once_with(
        "http://localhost:8096/Users/u1/Items",
        headers={"X-Emby-Token": "test_key"},
        params=expected_params,
        timeout=30
    )


@patch('requests.post')
def test_add_virtual_folder_creation_failure_no_response(mock_post):
    mock_post.side_effect = requests.exceptions.RequestException("Network Error")

    with pytest.raises(RuntimeError) as excinfo:
        add_virtual_folder("http://localhost:8096", "test_key", "FailLib", ["/path1"])

    assert "Failed to create virtual folder 'FailLib': Network Error" in str(excinfo.value)


@patch('requests.post')
def test_add_virtual_folder_path_failure_no_response(mock_post):
    mock_response_ok = MagicMock()
    mock_response_ok.ok = True
    mock_response_ok.status_code = 200

    # First call OK, second call RequestException
    mock_post.side_effect = [mock_response_ok, requests.exceptions.RequestException("Path Network Error")]

    with pytest.raises(RuntimeError) as excinfo:
        add_virtual_folder("http://localhost:8096", "test_key", "FailLib", ["/path1"])

    assert "Failed to add path '/path1' to library 'FailLib': Path Network Error" in str(excinfo.value)


@patch('requests.post')
def test_add_virtual_folder_refresh_failure(mock_post):
    mock_response_ok = MagicMock()
    mock_response_ok.ok = True
    mock_response_ok.status_code = 200

    mock_response_fail = MagicMock()
    mock_response_fail.ok = False
    mock_response_fail.status_code = 502
    mock_response_fail.text = "Bad Gateway"

    mock_response_fail.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_response_fail)

    # create OK, path OK, refresh HTTPError
    mock_post.side_effect = [mock_response_ok, mock_response_ok, mock_response_fail]

    with pytest.raises(RuntimeError) as excinfo:
        add_virtual_folder("http://localhost:8096", "test_key", "RefreshFail", ["/path1"])

    assert "Failed to trigger library refresh for 'RefreshFail' (Status 502): Bad Gateway" in str(excinfo.value)


@patch('requests.post')
def test_add_virtual_folder_refresh_failure_no_response(mock_post):
    mock_response_ok = MagicMock()
    mock_response_ok.ok = True
    mock_response_ok.status_code = 200

    # create OK, path OK, refresh RequestException
    mock_post.side_effect = [mock_response_ok, mock_response_ok,
                             requests.exceptions.RequestException("Refresh Network Error")]

    with pytest.raises(RuntimeError) as excinfo:
        add_virtual_folder("http://localhost:8096", "test_key", "RefreshFail", ["/path1"])

    assert "Failed to trigger library refresh for 'RefreshFail': Refresh Network Error" in str(excinfo.value)


@patch('requests.delete')
def test_delete_virtual_folder_not_ok(mock_delete, caplog):
    mock_response = MagicMock()
    mock_response.ok = False
    mock_response.status_code = 404
    mock_response.text = "Not Found"
    mock_delete.return_value = mock_response

    with caplog.at_level(logging.WARNING):
        delete_virtual_folder("http://localhost:8096", "test_key", "ToDelete")

    assert "Delete Virtual Folder Failed (404): Not Found" in caplog.text


@patch('requests.get')
def test_get_library_id_request_exception(mock_get, caplog):
    mock_get.side_effect = requests.exceptions.RequestException("Fetch Error")

    result = get_library_id("http://localhost:8096", "test_key", "MyLib")
    assert result is None

    assert "Failed to get library ID for 'MyLib': Fetch Error" in caplog.text


@patch('jellyfin.get_library_id')
def test_set_virtual_folder_image_no_library_id(mock_get_library_id, caplog):
    mock_get_library_id.return_value = None

    set_virtual_folder_image("http://localhost:8096", "test_key", "MyLib", "/path/to/img.jpg")

    assert "Cannot set image: Library 'MyLib' not found or ID unknown." in caplog.text


@patch('jellyfin.get_library_id')
def test_set_virtual_folder_image_os_error(mock_get_library_id, caplog):
    mock_get_library_id.return_value = "123"

    with patch('builtins.open', side_effect=OSError("Permission Denied")):
        set_virtual_folder_image("http://localhost:8096", "test_key", "MyLib", "/path/to/img.jpg")

    assert "Cannot set image: Failed to read image file '/path/to/img.jpg': Permission Denied" in caplog.text


@patch('mimetypes.guess_type')
@patch('builtins.open')
@patch('requests.post')
@patch('jellyfin.get_library_id')
def test_set_virtual_folder_image_request_exception(mock_get_library_id, mock_post, mock_open, mock_guess, caplog):
    mock_guess.return_value = ("image/jpeg", None)
    mock_get_library_id.return_value = "123"
    mock_open.return_value.__enter__.return_value.read.return_value = b"image_data"

    mock_response_fail = MagicMock()
    mock_response_fail.ok = False
    mock_response_fail.status_code = 400
    mock_response_fail.text = "Bad Request"
    import requests
    fail_exc = requests.exceptions.HTTPError(response=mock_response_fail)

    # We assign the response to the exception so the handler can use exc.response
    fail_exc.response = mock_response_fail
    mock_post.side_effect = fail_exc

    set_virtual_folder_image("http://localhost:8096", "test_key", "MyLib", "/path/to/img.jpg")

    assert "Failed to set image for library 'MyLib' (Status 400): Bad Request" in caplog.text


@patch('mimetypes.guess_type')
@patch('builtins.open')
@patch('requests.post')
@patch('jellyfin.get_library_id')
def test_set_virtual_folder_image_request_exception_no_response(
    mock_get_library_id, mock_post, mock_open, mock_guess, caplog
):
    mock_guess.return_value = ("image/jpeg", None)
    mock_get_library_id.return_value = "123"
    mock_open.return_value.__enter__.return_value.read.return_value = b"image_data"

    mock_post.side_effect = requests.exceptions.RequestException("Upload Error")

    set_virtual_folder_image("http://localhost:8096", "test_key", "MyLib", "/path/to/img.jpg")

    assert "Failed to set image for library 'MyLib': Upload Error" in caplog.text


# ---------------------------------------------------------------------------
# Collection (Boxset) API tests
# ---------------------------------------------------------------------------


@patch('requests.post')
def test_create_collection_success(mock_post):
    mock_response = MagicMock()
    mock_response.json.return_value = {"Id": "col_123"}
    mock_response.raise_for_status.return_value = None
    mock_post.return_value = mock_response

    col_id = create_collection("http://localhost:8096", "test_key", "My Collection", ["item_1", "item_2"])
    assert col_id == "col_123"
    mock_post.assert_called_once_with(
        "http://localhost:8096/Collections",
        params={"Name": "My Collection", "Ids": "item_1,item_2"},
        headers={"X-Emby-Token": "test_key"},
        timeout=30,
    )


@patch('requests.post')
def test_create_collection_no_id(mock_post):
    mock_response = MagicMock()
    mock_response.json.return_value = {}
    mock_response.raise_for_status.return_value = None
    mock_post.return_value = mock_response

    with pytest.raises(RuntimeError, match="Collection created but no Id returned for 'Bad'"):
        create_collection("http://localhost:8096", "test_key", "Bad", ["item_1"])


@patch('requests.post')
def test_create_collection_http_error(mock_post):
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Server Error"
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_response)
    mock_post.return_value = mock_response

    with pytest.raises(RuntimeError) as excinfo:
        create_collection("http://localhost:8096", "test_key", "Fail", ["item_1"])
    assert "Failed to create collection 'Fail' (Status 500): Server Error" in str(excinfo.value)


@patch('requests.post')
def test_create_collection_request_exception_no_response(mock_post):
    mock_post.side_effect = requests.exceptions.RequestException("Network down")

    with pytest.raises(RuntimeError, match="Failed to create collection 'Fail': Network down"):
        create_collection("http://localhost:8096", "test_key", "Fail", ["item_1"])


@patch('requests.get')
def test_find_collection_by_name_found(mock_get):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "Items": [
            {"Name": "Other", "Id": "other_id"},
            {"Name": "My Boxset", "Id": "boxset_42"},
        ]
    }
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    result = find_collection_by_name("http://localhost:8096", "test_key", "My Boxset")
    assert result == "boxset_42"


@patch('requests.get')
def test_find_collection_by_name_not_found(mock_get):
    mock_response = MagicMock()
    mock_response.json.return_value = {"Items": [{"Name": "Other", "Id": "x"}]}
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    result = find_collection_by_name("http://localhost:8096", "test_key", "Missing")
    assert result is None


@patch('requests.get')
def test_find_collection_by_name_missing_id(mock_get):
    mock_response = MagicMock()
    mock_response.json.return_value = {"Items": [{"Name": "NoId"}]}
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    result = find_collection_by_name("http://localhost:8096", "test_key", "NoId")
    assert result is None


@patch('requests.get')
def test_find_collection_by_name_request_exception(mock_get):
    mock_get.side_effect = requests.exceptions.RequestException("Timeout")

    result = find_collection_by_name("http://localhost:8096", "test_key", "Anything")
    assert result is None


@patch('requests.get')
def test_find_collection_by_name_on_second_page(mock_get):
    page1 = MagicMock()
    page1.json.return_value = {
        "Items": [
            {"Name": "Marvel Phase 1", "Id": "phase1"},
            {"Name": "Marvel Phase 2", "Id": "phase2"},
        ],
        "TotalRecordCount": 3,
    }
    page1.raise_for_status.return_value = None

    page2 = MagicMock()
    page2.json.return_value = {
        "Items": [{"Name": "Marvel", "Id": "exact_match"}],
        "TotalRecordCount": 3,
    }
    page2.raise_for_status.return_value = None

    mock_get.side_effect = [page1, page2]

    result = find_collection_by_name("http://localhost:8096", "test_key", "Marvel")
    assert result == "exact_match"
    assert mock_get.call_count == 2


@patch('requests.post')
def test_add_to_collection_success(mock_post):
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_post.return_value = mock_response

    add_to_collection("http://localhost:8096", "test_key", "col_1", ["a", "b"])
    mock_post.assert_called_once_with(
        "http://localhost:8096/Collections/col_1/Items",
        params={"Ids": "a,b"},
        headers={"X-Emby-Token": "test_key"},
        timeout=30,
    )


def test_add_to_collection_empty_ids():
    add_to_collection("http://localhost:8096", "test_key", "col_1", [])


@patch('requests.post')
def test_add_to_collection_http_error(mock_post):
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.text = "Bad item"
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_response)
    mock_post.return_value = mock_response

    with pytest.raises(RuntimeError) as excinfo:
        add_to_collection("http://localhost:8096", "test_key", "col_1", ["bad"])
    assert "Failed to add items to collection 'col_1' (Status 400): Bad item" in str(excinfo.value)


@patch('requests.post')
def test_add_to_collection_request_exception(mock_post):
    mock_post.side_effect = requests.exceptions.RequestException("Net fail")

    with pytest.raises(RuntimeError, match="Failed to add items to collection 'col_1': Net fail"):
        add_to_collection("http://localhost:8096", "test_key", "col_1", ["x"])


@patch('requests.delete')
def test_remove_from_collection_success(mock_delete):
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_delete.return_value = mock_response

    remove_from_collection("http://localhost:8096", "test_key", "col_1", ["a", "b"])
    mock_delete.assert_called_once_with(
        "http://localhost:8096/Collections/col_1/Items",
        params={"Ids": "a,b"},
        headers={"X-Emby-Token": "test_key"},
        timeout=30,
    )


def test_remove_from_collection_empty_ids():
    remove_from_collection("http://localhost:8096", "test_key", "col_1", [])


@patch('requests.delete')
def test_remove_from_collection_http_error(mock_delete):
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.text = "Not found"
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_response)
    mock_delete.return_value = mock_response

    with pytest.raises(RuntimeError) as excinfo:
        remove_from_collection("http://localhost:8096", "test_key", "col_1", ["x"])
    assert "Failed to remove items from collection 'col_1' (Status 404): Not found" in str(excinfo.value)


@patch('requests.delete')
def test_remove_from_collection_request_exception(mock_delete):
    mock_delete.side_effect = requests.exceptions.RequestException("Timeout")

    with pytest.raises(RuntimeError, match="Failed to remove items from collection 'col_1': Timeout"):
        remove_from_collection("http://localhost:8096", "test_key", "col_1", ["x"])


@patch('requests.delete')
def test_delete_collection_success(mock_delete):
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_delete.return_value = mock_response

    delete_collection("http://localhost:8096", "test_key", "col_1")
    mock_delete.assert_called_once_with(
        "http://localhost:8096/Items/col_1",
        headers={"X-Emby-Token": "test_key"},
        timeout=30,
    )


@patch('requests.delete')
def test_delete_collection_http_error(mock_delete):
    mock_response = MagicMock()
    mock_response.status_code = 403
    mock_response.text = "Forbidden"
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_response)
    mock_delete.return_value = mock_response

    with pytest.raises(RuntimeError) as excinfo:
        delete_collection("http://localhost:8096", "test_key", "col_1")
    assert "Failed to delete collection 'col_1' (Status 403): Forbidden" in str(excinfo.value)


@patch('requests.delete')
def test_delete_collection_request_exception(mock_delete):
    mock_delete.side_effect = requests.exceptions.RequestException("Gone")

    with pytest.raises(RuntimeError, match="Failed to delete collection 'col_1': Gone"):
        delete_collection("http://localhost:8096", "test_key", "col_1")


@patch('mimetypes.guess_type')
@patch('builtins.open')
@patch('requests.post')
def test_set_collection_image_success(mock_post, mock_open, mock_guess, caplog):
    mock_guess.return_value = ("image/png", None)
    mock_open.return_value.__enter__.return_value.read.return_value = b"png_data"
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_post.return_value = mock_response

    set_collection_image("http://localhost:8096", "test_key", "col_1", "/path/cover.png")

    mock_post.assert_called_once_with(
        "http://localhost:8096/Items/col_1/Images/Primary",
        data=b"png_data",
        headers={"X-Emby-Token": "test_key", "Content-Type": "image/png"},
        timeout=30,
    )
    assert "Successfully updated cover image for collection 'col_1'" in caplog.text


@patch('builtins.open')
def test_set_collection_image_os_error(mock_open, caplog):
    mock_open.side_effect = OSError("Permission denied")

    set_collection_image("http://localhost:8096", "test_key", "col_1", "/bad/path.jpg")
    assert "Cannot set collection image: Failed to read '/bad/path.jpg': Permission denied" in caplog.text


@patch('mimetypes.guess_type')
@patch('builtins.open')
@patch('requests.post')
def test_set_collection_image_unknown_mime(mock_post, mock_open, mock_guess, caplog):
    mock_guess.return_value = (None, None)
    mock_open.return_value.__enter__.return_value.read.return_value = b"data"
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_post.return_value = mock_response

    set_collection_image("http://localhost:8096", "test_key", "col_1", "/path/file.bin")

    call_headers = mock_post.call_args[1]["headers"]
    assert call_headers["Content-Type"] == "application/octet-stream"
    assert "Successfully updated cover image for collection 'col_1'" in caplog.text


@patch('mimetypes.guess_type')
@patch('builtins.open')
@patch('requests.post')
def test_set_collection_image_http_error(mock_post, mock_open, mock_guess, caplog):
    mock_guess.return_value = ("image/jpeg", None)
    mock_open.return_value.__enter__.return_value.read.return_value = b"jpeg_data"
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.text = "Bad Image"
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_response)
    mock_post.return_value = mock_response

    set_collection_image("http://localhost:8096", "test_key", "col_1", "/path/img.jpg")
    assert "Failed to set image for collection 'col_1' (Status 400): Bad Image" in caplog.text


@patch('mimetypes.guess_type')
@patch('builtins.open')
@patch('requests.post')
def test_set_collection_image_request_exception_no_response(mock_post, mock_open, mock_guess, caplog):
    mock_guess.return_value = ("image/jpeg", None)
    mock_open.return_value.__enter__.return_value.read.return_value = b"jpeg_data"
    mock_post.side_effect = requests.exceptions.RequestException("Upload Error")

    set_collection_image("http://localhost:8096", "test_key", "col_1", "/path/img.jpg")
    assert "Failed to set image for collection 'col_1': Upload Error" in caplog.text
