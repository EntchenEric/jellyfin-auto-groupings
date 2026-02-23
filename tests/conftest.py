import sys
import os
import json
import shutil
import pytest
from unittest.mock import MagicMock, patch

# Sys.modules mock removed as requested, using patch instead to prevent real thread start
patcher = patch('scheduler._scheduler')
mock_bg_sched_instance = patcher.start()

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
