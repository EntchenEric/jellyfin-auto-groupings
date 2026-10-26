"""Tests for the retry helpers in ``network.py``.

The retry adapter wraps the underlying urllib3 failure in a
``MaxRetryError``, which ``_reraise_timeout`` unwraps into the exception a
caller expects. The distinction that matters is *why* the request failed:

- a read timeout means the server accepted the connection and stalled;
- a connect timeout means the TCP handshake never completed;
- anything else (refused port, DNS failure, unreachable network) is neither
  and must keep its original message.

``urllib3.exceptions.NewConnectionError`` inherits from
``ConnectTimeoutError``, so a naive ``isinstance`` check collapses the third
case into the second. That relabelled every "connection refused" and
"name resolution failed" error as "Connection timed out." and dropped the
host, the URL and the ``errno`` from the message the UI shows.
"""

from __future__ import annotations

import pytest
import requests
from urllib3.exceptions import (
    ConnectTimeoutError,
    MaxRetryError,
    NewConnectionError,
    ReadTimeoutError,
)

from network import _reraise_timeout


def _wrapped(reason: Exception) -> requests.ConnectionError:
    """Return the ``requests.ConnectionError`` the retry adapter would raise."""
    return requests.ConnectionError(MaxRetryError("pool", "/url", reason))


def test_read_timeout_becomes_requests_timeout() -> None:
    """A read timeout is surfaced as ``requests.Timeout``."""
    exc = _wrapped(ReadTimeoutError("pool", "/url", "read timed out"))

    with pytest.raises(requests.Timeout, match=r"Read timed out\."):
        _reraise_timeout(exc)


def test_connect_timeout_becomes_connection_error() -> None:
    """A connect timeout stays a ``ConnectionError`` with a clear message."""
    exc = _wrapped(ConnectTimeoutError("pool", "/url", "connect timed out"))

    with pytest.raises(requests.ConnectionError, match=r"Connection timed out\."):
        _reraise_timeout(exc)


def test_new_connection_error_is_not_relabelled_as_timeout() -> None:
    """A refused port keeps its own message instead of "Connection timed out."."""
    reason = NewConnectionError(
        None,
        "Failed to establish a new connection: [Errno 111] Connection refused",
    )
    exc = _wrapped(reason)

    # Returning normally makes ``_request`` re-raise the original error, whose
    # message names the host, the port and the errno.
    _reraise_timeout(exc)


def test_new_connection_error_subclasses_connect_timeout() -> None:
    """Guard the assumption behind the ordering in ``_reraise_timeout``.

    If urllib3 ever stops deriving ``NewConnectionError`` from
    ``ConnectTimeoutError`` this test fails, which is the signal that the
    explicit ``NewConnectionError`` branch may be dropped.
    """
    assert issubclass(NewConnectionError, ConnectTimeoutError)


def test_plain_connection_error_is_ignored() -> None:
    """A ``ConnectionError`` not wrapping ``MaxRetryError`` is left untouched."""
    _reraise_timeout(requests.ConnectionError("plain error"))


def test_connection_error_without_args_is_ignored() -> None:
    """An argument-less ``ConnectionError`` does not raise ``IndexError``."""
    _reraise_timeout(requests.ConnectionError())


def test_other_max_retry_reason_is_ignored() -> None:
    """A non-timeout ``MaxRetryError`` reason is passed through unchanged."""
    _reraise_timeout(_wrapped(ValueError("something else")))


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0", 0),
        ("5", 5),
        (" 2 ", 2),
    ],
)
def test_parse_total_accepts_integers(
    monkeypatch: pytest.MonkeyPatch,
    raw: str,
    expected: int,
) -> None:
    """``NETWORK_RETRY_TOTAL`` accepts non-negative integers."""
    import network

    monkeypatch.setenv("NETWORK_RETRY_TOTAL", raw)
    total, _backoff, _statuses = network._parse_retry_config()
    assert total == expected


