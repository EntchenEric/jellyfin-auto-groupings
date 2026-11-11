"""Unit tests for the module-level HTTP helpers in ``jellyfin.py``.

These guards exist so that a malformed Jellyfin response (a proxy rewriting
JSON, a differently-versioned server, an error page served with status 200)
turns into a clean ``RuntimeError`` instead of an ``AttributeError`` or
``TypeError`` deep inside a sync run.
"""

import logging
from unittest.mock import patch

import pytest
import requests

import jellyfin


class TestParseJson:
    def test_valid_json(self):
        response = requests.Response()
        response.status_code = 200
        response._content = b'{"ok": true}'
        assert jellyfin._parse_json(response) == {"ok": True}

    def test_invalid_json_raises_runtime_error(self):
        response = requests.Response()
        response.status_code = 502
        response._content = b"<html>Bad Gateway</html>"
        with pytest.raises(RuntimeError, match=r"Invalid JSON response.*502"):
            jellyfin._parse_json(response)


class TestFormatRequestError:
    def test_with_response_details(self):
        exc = requests.exceptions.HTTPError("500 Server Error")
        exc.response = requests.Response()
        exc.response.status_code = 500
        exc.response._content = b"boom"
        msg = jellyfin._format_request_error(exc, "GET /Items")
        assert msg.startswith("GET /Items")
        assert "Status 500" in msg
        assert "boom" in msg

    def test_without_response(self):
        exc = requests.exceptions.ConnectionError("connection refused")
        msg = jellyfin._format_request_error(exc, "GET /Users")
        assert msg == "GET /Users: connection refused"


class TestGetJsonObject:
    def test_object_passthrough(self):
        with patch.object(jellyfin.network, "get") as mock_get:
            mock_get.return_value.json.return_value = {"a": 1}
            assert jellyfin._get_json_object("http://x") == {"a": 1}

    def test_list_body_raises(self):
        with patch.object(jellyfin.network, "get") as mock_get:
            mock_get.return_value.json.return_value = [1, 2]
            with pytest.raises(RuntimeError, match=r"Expected a JSON object.*got list"):
                jellyfin._get_json_object("http://x")

    def test_null_body_raises(self):
        with patch.object(jellyfin.network, "get") as mock_get:
            mock_get.return_value.json.return_value = None
            with pytest.raises(RuntimeError, match=r"got NoneType"):
                jellyfin._get_json_object("http://x")


class TestGetJsonList:
    def test_list_passthrough_and_entry_filtering(self):
        with patch.object(jellyfin.network, "get") as mock_get:
            mock_get.return_value.json.return_value = [
                {"Id": "1"},
                "not-an-object",
                42,
            ]
            assert jellyfin._get_json_list("http://x") == [{"Id": "1"}]

    def test_object_body_raises(self):
        with patch.object(jellyfin.network, "get") as mock_get:
            mock_get.return_value.json.return_value = {"unexpected": "object"}
            with pytest.raises(RuntimeError, match=r"Expected a JSON array.*got dict"):
                jellyfin._get_json_list("http://x")

    def test_null_body_raises(self):
        with patch.object(jellyfin.network, "get") as mock_get:
            mock_get.return_value.json.return_value = None
            with pytest.raises(RuntimeError, match=r"got NoneType"):
                jellyfin._get_json_list("http://x")


class TestGetJsonRequestFailures:
    def test_get_json_translates_request_exception(self):
        with (
            patch.object(
                jellyfin.network,
                "get",
                side_effect=requests.ConnectionError("reset"),
            ),
            pytest.raises(RuntimeError, match="reset"),
        ):
            jellyfin._get_json("http://x")

    def test_post_or_raise_translates_request_exception(self):
        with (
            patch.object(
                jellyfin.network,
                "post",
                side_effect=requests.Timeout("timed out"),
            ),
            pytest.raises(RuntimeError, match="timed out"),
        ):
            jellyfin._post_or_raise("http://x", error_prefix="POST /Collections")

    def test_delete_or_raise_translates_request_exception(self):
        with (
            patch.object(
                jellyfin.network,
                "delete",
                side_effect=requests.ConnectionError("refused"),
            ),
            pytest.raises(RuntimeError, match="refused"),
        ):
            jellyfin._delete_or_raise("http://x")


class TestRequestOrRaise:
    def test_unsupported_method_raises_value_error(self):
        with pytest.raises(ValueError, match="Unsupported HTTP method: GET2"):
            jellyfin._request_or_raise("GET2", "http://x")

    def test_kwargs_forwarded(self):
        with patch.object(jellyfin.network, "put") as mock_put:
            mock_put.return_value.raise_for_status.return_value = None
            jellyfin._request_or_raise(
                "PUT",
                "http://x",
                headers={"h": "1"},
                params={"p": "2"},
                data=b"body",
                timeout=11,
                error_prefix="PUT /x",
            )
            kwargs = mock_put.call_args.kwargs
            assert kwargs["headers"] == {"h": "1"}
            assert kwargs["params"] == {"p": "2"}
            assert kwargs["data"] == b"body"
            assert kwargs["timeout"] == 11


class TestCoerceItemsList:
    def test_missing_items_yields_empty(self):
        assert jellyfin._coerce_items_list({}, "http://x") == []

    def test_null_items_yields_empty(self):
        assert jellyfin._coerce_items_list({"Items": None}, "http://x") == []

    def test_non_list_items_raises(self):
        with pytest.raises(RuntimeError, match=r"'Items' to be a JSON array.*got str"):
            jellyfin._coerce_items_list({"Items": "oops"}, "http://x")

    def test_non_object_entries_dropped(self):
        body = {"Items": [{"Id": "1"}, "junk", None, {"Id": "2"}]}
        assert jellyfin._coerce_items_list(body, "http://x") == [
            {"Id": "1"},
            {"Id": "2"},
        ]


class TestPageSignature:
    def test_ids_extracted(self):
        page = [{"Id": "b"}, {"Id": 10}, "junk", {"Name": "no id"}]
        assert jellyfin._page_signature(page) == ("b", "10")

    def test_empty_page_is_none(self):
        assert jellyfin._page_signature([]) is None

    def test_no_usable_ids_is_none(self):
        assert jellyfin._page_signature([{"Name": "x"}, "junk"]) is None


class TestTotalRecordCount:
    def test_int_passthrough(self):
        assert jellyfin._total_record_count({"TotalRecordCount": 42}) == 42

    def test_missing_is_none(self):
        assert jellyfin._total_record_count({}) is None

    def test_bool_is_none(self):
        assert jellyfin._total_record_count({"TotalRecordCount": True}) is None

    def test_numeric_string_converted(self):
        assert jellyfin._total_record_count({"TotalRecordCount": " 250 "}) == 250

    def test_non_numeric_string_warns_and_is_none(self, caplog):
        with caplog.at_level(logging.WARNING):
            assert jellyfin._total_record_count({"TotalRecordCount": "abc"}) is None
        assert "non-numeric TotalRecordCount" in caplog.text

    def test_other_types_warn_and_are_none(self, caplog):
        for value in ({"x": 1}, [1], 1.5):
            with caplog.at_level(logging.WARNING):
                assert jellyfin._total_record_count({"TotalRecordCount": value}) is None
            assert "malformed TotalRecordCount" in caplog.text
