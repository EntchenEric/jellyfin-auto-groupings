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


def test_reraise_timeout_maxretry_no_reason():
    """_reraise_timeout handles MaxRetryError with no reason attribute."""
    from network import _reraise_timeout

    # MaxRetryError raised directly as reason to cover code path where exc.args[0]
    # exists but has no .reason attribute
    class MaxRetryNoReason:
        pass

    mr = MaxRetryNoReason()
    conn_err = requests.ConnectionError(mr)
    _reraise_timeout(conn_err)  # should not raise


def test_reraise_timeout_maxretry_reason_none():
    """_reraise_timeout handles MaxRetryError with reason=None."""
    from network import _reraise_timeout

    max_retry = MaxRetryError("pool", "url", reason=None)
    conn_err = requests.ConnectionError(max_retry)
    _reraise_timeout(conn_err)  # should not raise


# ---------------------------------------------------------------------------
# network.py: _parse_retry_config edge cases
# ---------------------------------------------------------------------------


def test_parse_retry_config_defaults():
    """_parse_retry_config returns defaults when no env vars are set."""
    from network import _RETRY_TOTAL, _RETRY_BACKOFF_FACTOR, _RETRY_STATUS_FORCELIST

    assert _RETRY_TOTAL == 3
    assert _RETRY_BACKOFF_FACTOR == 1.0
    assert 429 in _RETRY_STATUS_FORCELIST
    assert 500 in _RETRY_STATUS_FORCELIST


def test_parse_retry_config_invalid_total_fallback(monkeypatch):
    """Invalid NETWORK_RETRY_TOTAL falls back to default 3."""
    monkeypatch.setenv("NETWORK_RETRY_TOTAL", "not-a-number")
    # Force re-import of the module to trigger re-parse
    import importlib
    import network as net
    importlib.reload(net)
    assert net._RETRY_TOTAL == 3


def test_parse_retry_config_negative_total(monkeypatch):
    """Negative NETWORK_RETRY_TOTAL raises ValueError."""
    monkeypatch.setenv("NETWORK_RETRY_TOTAL", "-1")
    from network import _parse_retry_config
    with pytest.raises(ValueError, match="must be non-negative"):
        _parse_retry_config()


def test_parse_retry_config_negative_backoff(monkeypatch):
    """Negative NETWORK_RETRY_BACKOFF_FACTOR raises ValueError."""
    monkeypatch.setenv("NETWORK_RETRY_BACKOFF_FACTOR", "-2.0")
    from network import _parse_retry_config
    with pytest.raises(ValueError, match="must be non-negative"):
        _parse_retry_config()


def test_parse_retry_config_invalid_backoff_fallback(monkeypatch):
    """Invalid NETWORK_RETRY_BACKOFF_FACTOR falls back to default 1.0."""
    monkeypatch.setenv("NETWORK_RETRY_BACKOFF_FACTOR", "xyz")
    import importlib
    import network as net
    importlib.reload(net)
    assert net._RETRY_BACKOFF_FACTOR == 1.0


def test_parse_retry_config_invalid_status_code_in_list(monkeypatch):
    """Invalid entry in NETWORK_RETRY_STATUS_FORCELIST raises ValueError."""
    monkeypatch.setenv("NETWORK_RETRY_STATUS_FORCELIST", "429,9999")
    from network import _parse_retry_config
    with pytest.raises(ValueError, match="invalid HTTP status code: 9999"):
        _parse_retry_config()


def test_parse_retry_config_non_numeric_status(monkeypatch):
    """Non-numeric entries in NETWORK_RETRY_STATUS_FORCELIST are skipped, valid ones kept."""
    monkeypatch.setenv("NETWORK_RETRY_STATUS_FORCELIST", "429,abc,503")
    import importlib
    import network as net
    importlib.reload(net)
    assert 429 in net._RETRY_STATUS_FORCELIST
    assert 503 in net._RETRY_STATUS_FORCELIST
    assert len(net._RETRY_STATUS_FORCELIST) == 2


def test_parse_retry_config_trailing_comma(monkeypatch):
    """Trailing commas in NETWORK_RETRY_STATUS_FORCELIST are tolerated."""
    monkeypatch.setenv("NETWORK_RETRY_STATUS_FORCELIST", "429,500,")
    import importlib
    import network as net
    importlib.reload(net)
    assert 429 in net._RETRY_STATUS_FORCELIST
    assert 500 in net._RETRY_STATUS_FORCELIST
    assert len(net._RETRY_STATUS_FORCELIST) == 2


def test_parse_retry_config_negative_status_code(monkeypatch):
    """Negative status code in NETWORK_RETRY_STATUS_FORCELIST raises ValueError."""
    monkeypatch.setenv("NETWORK_RETRY_STATUS_FORCELIST", "-1")
    from network import _parse_retry_config
    with pytest.raises(ValueError, match="invalid HTTP status code: -1"):
        _parse_retry_config()


def test_parse_retry_config_zero_status_code(monkeypatch):
    """Status code 0 in NETWORK_RETRY_STATUS_FORCELIST raises ValueError."""
    monkeypatch.setenv("NETWORK_RETRY_STATUS_FORCELIST", "0")
    from network import _parse_retry_config
    with pytest.raises(ValueError, match="invalid HTTP status code: 0"):
        _parse_retry_config()
