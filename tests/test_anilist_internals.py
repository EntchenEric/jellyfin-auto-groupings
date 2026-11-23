"""Focused tests for anilist.py internals and error paths.

Covers the status normalization, payload extraction, API-URL validation,
and network/JSON failure handling that test_providers.py's single
test_anilist_fetch does not reach.
"""

import pytest
import requests

import anilist


# ---------------------------------------------------------------------------
# _resolve_anilist_status
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (None, None),
        ("", None),
        ("ALL", None),
        ("all", None),
        ("COMPLETED", "COMPLETED"),
        ("completed", "COMPLETED"),
        ("WATCHING", "CURRENT"),
        ("rewatching", "REPEATING"),
        ("PAUSED", "PAUSED"),
    ],
)
def test_resolve_status_valid(status, expected):
    assert anilist._resolve_anilist_status(status) == expected


def test_resolve_status_unknown_raises():
    with pytest.raises(ValueError, match="Unknown AniList status"):
        anilist._resolve_anilist_status("NOT_A_STATUS")


# ---------------------------------------------------------------------------
# _extract_media_ids
# ---------------------------------------------------------------------------


def test_extract_ids_happy_path():
    payload = {
        "data": {
            "MediaListCollection": {
                "lists": [
                    {"entries": [{"mediaId": 1}, {"mediaId": 2}]},
                    {"entries": [{"mediaId": 3}]},
                ]
            }
        }
    }
    assert anilist._extract_media_ids(payload) == [1, 2, 3]


def test_extract_ids_data_not_dict():
    assert anilist._extract_media_ids({"data": "nope"}) == []


def test_extract_ids_collection_missing():
    assert anilist._extract_media_ids({"data": {}}) == []


def test_extract_ids_lists_not_list():
    payload = {"data": {"MediaListCollection": {"lists": "oops"}}}
    assert anilist._extract_media_ids(payload) == []


def test_extract_ids_skips_malformed_entries():
    payload = {
        "data": {
            "MediaListCollection": {
                "lists": [
                    {"entries": ["not-a-dict", {"mediaId": "nope"}, None, {"mediaId": 7}]},
                    "not-a-list-dict",
                    {"entries": "not-a-list"},
                ]
            }
        }
    }
    assert anilist._extract_media_ids(payload) == [7]


def test_extract_ids_bool_is_not_an_id():
    payload = {
        "data": {"MediaListCollection": {"lists": [{"entries": [{"mediaId": True}]}]}}
    }
    assert anilist._extract_media_ids(payload) == []


def test_extract_missing_media_id_is_skipped():
    payload = {"data": {"MediaListCollection": {"lists": [{"entries": [{"foo": 1}]}]}}}
    assert anilist._extract_media_ids(payload) == []


# ---------------------------------------------------------------------------
# _resolve_anilist_api_url
# ---------------------------------------------------------------------------


def test_resolve_url_default_when_none():
    assert anilist._resolve_anilist_api_url(None) == anilist.ANILIST_API_URL


def test_resolve_url_accepts_custom_https_endpoint():
    url = "https://my-anilist-proxy.example.com/graphql"
    assert anilist._resolve_anilist_api_url(url) == url


def test_resolve_url_strips_query_and_fragment():
    resolved = anilist._resolve_anilist_api_url("https://proxy.example.com/gql?key=1#frag")
    assert resolved == "https://proxy.example.com/gql"


def test_resolve_url_rejects_prose():
    with pytest.raises(ValueError, match="Invalid AniList API URL"):
        anilist._resolve_anilist_api_url("not a url")


def test_resolve_url_rejects_userinfo_ambiguity():
    with pytest.raises(ValueError, match="Invalid AniList API URL"):
        anilist._resolve_anilist_api_url("https://evil.example\\@graphql.anilist.co")


def test_resolve_url_rejects_non_http_scheme():
    with pytest.raises(ValueError, match="Invalid AniList API URL"):
        anilist._resolve_anilist_api_url("ftp://proxy.example.com/gql")


# ---------------------------------------------------------------------------
# fetch_anilist_list error paths
# ---------------------------------------------------------------------------


def _ok_response(payload):
    resp = requests.Response()
    resp.status_code = 200
    resp._content = b"{}"
    resp.headers["Content-Type"] = "application/json"
    if payload is not None:
        import json

        resp._content = json.dumps(payload).encode()
    return resp


def test_fetch_wraps_request_exception():
    with patch_network_post(None, side_effect=requests.ConnectionError("boom")):
        with pytest.raises(RuntimeError, match="Failed to fetch AniList list"):
            anilist.fetch_anilist_list("user")


def test_fetch_wraps_invalid_json():
    resp = requests.Response()
    resp.status_code = 200
    resp._content = b"definitely-not-json{"
    with patch_network_post(resp):
        with pytest.raises(RuntimeError, match="Invalid JSON response"):
            anilist.fetch_anilist_list("user")


def test_fetch_wraps_bare_list_payload():
    with patch_network_post(_ok_response([1, 2, 3])):
        with pytest.raises(RuntimeError, match="Unexpected AniList API response shape"):
            anilist.fetch_anilist_list("user")


def test_fetch_bare_object_payload_returns_no_ids():
    with patch_network_post(_ok_response({})):
        assert anilist.fetch_anilist_list("user") == []


def test_fetch_collects_ids():
    payload = {
        "data": {"MediaListCollection": {"lists": [{"entries": [{"mediaId": 42}]}]}}
    }
    with patch_network_post(_ok_response(payload)):
        assert anilist.fetch_anilist_list("user") == [42]


def test_fetch_sends_status_variable():
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured.update(json or {})
        return _ok_response({"data": {}})

    with patch_network_post(None, side_effect=fake_post):
        anilist.fetch_anilist_list("user", status="COMPLETED")
    assert captured["variables"]["status"] == "COMPLETED"
    assert captured["variables"]["userName"] == "user"


def test_fetch_omits_status_when_all():
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured.update(json or {})
        return _ok_response({})

    with patch_network_post(None, side_effect=fake_post):
        anilist.fetch_anilist_list("user", status="ALL")
    assert "status" not in captured["variables"]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def patch_network_post(response=None, side_effect=None):
    from unittest.mock import patch as _patch

    kwargs = {"return_value": response}
    if side_effect is not None:
        kwargs.pop("return_value")
        kwargs["side_effect"] = side_effect
    return _patch.object(anilist.network, "post", **kwargs)
