"""network.py - Retry-aware HTTP for external API calls.

Provides explicit :func:`get`, :func:`post`, and :func:`delete` helpers
that delegate to a shared :class:`requests.Session` configured with
exponential-backoff retry on transient failures (5xx, connection errors).

Import these helpers instead of ``requests.get`` / ``requests.post`` / ``requests.delete``
to benefit from retry logic with **zero monkey-patching**.
"""

from __future__ import annotations

import logging
import math
import os
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from collections.abc import Callable

import requests
from requests.adapters import HTTPAdapter
from urllib3.exceptions import ConnectTimeoutError, MaxRetryError, ReadTimeoutError
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

__all__ = [
    "delete",
    "get",
    "patch",
    "post",
    "put",
]

_RETRY_TOTAL: int
_RETRY_BACKOFF_FACTOR: float
_RETRY_STATUS_FORCELIST: list[int]


# Valid HTTP status code range for retry configuration
_HTTP_STATUS_MIN: int = 100
_HTTP_STATUS_MAX: int = 599


def _parse_retry_config() -> tuple[int, float, list[int]]:
    """Parse retry configuration from environment variables with validation.

    Returns
    -------
    tuple of (total, backoff_factor, status_forcelist)

    Raises
    ------
    ValueError
        If any parsed value is out of valid range.

    """
    # Parse total retries
    raw_total = os.environ.get("NETWORK_RETRY_TOTAL", "3")
    try:
        total = int(raw_total)
    except ValueError:
        logger.warning(
            "Invalid NETWORK_RETRY_TOTAL value %r, falling back to default 3",
            raw_total,
        )
        total = 3
    if total < 0:
        msg = f"NETWORK_RETRY_TOTAL must be non-negative, got: {total}"
        raise ValueError(msg)

    # Parse backoff factor
    raw_backoff = os.environ.get("NETWORK_RETRY_BACKOFF_FACTOR", "1.0")
    try:
        backoff = float(raw_backoff)
        if math.isnan(backoff) or math.isinf(backoff):
            logger.warning(
                "Invalid NETWORK_RETRY_BACKOFF_FACTOR value %r (NaN/Inf), "
                "falling back to default 1.0",
                raw_backoff,
            )
            backoff = 1.0
    except ValueError:
        logger.warning(
            "Invalid NETWORK_RETRY_BACKOFF_FACTOR value %r, falling back to default 1.0",
            raw_backoff,
        )
        backoff = 1.0
    if backoff < 0:
        msg = f"NETWORK_RETRY_BACKOFF_FACTOR must be non-negative, got: {backoff}"
        raise ValueError(msg)

    # Parse status forcelist
    raw = os.environ.get("NETWORK_RETRY_STATUS_FORCELIST", "429,500,502,503,504")
    statuses: list[int] = []
    for part in raw.split(","):
        stripped = part.strip()
        if not stripped:
            continue  # tolerate trailing commas / empty entries
        try:
            code = int(stripped)
        except ValueError:
            logger.warning(
                "Ignoring invalid entry %r in NETWORK_RETRY_STATUS_FORCELIST",
                stripped,
            )
            continue
        if not (_HTTP_STATUS_MIN <= code <= _HTTP_STATUS_MAX):
            msg = f"NETWORK_RETRY_STATUS_FORCELIST contains invalid HTTP status code: {code}"
            raise ValueError(
                msg,
            )
        statuses.append(code)

    return total, backoff, statuses


try:
    _RETRY_TOTAL, _RETRY_BACKOFF_FACTOR, _RETRY_STATUS_FORCELIST = _parse_retry_config()
except ValueError:
    logger.exception(
        "Invalid retry configuration in environment — falling back to defaults",
    )
    _RETRY_TOTAL = 3
    _RETRY_BACKOFF_FACTOR = 1.0
    _RETRY_STATUS_FORCELIST = [429, 500, 502, 503, 504]
_ALLOWED_RETRY_METHODS: frozenset[str] = frozenset(
    {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"},
)


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
# Public helpers — explicit functions instead of monkey-patching requests.
# ---------------------------------------------------------------------------


def _reraise_timeout(exc: requests.ConnectionError) -> None:
    """Re-raise a retry timeout as the appropriate exception type.

    Detects ``ReadTimeoutError`` and ``ConnectTimeoutError`` wrapped by the
    retry adapter's ``MaxRetryError``, and re-raises them as their natural
    exception type so callers see the expected signal:

    - ``ReadTimeoutError`` -> :class:`requests.Timeout`
    - ``ConnectTimeoutError`` -> :class:`requests.ConnectionError`
    """
    inner = exc.args[0] if exc.args else None
    if not isinstance(inner, MaxRetryError):
        return

    reason = getattr(inner, "reason", None)
    if isinstance(reason, ReadTimeoutError):
        msg = "Read timed out."
        raise requests.Timeout(msg) from reason
    if isinstance(reason, ConnectTimeoutError):
        msg = "Connection timed out."
        raise requests.ConnectionError(msg) from reason


def _request(method: str, url: str, **kwargs: Any) -> requests.Response:
    """Send a *method* request to *url* through the retry-enabled session."""
    try:
        http_fn = cast(
            "Callable[..., requests.Response]", getattr(_SESSION, method.lower()),
        )
        return http_fn(url, **kwargs)
    except requests.ConnectionError as exc:
        _reraise_timeout(exc)
        raise


def get(url: str, **kwargs: Any) -> requests.Response:
    """GET *url* through the retry-enabled session."""
    return _request("get", url, **kwargs)


def post(url: str, **kwargs: Any) -> requests.Response:
    """POST to *url* through the retry-enabled session."""
    return _request("post", url, **kwargs)


def put(url: str, **kwargs: Any) -> requests.Response:
    """PUT *url* through the retry-enabled session."""
    return _request("put", url, **kwargs)


def patch(url: str, **kwargs: Any) -> requests.Response:
    """PATCH *url* through the retry-enabled session."""
    return _request("patch", url, **kwargs)


def delete(url: str, **kwargs: Any) -> requests.Response:
    """DELETE *url* through the retry-enabled session."""
    return _request("delete", url, **kwargs)
