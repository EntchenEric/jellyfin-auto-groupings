"""E2E test configuration and fixtures.

These tests require a running Jellyfin instance and the app server.
Run with: pytest tests/test_e2e/ -v -m e2e
"""

import os
import json
import time
import pytest
import requests


E2E_APP_URL = os.environ.get("E2E_APP_URL", "http://localhost:5005")
E2E_JELLYFIN_URL = os.environ.get("E2E_JELLYFIN_URL", "http://localhost:8096")
E2E_JELLYFIN_URL_INTERNAL = os.environ.get("E2E_JELLYFIN_URL_INTERNAL", "http://jellyfin:8096")
E2E_API_KEY = os.environ.get("JELLYFIN_API_KEY", "")


def wait_for_app(timeout=30):
    """Wait for the app server to be ready."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = requests.get(f"{E2E_APP_URL}/api/config", timeout=3)
            if resp.status_code == 200:
                return True
        except requests.ConnectionError:
            pass
        time.sleep(1)
    return False


def wait_for_jellyfin(timeout=30):
    """Wait for Jellyfin to be healthy."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = requests.get(f"{E2E_JELLYFIN_URL}/health", timeout=3)
            if resp.status_code == 200:
                return True
        except requests.ConnectionError:
            pass
        time.sleep(1)
    return False


@pytest.fixture(scope="session")
def e2e_app_url():
    """Ensure the app is running and return its base URL."""
    if not wait_for_app():
        pytest.skip("E2E app server not available")
    return E2E_APP_URL


@pytest.fixture(scope="session")
def e2e_jellyfin_url():
    """Ensure Jellyfin is running and return its base URL."""
    if not wait_for_jellyfin():
        pytest.skip("E2E Jellyfin server not available")
    return E2E_JELLYFIN_URL


@pytest.fixture(scope="session")
def e2e_api_key():
    """Return the Jellyfin API key for E2E tests."""
    if not E2E_API_KEY:
        pytest.skip("JELLYFIN_API_KEY not set")
    return E2E_API_KEY


@pytest.fixture(scope="session")
def e2e_session(e2e_app_url, e2e_jellyfin_url, e2e_api_key):
    """Configure the app with Jellyfin connection for E2E tests."""
    # Save config with Jellyfin connection details.
    # Use the Docker-internal URL for Jellyfin so the app container can reach it.
    config = {
        "jellyfin_url": E2E_JELLYFIN_URL_INTERNAL,
        "api_key": e2e_api_key,
        "target_path": "/tmp/e2e-test-output",
        "media_path_in_jellyfin": "/media",
        "media_path_on_host": "/media",
        "target_path_in_jellyfin": "/groupings",
        "setup_done": True,
        "groups": [],
        "scheduler": {
            "global_enabled": False,
            "global_schedule": "",
            "global_exclude_ids": [],
            "cleanup_enabled": False,
            "cleanup_schedule": ""
        }
    }
    resp = requests.post(f"{e2e_app_url}/api/config", json=config, timeout=10)
    assert resp.status_code == 200
    yield {
        "app_url": e2e_app_url,
        "jellyfin_url": e2e_jellyfin_url,
        "jellyfin_url_internal": E2E_JELLYFIN_URL_INTERNAL,
        "api_key": e2e_api_key
    }


def api_post(session, path, data=None):
    """Helper to POST to the app API."""
    url = f"{session['app_url']}{path}"
    resp = requests.post(url, json=data or {}, timeout=10)
    return resp.json()


def api_get(session, path):
    """Helper to GET from the app API."""
    url = f"{session['app_url']}{path}"
    resp = requests.get(url, timeout=10)
    return resp.json()
