from unittest.mock import patch, MagicMock
import pytest
from jellyfin import get_libraries, add_virtual_folder, delete_virtual_folder

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
