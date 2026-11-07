"""Unit tests for the Jellyfin metadata endpoint.

``GET /api/jellyfin/metadata`` aggregates genres, studios, actors and tags
from Jellyfin's dedicated list endpoints via ``_fetch_jellyfin_endpoint``,
which is itself a thin walker over ``_paginate_jellyfin`` with a
partial-data-is-better-than-nothing error policy.  That policy (and the
route's own handling of fully-failed lookups) was previously only covered
by the e2e suite, which requires a live server.
"""

import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import routes
from app import app as flask_app


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as test_client:
        yield test_client


@pytest.fixture
def jellyfin_config(monkeypatch):
    monkeypatch.setattr(
        routes,
        "_get_jellyfin_config",
        lambda: ("http://jf", "key"),
    )


# ---------------------------------------------------------------------------
# _fetch_jellyfin_endpoint
# ---------------------------------------------------------------------------


def test_fetch_endpoint_collects_all_pages(monkeypatch):
    pages = [[{"Name": "Action"}], [{"Name": "Drama"}]]

    def fake_paginate(*_args, **_kwargs):
        yield from pages

    monkeypatch.setattr(routes, "_paginate_jellyfin", fake_paginate)

    assert routes._fetch_jellyfin_endpoint(
        "http://jf", "key", "Genres"
    ) == [{"Name": "Action"}, {"Name": "Drama"}]


def test_fetch_endpoint_returns_empty_when_no_pages(monkeypatch):
    def fake_paginate(*_args, **_kwargs):
        return iter(())
        yield  # pragma: no cover

    monkeypatch.setattr(routes, "_paginate_jellyfin", fake_paginate)

    assert routes._fetch_jellyfin_endpoint("http://jf", "key", "Tags") == []


def test_fetch_endpoint_keeps_partial_data_on_walk_failure(monkeypatch, caplog):
    """An error after some data is fetched returns what we have."""
    import logging

    def fake_paginate(*_args, **_kwargs):
        yield [{"Name": "Action"}]
        raise RuntimeError("server exploded mid-walk")

    monkeypatch.setattr(routes, "_paginate_jellyfin", fake_paginate)

    with caplog.at_level(logging.DEBUG):
        result = routes._fetch_jellyfin_endpoint("http://jf", "key", "Genres")

    assert result == [{"Name": "Action"}]
    assert "Partial fetch" in caplog.text


def test_fetch_endpoint_reraises_when_nothing_fetched(monkeypatch):
    def fake_paginate(*_args, **_kwargs):
        raise RuntimeError("connection refused")
        yield  # pragma: no cover

    monkeypatch.setattr(routes, "_paginate_jellyfin", fake_paginate)

    with pytest.raises(RuntimeError, match="connection refused"):
        routes._fetch_jellyfin_endpoint("http://jf", "key", "Genres")


def test_fetch_endpoint_partial_data_survives_request_errors(monkeypatch):
    def fake_paginate(*_args, **_kwargs):
        yield [{"Name": "Fox"}]
        raise requests.RequestException("network dropped")

    monkeypatch.setattr(routes, "_paginate_jellyfin", fake_paginate)

    result = routes._fetch_jellyfin_endpoint(
        "http://jf", "key", "Studios", timeout=3
    )
    assert result == [{"Name": "Fox"}]


def test_fetch_endpoint_request_error_without_data_reraises(monkeypatch):
    def fake_paginate(*_args, **_kwargs):
        raise requests.ConnectionError("unreachable")
        yield  # pragma: no cover

    monkeypatch.setattr(routes, "_paginate_jellyfin", fake_paginate)

    with pytest.raises(requests.ConnectionError):
        routes._fetch_jellyfin_endpoint("http://jf", "key", "Studios")


# ---------------------------------------------------------------------------
# GET /api/jellyfin/metadata
# ---------------------------------------------------------------------------


def _patch_parallel_fetch(monkeypatch, results):
    """Force ``_fetch_jellyfin_endpoint`` to return canned results."""

    def fake_fetch(_base, _key, endpoint, **_kwargs):
        return results.get(endpoint, [])

    monkeypatch.setattr(routes, "_fetch_jellyfin_endpoint", fake_fetch)


def test_metadata_route_aggregates_and_trims(client, jellyfin_config, monkeypatch):
    _patch_parallel_fetch(
        monkeypatch,
        {
            "Genres": [{"Name": "Action"}, {"Name": ""}, {"Name": "Drama"}],
            "Studios": [{"Name": "Universal"}],
            "Persons": [{"Name": "Keanu"}, {"Name": "Carrie"}],
            "Tags": [],
        },
    )

    resp = client.get("/api/jellyfin/metadata")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "success"
    assert body["metadata"] == {
        "genre": ["Action", "Drama"],
        "studio": ["Universal"],
        "actor": ["Keanu", "Carrie"],
        "tag": [],
    }


def test_metadata_route_marks_failed_keys_and_returns_them_empty(
    client, jellyfin_config, monkeypatch
):
    """One failed lookup downgrades to an empty list, not an error."""
    import logging

    def fake_fetch(_base, _key, endpoint, **_kwargs):
        if endpoint == "Tags":
            raise RuntimeError("tags endpoint broken")
        return [{"Name": "x"}]

    monkeypatch.setattr(routes, "_fetch_jellyfin_endpoint", fake_fetch)

    logging.disable(logging.WARNING)
    try:
        resp = client.get("/api/jellyfin/metadata")
    finally:
        logging.disable(logging.NOTSET)

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "success"
    assert body["metadata"]["tag"] == []
    assert body["metadata"]["genre"] == ["x"]


def test_metadata_route_rejects_when_every_lookup_fails(
    client, jellyfin_config, monkeypatch
):
    def fake_fetch(*_args, **_kwargs):
        raise RuntimeError("down")

    monkeypatch.setattr(routes, "_fetch_jellyfin_endpoint", fake_fetch)

    resp = client.get("/api/jellyfin/metadata")
    assert resp.status_code == 400
    assert resp.get_json()["message"] == "Failed to fetch metadata from Jellyfin"


def test_metadata_route_unexpected_error_is_500(
    client, jellyfin_config, monkeypatch
):
    def boom(*_args, **_kwargs):
        raise OSError("no route to host")

    monkeypatch.setattr(routes, "_get_jellyfin_config", boom)

    resp = client.get("/api/jellyfin/metadata")
    assert resp.status_code == 500
