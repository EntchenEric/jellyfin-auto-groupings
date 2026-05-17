"""network.py - Retry-aware HTTP for external API calls.

Importing this module monkey-patches ``requests.get``, ``requests.post``, and
``requests.delete`` to use a shared :class:`requests.Session` configured with
exponential-backoff retry on transient failures (5xx, connection errors).

All modules that ``import requests`` after this module has been loaded
automatically benefit from retry logic with **zero code changes**.

Tests that ``@patch('module.requests.get')`` continue to work because the mock
replaces the monkey-patched function, not the underlying session.
"""

from __future__ import annotations

import logging
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.exceptions import MaxRetryError, ReadTimeoutError
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

_RETRY_TOTAL = 3
_RETRY_BACKOFF_FACTOR = 1.0
_RETRY_STATUS_FORCELIST = [429, 500, 502, 503, 504]
_ALLOWED_RETRY_METHODS = frozenset({"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"})


def _build_retry_session() -> requests.Session:
    """Create a :class:`requests.Session` with retry logic configured."""
    retry = Retry(
        total=_RETRY_TOTAL,
        connect=_RETRY_TOTAL,
        read=0,  # read timeouts are not transient — don't retry
        backoff_factor=_RETRY_BACKOFF_FACTOR,
        status_forcelist=_RETRY_STATUS_FORCELIST,
        allowed_methods=_ALLOWED_RETRY_METHODS,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


_SESSION = _build_retry_session()

# ---------------------------------------------------------------------------
# Monkey-patch the top-level requests functions to delegate to the session.
# ---------------------------------------------------------------------------
_original_get = requests.get
_original_post = requests.post
_original_delete = requests.delete


def _reraise_timeout(exc: requests.ConnectionError) -> None:
    """Re-raise a retry timeout as :class:`requests.Timeout`.

    If *exc* wraps a read-timeout from the retry adapter, re-raise it so callers
    see the expected exception type.
    """
    inner = exc.args[0] if exc.args else None
    if not isinstance(inner, MaxRetryError):
        return

    reason = getattr(inner, "reason", None)
    if isinstance(reason, ReadTimeoutError):
        msg = "Read timed out."
        raise requests.Timeout(msg) from reason


def _patched_get(url: str, **kwargs: Any) -> requests.Response:
    """GET *url* through the retry-enabled session."""
    try:
        return _SESSION.get(url, **kwargs)
    except requests.ConnectionError as exc:
        _reraise_timeout(exc)
        raise


def _patched_post(url: str, **kwargs: Any) -> requests.Response:
    """POST to *url* through the retry-enabled session."""
    try:
        return _SESSION.post(url, **kwargs)
    except requests.ConnectionError as exc:
        _reraise_timeout(exc)
        raise


def _patched_delete(url: str, **kwargs: Any) -> requests.Response:
    """DELETE *url* through the retry-enabled session."""
    try:
        return _SESSION.delete(url, **kwargs)
    except requests.ConnectionError as exc:
        _reraise_timeout(exc)
        raise


requests.get = _patched_get         # type: ignore[method-assign, assignment]
requests.post = _patched_post       # type: ignore[method-assign, assignment]
requests.delete = _patched_delete   # type: ignore[method-assign, assignment]