def test_parse_total_falls_back_on_garbage(monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-numeric total warns and falls back to 3 rather than crashing."""
    import network

    monkeypatch.setenv("NETWORK_RETRY_TOTAL", "three")
    total, _backoff, _statuses = network._parse_retry_config()
    assert total == 3


def test_parse_total_rejects_negative(monkeypatch: pytest.MonkeyPatch) -> None:
    """A negative total is a configuration error, not a silent default."""
    import network

    monkeypatch.setenv("NETWORK_RETRY_TOTAL", "-1")
    with pytest.raises(ValueError, match="must be non-negative"):
        network._parse_retry_config()


@pytest.mark.parametrize("raw", ["nan", "inf", "-inf"])
def test_parse_backoff_rejects_non_finite(
    monkeypatch: pytest.MonkeyPatch,
    raw: str,
) -> None:
    """NaN and infinity fall back to 1.0; they would break ``Retry``'s backoff."""
    import network

    monkeypatch.setenv("NETWORK_RETRY_BACKOFF_FACTOR", raw)
    _total, backoff, _statuses = network._parse_retry_config()
    assert backoff == 1.0


def test_parse_backoff_falls_back_on_garbage(monkeypatch: pytest.MonkeyPatch) -> None:
    """A non-numeric backoff warns and falls back to 1.0."""
    import network

    monkeypatch.setenv("NETWORK_RETRY_BACKOFF_FACTOR", "fast")
    _total, backoff, _statuses = network._parse_retry_config()
    assert backoff == 1.0


def test_parse_backoff_rejects_negative(monkeypatch: pytest.MonkeyPatch) -> None:
    """A negative backoff is a configuration error."""
    import network

    monkeypatch.setenv("NETWORK_RETRY_BACKOFF_FACTOR", "-0.5")
    with pytest.raises(ValueError, match="must be non-negative"):
        network._parse_retry_config()


def test_parse_forcelist_tolerates_blank_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Trailing and doubled commas are skipped, not treated as failures."""
    import network

    monkeypatch.setenv("NETWORK_RETRY_STATUS_FORCELIST", "429,, 503,")
    _total, _backoff, statuses = network._parse_retry_config()
    assert statuses == [429, 503]


def test_parse_forcelist_skips_non_numeric_entries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-numeric status is logged and dropped."""
    import network

    monkeypatch.setenv("NETWORK_RETRY_STATUS_FORCELIST", "500,oops,502")
    _total, _backoff, statuses = network._parse_retry_config()
    assert statuses == [500, 502]


@pytest.mark.parametrize("raw", ["99", "600", "0"])
def test_parse_forcelist_rejects_out_of_range_status(
    monkeypatch: pytest.MonkeyPatch,
    raw: str,
) -> None:
    """A numeric but non-HTTP status is a configuration error."""
    import network

    monkeypatch.setenv("NETWORK_RETRY_STATUS_FORCELIST", raw)
    with pytest.raises(ValueError, match="invalid HTTP status code"):
        network._parse_retry_config()


def test_empty_forcelist_disables_status_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty forcelist is valid and means no status-based retries."""
    import network

    monkeypatch.setenv("NETWORK_RETRY_STATUS_FORCELIST", "")
    _total, _backoff, statuses = network._parse_retry_config()
    assert statuses == []


class _FakeSession:
    """Minimal stand-in for ``requests.Session`` that always raises *exc*.

    Every HTTP verb is exposed, because ``_request`` resolves the verb on the
    session with ``getattr``.
    """

    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    def __getattr__(self, name: str) -> object:
        if name not in {"get", "post", "put", "patch", "delete", "head"}:
            msg = f"{type(self).__name__!r} has no attribute {name!r}"
            raise AttributeError(msg)

        def _raise(*_args: object, **_kwargs: object) -> None:
            raise self._exc

        return _raise


@pytest.mark.parametrize("method", ["get", "post", "put", "patch", "delete"])
def test_public_helpers_preserve_refused_connection(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
) -> None:
    """Every public helper re-raises a refused connection with its own text."""
    import network

    reason = NewConnectionError(None, "[Errno 111] Connection refused")
    original = _wrapped(reason)
    monkeypatch.setattr(network, "_SESSION", _FakeSession(original))

    with pytest.raises(requests.ConnectionError) as caught:
        getattr(network, method)("http://example.invalid/api")

    # The handler must not have replaced the exception: the message still
    # carries the urllib3 cause rather than the generic timeout wording.
    assert caught.value is original
    assert "Connection refused" in str(caught.value)


@pytest.mark.parametrize("method", ["get", "post", "put", "patch", "delete"])
def test_public_helpers_still_translate_read_timeouts(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
) -> None:
    """A wrapped read timeout becomes ``requests.Timeout`` from every helper."""
    import network

    original = _wrapped(ReadTimeoutError("pool", "/url", "read timed out"))
    monkeypatch.setattr(network, "_SESSION", _FakeSession(original))

    with pytest.raises(requests.Timeout, match=r"Read timed out\."):
        getattr(network, method)("http://example.invalid/api")


def test_invalid_config_at_import_falls_back_to_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A broken ``NETWORK_RETRY_*`` value never prevents the module importing.

    The module parses its retry configuration at import time; one bad
    environment variable must not make ``import network`` fail for every
    caller, so the parse error is caught and the documented defaults win.
    """
    import importlib

    import network

    monkeypatch.setenv("NETWORK_RETRY_STATUS_FORCELIST", "600")
    try:
        importlib.reload(network)
        assert network._RETRY_TOTAL == 3
        assert network._RETRY_BACKOFF_FACTOR == 1.0
        assert network._RETRY_STATUS_FORCELIST == [429, 500, 502, 503, 504]
    finally:
        monkeypatch.delenv("NETWORK_RETRY_STATUS_FORCELIST", raising=False)
        importlib.reload(network)
