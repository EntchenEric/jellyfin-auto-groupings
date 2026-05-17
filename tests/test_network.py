"""Tests for network.py retry logic and error handling."""

import pytest
import requests
from urllib3.exceptions import ConnectTimeoutError, MaxRetryError, ReadTimeoutError


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


def testget_success(monkeypatch):
    """get delegates to session and returns response."""
    from network import _SESSION, get

    class FakeResp:
        status_code = 200

        def json(self):
            return {"ok": True}

        def raise_for_status(self):
            pass

    monkeypatch.setattr(_SESSION, "get", lambda url, **kw: FakeResp())
    result = get("http://example.com/api")
    assert result.json() == {"ok": True}


def testget_timeout_re_raise(monkeypatch):
    """get re-raises ReadTimeout as requests.Timeout."""
    from network import _SESSION, get

    read_err = ReadTimeoutError("pool", "url", "msg")
    max_retry = MaxRetryError("pool", "url", reason=read_err)
    conn_err = requests.ConnectionError(max_retry)

    def _fail(*a, **kw):
        raise conn_err

    monkeypatch.setattr(_SESSION, "get", _fail)
    with pytest.raises(requests.Timeout):
        get("http://example.com/api")


def testget_connection_error(monkeypatch):
    """get re-raises ConnectionError that is not a read timeout."""
    from network import _SESSION, get

    conn_err = requests.ConnectionError("genuine connection refused")

    def _fail(*a, **kw):
        raise conn_err

    monkeypatch.setattr(_SESSION, "get", _fail)
    with pytest.raises(requests.ConnectionError) as excinfo:
        get("http://example.com/api")
    assert "genuine connection refused" in str(excinfo.value)


def testpost_success(monkeypatch):
    """post delegates to session."""
    from network import _SESSION, post

    class FakeResp:
        status_code = 201

        def json(self):
            return {"created": True}

        def raise_for_status(self):
            pass

    monkeypatch.setattr(_SESSION, "post", lambda url, **kw: FakeResp())
    result = post("http://example.com/api")
    assert result.json() == {"created": True}


def testpost_timeout_re_raise(monkeypatch):
    """post re-raises ReadTimeout as requests.Timeout."""
    from network import _SESSION, post

    read_err = ReadTimeoutError("pool", "url", "msg")
    max_retry = MaxRetryError("pool", "url", reason=read_err)
    conn_err = requests.ConnectionError(max_retry)

    def _fail(*a, **kw):
        raise conn_err

    monkeypatch.setattr(_SESSION, "post", _fail)
    with pytest.raises(requests.Timeout):
        post("http://example.com/api")


def testdelete_success(monkeypatch):
    """delete delegates to session."""
    from network import _SESSION, delete

    class FakeResp:
        status_code = 204

        def json(self):
            return {}

        def raise_for_status(self):
            pass

    monkeypatch.setattr(_SESSION, "delete", lambda url, **kw: FakeResp())
    result = delete("http://example.com/api")
    assert result.status_code == 204


def testdelete_timeout_re_raise(monkeypatch):
    """delete re-raises ReadTimeout as requests.Timeout."""
    from network import _SESSION, delete

    read_err = ReadTimeoutError("pool", "url", "msg")
    max_retry = MaxRetryError("pool", "url", reason=read_err)
    conn_err = requests.ConnectionError(max_retry)

    def _fail(*a, **kw):
        raise conn_err

    monkeypatch.setattr(_SESSION, "delete", _fail)
    with pytest.raises(requests.Timeout):
        delete("http://example.com/api")


# ---------------------------------------------------------------------------
# network.py edge cases: MaxRetryError with non-read-timeout reason
# ---------------------------------------------------------------------------


def testpost_maxretry_non_readtimeout(monkeypatch):
    """post re-raises ConnectionError when MaxRetryError reason is not ReadTimeout."""
    from network import _SESSION, post

    connect_err = ConnectTimeoutError("pool", "url", "msg")
    max_retry = MaxRetryError("pool", "url", reason=connect_err)
    conn_err = requests.ConnectionError(max_retry)

    def _fail(*a, **kw):
        raise conn_err

    monkeypatch.setattr(_SESSION, "post", _fail)
    with pytest.raises(requests.ConnectionError):
        post("http://example.com/api")


def testdelete_maxretry_non_readtimeout(monkeypatch):
    """delete re-raises ConnectionError when MaxRetryError reason is not ReadTimeout."""
    from network import _SESSION, delete

    connect_err = ConnectTimeoutError("pool", "url", "msg")
    max_retry = MaxRetryError("pool", "url", reason=connect_err)
    conn_err = requests.ConnectionError(max_retry)

    def _fail(*a, **kw):
        raise conn_err

    monkeypatch.setattr(_SESSION, "delete", _fail)
    with pytest.raises(requests.ConnectionError):
        delete("http://example.com/api")
