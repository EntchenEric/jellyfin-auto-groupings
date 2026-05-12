import pytest
import requests
from jellyfin import (
    get_libraries, 
    add_virtual_folder, 
    delete_virtual_folder, 
    get_library_id, 
    set_virtual_folder_image, 
    get_users, 
    get_user_recent_items
)

@pytest.fixture
def jellyfin_url(virtual_jellyfin):
    return virtual_jellyfin

def test_get_libraries(jellyfin_url):
    libs = get_libraries(jellyfin_url, "test_key")
    # virtual_jellyfin starts with Movies and TV Shows
    assert "Movies" in libs
    assert "TV Shows" in libs

def test_add_virtual_folder_success(jellyfin_url):
    name = "NewLib"
    add_virtual_folder(jellyfin_url, "test_key", name, ["/tmp/path1"])
    
    libs = get_libraries(jellyfin_url, "test_key")
    assert name in libs

def test_add_virtual_folder_already_exists(jellyfin_url):
    name = "Movies" # Already exists in virtual_jellyfin
    # add_virtual_folder should handle 409 and not raise
    add_virtual_folder(jellyfin_url, "test_key", name, ["/tmp/path2"])

def test_delete_virtual_folder(jellyfin_url):
    name = "ToStore"
    add_virtual_folder(jellyfin_url, "test_key", name, ["/tmp/path"])
    
    delete_virtual_folder(jellyfin_url, "test_key", name)
    
    libs = get_libraries(jellyfin_url, "test_key")
    assert name not in libs

def test_get_library_id(jellyfin_url):
    item_id = get_library_id(jellyfin_url, "test_key", "Movies")
    assert item_id == "movies_id"
    
    item_id_none = get_library_id(jellyfin_url, "test_key", "NonExistent")
    assert item_id_none is None

def test_set_virtual_folder_image(jellyfin_url, tmp_path):
    img_path = tmp_path / "test.jpg"
    img_path.write_bytes(b"fake_image_data")
    
    # This should not raise
    set_virtual_folder_image(jellyfin_url, "test_key", "Movies", str(img_path))

def test_get_users(jellyfin_url):
    users = get_users(jellyfin_url, "test_key")
    assert len(users) >= 1
    assert users[0]["Name"] == "Admin"

def test_get_user_recent_items(jellyfin_url):
    items = get_user_recent_items(jellyfin_url, "test_key", "admin_id", limit=10)
    assert len(items) >= 2
    assert items[0]["Name"] == "Inception"
