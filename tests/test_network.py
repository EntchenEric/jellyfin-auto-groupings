"""Tests for network.py retry logic and error handling."""

import pytest
import requests
from urllib3.exceptions import MaxRetryError, ReadTimeoutError, ConnectTimeoutError


def test_reraise_timeout_read():
    """_reraise_timeout re-raises Timeout when wrapping a ReadTimeoutError."""
    from network import _reraise_timeout

    read_err = ReadTimeoutError("pool", "url", "msg")
    max_retry = MaxRetryError("pool", "url", reason=read_err)
    conn_err = requests.ConnectionError(max_retry)

    with pytest.raises(requests.Timeout):
        _reraise_timeout(conn_err)


def test_reraise_timeout_connect():
    """_reraise_timeout returns normally for ConnectTimeout, not ReadTimeout."""
    from network import _reraise_timeout

    connect_err = ConnectTimeoutError("pool", "url", "msg")
    max_retry = MaxRetryError("pool", "url", reason=connect_err)
    conn_err = requests.ConnectionError(max_retry)

    _reraise_timeout(conn_err)  # should not raise


def test_reraise_timeout_plain_connection_error():
    """_reraise_timeout returns normally for ConnectionError without MaxRetryError."""
    from network import _reraise_timeout

    conn_err = requests.ConnectionError("plain error")
    _reraise_timeout(conn_err)  # should not raise


def test_reraise_timeout_empty_args():
    """_reraise_timeout handles ConnectionError with no args."""
    from network import _reraise_timeout

    conn_err = requests.ConnectionError()
    _reraise_timeout(conn_err)  # should not raise


def test_patched_get_success(monkeypatch):
    """_patched_get delegates to session and returns response."""
    from network import _patched_get, _SESSION

    class FakeResp:
        status_code = 200

        def json(self):
            return {"ok": True}

        def raise_for_status(self):
            pass

    monkeypatch.setattr(_SESSION, "get", lambda url, **kw: FakeResp())
    result = _patched_get("http://example.com/api")
    assert result.json() == {"ok": True}


def test_patched_get_timeout_re_raise(monkeypatch):
    """_patched_get re-raises ReadTimeout as requests.Timeout."""
    from network import _patched_get, _SESSION

    read_err = ReadTimeoutError("pool", "url", "msg")
    max_retry = MaxRetryError("pool", "url", reason=read_err)
    conn_err = requests.ConnectionError(max_retry)

    def _fail(*a, **kw):
        raise conn_err

    monkeypatch.setattr(_SESSION, "get", _fail)
    with pytest.raises(requests.Timeout):
        _patched_get("http://example.com/api")


def test_patched_get_connection_error(monkeypatch):
    """_patched_get re-raises ConnectionError that is not a read timeout."""
    from network import _patched_get, _SESSION

    conn_err = requests.ConnectionError("genuine connection refused")

    def _fail(*a, **kw):
        raise conn_err

    monkeypatch.setattr(_SESSION, "get", _fail)
    with pytest.raises(requests.ConnectionError) as excinfo:
        _patched_get("http://example.com/api")
    assert "genuine connection refused" in str(excinfo.value)


def test_patched_post_success(monkeypatch):
    """_patched_post delegates to session."""
    from network import _patched_post, _SESSION

    class FakeResp:
        status_code = 201

        def json(self):
            return {"created": True}

        def raise_for_status(self):
            pass

    monkeypatch.setattr(_SESSION, "post", lambda url, **kw: FakeResp())
    result = _patched_post("http://example.com/api")
    assert result.json() == {"created": True}


def test_patched_post_timeout_re_raise(monkeypatch):
    """_patched_post re-raises ReadTimeout as requests.Timeout."""
    from network import _patched_post, _SESSION

    read_err = ReadTimeoutError("pool", "url", "msg")
    max_retry = MaxRetryError("pool", "url", reason=read_err)
    conn_err = requests.ConnectionError(max_retry)

    def _fail(*a, **kw):
        raise conn_err

    monkeypatch.setattr(_SESSION, "post", _fail)
    with pytest.raises(requests.Timeout):
        _patched_post("http://example.com/api")


def test_patched_delete_success(monkeypatch):
    """_patched_delete delegates to session."""
    from network import _patched_delete, _SESSION

    class FakeResp:
        status_code = 204

        def json(self):
            return {}

        def raise_for_status(self):
            pass

    monkeypatch.setattr(_SESSION, "delete", lambda url, **kw: FakeResp())
    result = _patched_delete("http://example.com/api")
    assert result.status_code == 204


def test_patched_delete_timeout_re_raise(monkeypatch):
    """_patched_delete re-raises ReadTimeout as requests.Timeout."""
    from network import _patched_delete, _SESSION

    read_err = ReadTimeoutError("pool", "url", "msg")
    max_retry = MaxRetryError("pool", "url", reason=read_err)
    conn_err = requests.ConnectionError(max_retry)

    def _fail(*a, **kw):
        raise conn_err

    monkeypatch.setattr(_SESSION, "delete", _fail)
    with pytest.raises(requests.Timeout):
        _patched_delete("http://example.com/api")
