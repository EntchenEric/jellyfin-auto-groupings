import sys
import os
import json
import shutil
import threading
import time
import requests
import pytest
from unittest.mock import MagicMock, patch
from tests.virtual_jellyfin import app as jelly_mock_app

@pytest.fixture(scope="session")
def virtual_jellyfin():
    """Fixture to run a virtual Jellyfin server in a background thread."""
    server_thread = threading.Thread(target=lambda: jelly_mock_app.run(port=8096, debug=False, use_reloader=False))
    server_thread.daemon = True
    server_thread.start()
    
    # Wait for server to be ready
    base_url = "http://localhost:8096"
    timeout = 5
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            requests.get(f"{base_url}/Library/VirtualFolders")
            break
        except requests.exceptions.ConnectionError:
            time.sleep(0.1)
    else:
        pytest.fail("Virtual Jellyfin server failed to start")
        
    return base_url

@pytest.fixture(autouse=True)
def mock_scheduler():
    patcher = patch('scheduler._scheduler')
    mock_bg_sched_instance = patcher.start()
    yield mock_bg_sched_instance
    patcher.stop()

from app import app as flask_app
from config import DEFAULT_CONFIG, CONFIG_DIR

@pytest.fixture
def app():
    from copy import deepcopy
    old_config = deepcopy(flask_app.config)
    flask_app.config.update({
        "TESTING": True,
    })
    
    with flask_app.app_context():
        yield flask_app
    
    flask_app.config = old_config

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def temp_config(tmp_path):
    """Fixture to provide a temporary configuration file."""
    test_config_dir = tmp_path / "config"
    test_config_dir.mkdir()
    test_config_file = test_config_dir / "config.json"
    
    # Mock CONFIG_FILE in config module
    import config
    original_config_file = config.CONFIG_FILE
    original_config_dir = config.CONFIG_DIR
    
    config.CONFIG_FILE = str(test_config_file)
    config.CONFIG_DIR = str(test_config_dir)
    
    yield test_config_file
    
    # Restore original paths
    config.CONFIG_FILE = original_config_file
    config.CONFIG_DIR = original_config_dir

@pytest.fixture
def mock_jellyfin_items():
    return [
        {
            "Id": "1",
            "Name": "Movie 1",
            "Path": "/media/movies/Movie 1 (2020)/movie.mkv",
            "ProductionYear": 2020,
            "Genres": ["Action"],
            "ProviderIds": {"Imdb": "tt1234567"},
            "People": [{"Name": "Actor A", "Type": "Actor"}]
        },
        {
            "Id": "2",
            "Name": "Movie 2",
            "Path": "/media/movies/Movie 2 (2021)/movie.mkv",
            "ProductionYear": 2021,
            "Genres": ["Comedy"],
            "ProviderIds": {"Imdb": "tt7654321"},
            "People": [{"Name": "Actor B", "Type": "Actor"}]
        }
    ]
