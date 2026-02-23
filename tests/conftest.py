import sys
import os
import json
import shutil
import pytest
from unittest.mock import MagicMock, patch

# We don't want the real BackgroundScheduler to run during tests
# but we DO want to be able to import and test the scheduler module.
mock_bg_sched_class = MagicMock()
sys.modules.setdefault('apscheduler', mock_bg_sched_class)
sys.modules.setdefault('apscheduler.schedulers.background', mock_bg_sched_class)

from app import app as flask_app
from config import DEFAULT_CONFIG, CONFIG_DIR

@pytest.fixture
def app():
    flask_app.config.update({
        "TESTING": True,
    })
    yield flask_app

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
