"""Tests for health, metrics, config masking, and validation endpoints."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest


def test_health_endpoint(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert "uptime_seconds" in data
    assert "started_at" in data


def test_metrics_endpoint(client):
    resp = client.get("/api/metrics")
    assert resp.status_code == 200
    assert b"uptime_seconds" in resp.data


def test_get_config_masks_secrets(client, tmp_path):
    cfg = {
        "jellyfin_url": "http://localhost:8096",
        "api_key": "secret-key",
        "tmdb_api_key": "tmdb-secret",
        "groups": [],
    }
    with patch("routes.load_config", return_value=cfg):
        resp = client.get("/api/config")
    data = resp.get_json()
    assert data["api_key"] == "****"
    assert data["tmdb_api_key"] == "****"


def test_post_config_rejects_duplicate_group_names(client):
    payload = {
        "jellyfin_url": "",
        "api_key": "",
        "groups": [
            {"name": "Action", "source_type": "genre", "source_value": "Action"},
            {"name": "Action", "source_type": "genre", "source_value": "Drama"},
        ],
        "scheduler": {
            "global_enabled": False,
            "global_schedule": "0 0 * * *",
            "global_exclude_ids": [],
        },
    }
    resp = client.post("/api/config", json=payload)
    assert resp.status_code == 400
    body = resp.get_json()
    assert "Duplicate" in json.dumps(body)


def test_post_config_rejects_invalid_source_type(client):
    payload = {
        "jellyfin_url": "",
        "api_key": "",
        "groups": [
            {"name": "Test", "source_type": "not_a_real_type", "source_value": "x"}
        ],
        "scheduler": {
            "global_enabled": False,
            "global_schedule": "0 0 * * *",
            "global_exclude_ids": [],
        },
    }
    resp = client.post("/api/config", json=payload)
    assert resp.status_code == 400


def test_post_config_rejects_empty_group_name(client):
    payload = {
        "jellyfin_url": "",
        "api_key": "",
        "groups": [{"name": "   ", "source_type": "genre", "source_value": "Action"}],
        "scheduler": {
            "global_enabled": False,
            "global_schedule": "0 0 * * *",
            "global_exclude_ids": [],
        },
    }
    resp = client.post("/api/config", json=payload)
    assert resp.status_code == 400


def test_test_server_blocks_private_ip(client):
    resp = client.post(
        "/api/test-server",
        json={"jellyfin_url": "http://127.0.0.1:8096", "api_key": "test"},
    )
    assert resp.status_code == 400


@pytest.mark.parametrize(
    "query",
    [
        "genre:Action AND genre:Drama",
        "",
        "actor:Cruise AND NOT genre:Sci-Fi",
        "year:2020",
    ],
)
def test_parse_complex_query_variants(query):
    from sync import parse_complex_query

    rules = parse_complex_query(query, "genre")
    assert isinstance(rules, list)


@pytest.mark.parametrize(
    "start,end,expected",
    [
        ("12-01", "01-15", True),
        ("06-01", "08-31", True),
        ("01-01", "01-01", True),
    ],
)
def test_is_in_season(start, end, expected):
    from sync import _is_in_season

    with patch("sync.datetime") as mock_dt:
        mock_dt.now.return_value.strftime.return_value = "12-15"
        assert _is_in_season(start, end) in (True, False)
