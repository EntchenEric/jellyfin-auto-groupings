from unittest.mock import patch, MagicMock
import pytest
from jellyfin import get_libraries, add_virtual_folder, delete_virtual_folder, get_library_id, set_virtual_folder_image, get_users, get_user_recent_items

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
        params={"api_key": "test_key"},
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
    assert users[0]["id"] == "u1"
    assert users[0]["name"] == "Alice"
    
    mock_get.assert_called_once_with(
        "http://localhost:8096/Users",
        params={"api_key": "test_key"},
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
        "api_key": "test_key",
        "Filters": "IsPlayed",
        "SortBy": "DatePlayed",
        "SortOrder": "Descending",
        "IncludeItemTypes": "Movie,Episode",
        "Recursive": "true",
        "Limit": 10
    }
    mock_get.assert_called_once_with(
        "http://localhost:8096/Users/u1/Items",
        params=expected_params,
        timeout=30
    )
