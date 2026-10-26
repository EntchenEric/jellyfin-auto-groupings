"""routes.py - Flask Blueprint containing all HTTP route handlers.

Every route is registered on the ``bp`` Blueprint which is imported and
registered with the Flask application in ``app.py``.  Route handlers are
intentionally thin: they validate inputs, delegate to service functions in
other modules, and serialise results back to JSON.
"""

from __future__ import annotations

import base64
import binascii
import copy
import hmac
import logging
import math
import os
import shutil
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path
from typing import TYPE_CHECKING, Any

import requests
from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    jsonify,
    render_template,
    request,
)
from werkzeug.exceptions import HTTPException

import network
from _common import DEFAULT_SEARCH_ROOTS as _DEFAULT_SEARCH_ROOTS
from _common import SOURCE_TYPES as _ALLOWED_PREVIEW_TYPES
from _common import is_valid_mmdd, normalize_group_relpath
from config import (
    _active_env_overrides,
    load_config,
    load_stored_config,
    save_config,
)
from jellyfin import (
    _PAGE_LIMIT,
    RECURSIVE_TRUE,
    SORT_MAP,
    _paginate_jellyfin,
    delete_virtual_folder,
    fetch_jellyfin_items,
    get_users,
)
from scheduler import _scheduler, update_scheduler_jobs, validate_cron
from sync import (
    _LIST_ORDER_VALUES as _VALID_LIST_ORDER_VALUES,
)
from sync import (
    clear_library_cache,
    get_cover_path,
    preview_group,
    run_sync,
)

# Resolve the application version from package metadata.
# Falls back to a dev placeholder when running from source
# (i.e. the package is not installed via pip).
try:
    __version__: str = _pkg_version("jellyfin-groupings")
except PackageNotFoundError:
    __version__ = "1.0.0+dev"
del _pkg_version

if TYPE_CHECKING:
    from flask.typing import ResponseReturnValue

_APP_START_TIME: float = time.time()

logger = logging.getLogger(__name__)

__all__ = ["bp"]

bp = Blueprint("main", __name__)


def _handle_http_error(exc: HTTPException) -> ResponseReturnValue:
    """Translate blueprint HTTP exceptions into JSON error responses.

    Args:
        exc: The exception that was raised.

    """
    if exc.code is None:
        raise exc
    return jsonify({"status": "error", "message": exc.description}), exc.code


bp.register_error_handler(HTTPException, _handle_http_error)


def _error(message: str, status_code: int = 400, **extra: Any) -> ResponseReturnValue:
    """Return a JSON error response.

    Args:
        message: The message for the response.
        status_code: HTTP status code for the response.

    """
    payload: dict[str, Any] = {"status": "error", "message": message}
    if extra:
        payload.update(extra)
    return jsonify(payload), status_code


def _success(message: str, status_code: int = 200, **extra: Any) -> ResponseReturnValue:
    """Return a JSON success response.

    Args:
        message: The message for the response.
        status_code: HTTP status code for the response.

    """
    payload: dict[str, Any] = {"status": "success", "message": message}
    if extra:
        payload.update(extra)
    return jsonify(payload), status_code


# Allowed image MIME types for cover upload
_ALLOWED_COVER_MIME_TYPES: frozenset[str] = frozenset(
    {"image/jpeg", "image/png", "image/webp", "image/gif"},
)

# Map MIME type to file extension (used by upload_cover)
_MIME_TO_EXT: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}

# Max size for base64 encoded cover image (approx 4MB)
MAX_B64_SIZE = 4 * 1024 * 1024

# Auto-detect filesystem search limits
_AUTO_DETECT_TIMEOUT = 30
_AUTO_DETECT_MAX_FILES = 50_000
_AUTO_DETECT_MAX_DEPTH = 6

# Test result filenames
_TEST_RESULT_FILENAMES = (
    "test_results.txt",
    "current_test_out.txt",
    "test_api_out.txt",
)

# Allowed preview metadata types, including external list sources
# (imported from _common as _ALLOWED_PREVIEW_TYPES)

# Default filesystem search roots for auto-detect
# (imported from _common as _DEFAULT_SEARCH_ROOTS)

# Sync rate limiting (per client IP)
_SYNC_RATE_LIMIT_SECONDS = 5
_last_sync_by_ip: dict[str, float] = {}

_SENSITIVE_CONFIG_KEYS: tuple[str, ...] = (
    "api_key",
    "trakt_client_id",
    "tmdb_api_key",
    "mal_client_id",
    "anilist_api_url",
)
_CONFIG_MASK = "****"

# Server connection-test timeout (seconds)
_TEST_SERVER_TIMEOUT: int = 5

# Auto-detect sample fetch limit
_AUTO_DETECT_SAMPLE_LIMIT: int = 10

# Auto-detect Jellyfin API timeout (seconds)
_AUTO_DETECT_JELLYFIN_TIMEOUT: int = 10

# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

_APP_PASSWORD: str = os.environ.get("APP_PASSWORD", "")


def _passwords_match(supplied: str, expected: str) -> bool:
    """Compare two passwords in constant time, tolerating non-ASCII text.

    :func:`hmac.compare_digest` raises ``TypeError`` when either argument is
    a ``str`` containing non-ASCII characters, so an operator who set a
    password like ``"pässwort"`` made every authenticated request fail with
    HTTP 500 instead of being rejected or accepted.  Both sides are encoded
    to UTF-8 first, which keeps the comparison constant-time over bytes and
    never raises.

    Args:
        supplied: The password sent by the client.
        expected: The configured ``APP_PASSWORD``.

    Returns:
        ``True`` if the passwords are byte-identical, ``False`` otherwise.

    """
    return hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8"))


@bp.before_request
def _check_auth() -> ResponseReturnValue | None:
    """Require HTTP Basic Auth when APP_PASSWORD is set.

    The password comparison uses :func:`_passwords_match`, which wraps
    :func:`hmac.compare_digest` so that a timing side-channel cannot be used
    to enumerate the password character by character (a plain ``==`` string
    comparison short-circuits on the first mismatching byte) while still
    accepting non-ASCII passwords.
    """
    if not _APP_PASSWORD:
        return None
    # Allow unauthenticated access to the main UI, static assets, and health check
    if request.endpoint == "main.index":
        return None
    if request.endpoint == "main.health_check":
        return None
    if request.path.startswith("/static/"):
        return None  # pragma: no cover (defensive — Flask serves static at app level)

    auth = request.authorization
    if (
        auth
        and auth.password is not None
        and _passwords_match(auth.password, _APP_PASSWORD)
    ):
        return None

    return Response(
        "Authentication required",
        401,
        {"WWW-Authenticate": 'Basic realm="Jellyfin Groupings"'},
    )


# Endpoints that are exempted from the CSRF X-Requested-With check.
# Add endpoint names here when you need to POST from non-browser clients
# that cannot set the ``X-Requested-With: XMLHttpRequest`` header.
#
# Set the ``ALLOWED_NON_CSRF_ENDPOINTS`` environment variable to a
# comma-separated list of endpoint names (e.g. ``"main.webhook,main.callback"``)
# to override the default (empty) set at process start.
_ALLOWED_NON_CSRF_REQUESTS: frozenset[str] = frozenset(
    e
    for _split in os.environ.get("ALLOWED_NON_CSRF_ENDPOINTS", "").split(",")
    if (e := _split.strip())
)

# HTTP methods that require CSRF protection
_CSRF_MUTATING_METHODS: tuple[str, ...] = ("POST", "PUT", "DELETE", "PATCH")


@bp.before_request
def _check_csrf() -> ResponseReturnValue | None:
    """Require ``X-Requested-With`` header on state-changing requests.

    POST, PUT, DELETE, and PATCH requests from the browser must include the
    ``X-Requested-With: XMLHttpRequest`` header (set automatically by
    JavaScript ``fetch``/``XMLHttpRequest``).

    To permit a specific endpoint to accept requests **without** this header
    (e.g. for external scripts), add its endpoint name to
    :data:`_ALLOWED_NON_CSRF_REQUESTS` or set the
    ``ALLOWED_NON_CSRF_ENDPOINTS`` environment variable to a
    comma-separated list of endpoint names.
    """
    if request.method in _CSRF_MUTATING_METHODS:
        if current_app.config.get("TESTING"):
            return None
        if request.endpoint and request.endpoint in _ALLOWED_NON_CSRF_REQUESTS:
            return None
        if request.headers.get("X-Requested-With") != "XMLHttpRequest":
            return _error("CSRF validation failed", 403)
    return None


# ---------------------------------------------------------------------------
# Security headers — applied to every response
# ---------------------------------------------------------------------------


@bp.after_request
def _add_security_headers(response: Response) -> Response:
    """Set security-related HTTP headers on every response.

    * ``X-Content-Type-Options: nosniff`` — prevents MIME-type sniffing.
    * ``X-Frame-Options: DENY`` — prevents clickjacking in frames.
    * ``Referrer-Policy: no-referrer`` — prevents leaking the current URL
      (which may contain query parameters) in the ``Referer`` header of
      outbound requests.
    * ``X-XSS-Protection: 1; mode=block`` — legacy XSS filter for older
      browsers that do not support a Content-Security-Policy.
    * ``Permissions-Policy`` — disables browser features this app does not
      use (camera, microphone, geolocation, etc.) to reduce the attack
      surface and prevent silent feature abuse.

    Args:
        response: The HTTP response object.

    """
    response.headers.set("X-Content-Type-Options", "nosniff")
    response.headers.set("X-Frame-Options", "DENY")
    response.headers.set("Referrer-Policy", "no-referrer")
    response.headers.set("X-XSS-Protection", "1; mode=block")
    response.headers.set(
        "Permissions-Policy",
        "camera=(), microphone=(), geolocation=(), "
        "payment=(), usb=(), magnetometer=(), gyroscope=(), "
        "accelerometer=(), midi=(), sync-xhr=(), "
        "fullscreen=(self)",
    )
    return response


# Security helpers for the filesystem browser
# ---------------------------------------------------------------------------


# Roots that the folder browser is allowed to expose.
_BROWSE_ROOTS: tuple[str, ...] = tuple(
    os.path.realpath(r) for r in _DEFAULT_SEARCH_ROOTS
)


def _path_is_allowed(path: str) -> bool:
    """Return ``True`` only if *path* is at or below one of the whitelisted roots.

    Args:
        path: Absolute filesystem path to check.

    Returns:
        ``True`` if access should be permitted, ``False`` otherwise.

    """
    real = os.path.realpath(path)
    return any(real == root or real.startswith(root + os.sep) for root in _BROWSE_ROOTS)


def _short(value: object, limit: int = 80) -> str:
    """Return a bounded, quotable rendering of *value* for logs and errors.

    A rejected folder name or path can be thousands of characters long (a
    client is free to POST one). Interpolating it verbatim buries the rest of
    the message and floods the log, so the middle is elided once the value is
    longer than *limit*.

    Args:
        value: The value to render.
        limit: Maximum number of characters to keep before eliding.

    Returns:
        The rendered value, truncated with an explicit remainder marker.

    """
    text = str(value)
    if len(text) <= limit:
        return text
    return f"{text[:limit]}… ({len(text) - limit} more chars)"


def _os_error_reason(exc: BaseException) -> str:
    """Return a bounded reason for *exc* without repeating the offending path.

    ``OSError.__str__`` appends the failing path, and ``filename2`` for a
    rename-style error. A rejected long path therefore produced a message
    thousands of characters long, both in the log and in the HTTP response.
    ``strerror`` carries the reason alone.

    Args:
        exc: The exception to describe.

    Returns:
        The OS reason, falling back to the exception type name.

    """
    strerror = getattr(exc, "strerror", None)
    return str(strerror) if strerror else type(exc).__name__


def _safe_exists(path: str | os.PathLike[str]) -> bool:
    """Return whether *path* exists, treating an unstattable path as absent.

    ``Path.exists()`` runs ``stat`` and only swallows ``ENOENT``-class errors;
    it *raises* for a name the kernel rejects outright. A path component
    longer than ``NAME_MAX`` therefore raises ``OSError(ENAMETOOLONG)`` from
    every ``exists()`` / ``is_dir()`` call, and a config or request carrying
    such a path used to abort the handler with an unhandled 500 instead of a
    normal "not found" answer.

    Args:
        path: The filesystem path to test.

    Returns:
        ``True`` only when the path can be inspected and exists.

    """
    try:
        return Path(path).exists()
    except (OSError, ValueError) as exc:
        logger.warning("Cannot stat %s: %s", _short(path), _os_error_reason(exc))
        return False


def _safe_is_dir(path: str | os.PathLike[str]) -> bool:
    """Return whether *path* is a directory, treating an unstattable one as not.

    Companion to :func:`_safe_exists` for callers that only need the directory
    check; see there for why the underlying ``stat`` can raise.

    Args:
        path: The filesystem path to test.

    Returns:
        ``True`` only when the path can be inspected and is a directory.

    """
    try:
        return Path(path).is_dir()
    except (OSError, ValueError) as exc:
        logger.warning("Cannot stat %s: %s", _short(path), _os_error_reason(exc))
        return False


def _get_jellyfin_config(
    missing_msg: str = "Server settings not configured",
) -> tuple[str, str]:
    """Load and validate Jellyfin URL + API key from the active config.

    Args:
        missing_msg: Message to include if config is missing.

    Returns:
        ``(url, api_key)`` on success.

    Raises:
        werkzeug.exceptions.HTTPException: 400 or 500 if the config
        is missing or invalid.

    """
    config = load_config()
    if not isinstance(config, dict):
        abort(500, description="Invalid configuration format")
    url = str(config.get("jellyfin_url") or "").rstrip("/")
    api_key = str(config.get("api_key") or "")
    if not url or not api_key:
        abort(400, description=missing_msg)
    return url, api_key


def _mask_config(config: dict[str, Any]) -> dict[str, Any]:
    """Mask sensitive config values for safe serialisation.

    Replaces values for keys in :data:`_SENSITIVE_CONFIG_KEYS` with
    :data:`_CONFIG_MASK` (``"****"``) so they are never exposed to the
    frontend.

    Args:
        config: The configuration dict.

    """
    masked = copy.deepcopy(config)
    for key in _SENSITIVE_CONFIG_KEYS:
        if masked.get(key):
            masked[key] = _CONFIG_MASK
    return masked


def _restore_masked_secrets(new_config: dict[str, Any]) -> dict[str, Any]:
    """Replace echoed masks with the stored secret and drop internal keys.

    ``GET /api/config`` masks secrets, and the frontend posts the whole
    config object back when saving. Any sensitive field that still equals
    :data:`_CONFIG_MASK` therefore means "unchanged" and is restored from
    disk; without this the real key would be persisted as ``"****"``.
    Non-persistent helper keys such as ``_active_env_overrides`` are removed.

    Args:
        new_config: The config dict parsed from the request body.

    Returns:
        A copy safe to persist.

    """
    cleaned = {k: v for k, v in new_config.items() if not k.startswith("_")}
    if not any(cleaned.get(key) == _CONFIG_MASK for key in _SENSITIVE_CONFIG_KEYS):
        return cleaned
    stored = load_stored_config()
    for key in _SENSITIVE_CONFIG_KEYS:
        if cleaned.get(key) == _CONFIG_MASK:
            cleaned[key] = stored.get(key, "")
    return cleaned


@bp.route("/api/config", methods=["GET"])
def get_config() -> ResponseReturnValue:
    """Return the current application configuration as JSON.

    The response includes a top-level ``_active_env_overrides`` key listing
    any config keys that are currently overridden by environment variables
    (see :mod:`config`). Sensitive values are masked.

    Returns:
        JSON-serialised configuration dictionary with an extra
        ``_active_env_overrides`` key.

    """
    config = load_config()
    config["_active_env_overrides"] = _active_env_overrides()
    return jsonify(_mask_config(config))


def _check_sync_rate_limit() -> ResponseReturnValue | None:
    """Enforce a per-IP rate limit on sync operations.

    Returns a 429 error response if the client has called sync within
    :data:`_SYNC_RATE_LIMIT_SECONDS`, otherwise records the current
    timestamp and returns ``None``.

    Stale entries (older than twice the rate-limit window) are pruned
    on each call to prevent unbounded growth.
    """
    ip = request.remote_addr or "unknown"
    now = time.monotonic()
    last = _last_sync_by_ip.get(ip, 0.0)
    if now - last < _SYNC_RATE_LIMIT_SECONDS:
        return _error("Please wait before syncing again", 429)
    _last_sync_by_ip[ip] = now
    # Prune entries older than twice the rate-limit window to prevent
    # unbounded growth from rotating/changing client IPs.
    cutoff = now - (2 * _SYNC_RATE_LIMIT_SECONDS)
    stale = [k for k, v in _last_sync_by_ip.items() if v < cutoff]
    for k in stale:
        del _last_sync_by_ip[k]
    return None


def _validate_cron_expressions(new_config: dict[str, Any]) -> list[str]:
    """Validate all cron expressions in *new_config*, returning a list of errors.

    Args:
        new_config: The new configuration dict to validate.

    """
    cron_errors: list[str] = []
    # ``new_config`` is untrusted client JSON, so every container can be
    # missing or of the wrong type. Walk it defensively: a malformed payload
    # must produce a 400 with validation errors, not an AttributeError/500.
    sched_cfg = new_config.get("scheduler")
    if not isinstance(sched_cfg, dict):
        # Wrong-typed sections are reported by _validate_config_types(); there
        # is nothing further to validate here.
        sched_cfg = {}
    if sched_cfg.get("global_enabled"):
        global_sched = sched_cfg.get("global_schedule", "")
        err = validate_cron(global_sched)
        if err:
            cron_errors.append(f"Global schedule: {err}")
    cleanup_sched = sched_cfg.get("cleanup_schedule", "")
    if cleanup_sched and sched_cfg.get("cleanup_enabled", True):
        err = validate_cron(cleanup_sched)
        if err:
            cron_errors.append(f"Cleanup schedule: {err}")
    groups = new_config.get("groups")
    if not isinstance(groups, list):
        groups = []
    for group in groups:
        if not isinstance(group, dict):
            # Reported by _validate_group_types().
            continue
        if group.get("schedule_enabled") and group.get("schedule"):
            err = validate_cron(group["schedule"])
            if err:
                cron_errors.append(f"Group '{group.get('name', 'unnamed')}': {err}")
    return cron_errors


def _optional_lower_str(data: dict[str, Any], key: str) -> str | None:
    """Read an optional string field from a JSON body, trimmed and lower-cased.

    ``/api/grouping/preview`` is called from JavaScript with values taken out
    of ``<select>`` elements, but the body is client-controlled: a caller can
    send a number, a list or an object for any field.  Those types used to
    reach ``.strip()`` and raise ``AttributeError``, which surfaced as an HTTP
    500 instead of a validation error.

    Args:
        data: The decoded JSON request body.
        key: The field name to read.

    Returns:
        The trimmed, lower-cased value; ``""`` when the field is absent or
        JSON ``null``; ``None`` when it holds any other non-string type, so
        the caller can answer 400 instead of silently ignoring a filter the
        user asked for.

    """
    value = data.get(key)
    if value is None:
        return ""
    if not isinstance(value, str):
        return None
    return value.strip().lower()


def _check_type(val: Any, expected_type: type, path: str, errors: list[str]) -> None:
    """Append an error to *errors* if *val* is not None and not of *expected_type*.

    Args:
        val: The value to check.
        expected_type: The expected type (e.g. ``str``, ``list``).
        path: The ``path`` parameter.
        errors: List to append error messages to.

    """
    if val is not None and not isinstance(val, expected_type):
        type_name = expected_type.__name__
        errors.append(f"'{path}' must be a {type_name}")


def _validate_scheduler_types(sched: dict[str, Any], errors: list[str]) -> None:
    """Validate type correctness of scheduler sub-object fields.

    Args:
        sched: The scheduler configuration dict section.
        errors: List to append error messages to.

    """
    if not isinstance(sched, dict):
        errors.append("'scheduler' must be an object")
        return
    for bool_field in ("global_enabled", "cleanup_enabled"):
        _check_type(sched.get(bool_field), bool, f"scheduler.{bool_field}", errors)
    for str_field in ("global_schedule", "cleanup_schedule"):
        _check_type(sched.get(str_field), str, f"scheduler.{str_field}", errors)
    _check_type(
        sched.get("global_exclude_ids"),
        list,
        "scheduler.global_exclude_ids",
        errors,
    )


def _validate_group_rules(
    rules: list[dict[str, Any]],
    prefix: str,
    errors: list[str],
) -> None:
    """Validate type correctness of a group's complex query rules.

    Args:
        rules: List of rule strings to validate.
        prefix: Dot-separated path prefix for error messages.
        errors: List to append error messages to.

    """
    for j, rule in enumerate(rules):
        if not isinstance(rule, dict):
            errors.append(f"{prefix}.rules[{j}] must be an object")
            continue
        rprefix = f"{prefix}.rules[{j}]"
        _check_type(rule.get("type"), str, f"{rprefix}.type", errors)
        _check_type(rule.get("value"), str, f"{rprefix}.value", errors)
        _check_type(rule.get("operator"), str, f"{rprefix}.operator", errors)
        _check_type(rule.get("not"), bool, f"{rprefix}.not", errors)


def _validate_group_types(
    group: dict[str, Any],
    prefix: str,
    errors: list[str],
) -> None:
    """Validate type correctness of a single group definition.

    Args:
        group: The group configuration dict.
        prefix: Dot-separated path prefix for error messages.
        errors: List to append error messages to.

    """
    if not isinstance(group, dict):
        errors.append(f"{prefix} must be an object")
        return
    _check_type(group.get("name"), str, f"{prefix}.name", errors)
    _check_type(group.get("source_type"), str, f"{prefix}.source_type", errors)
    _check_type(group.get("source_value"), str, f"{prefix}.source_value", errors)
    _check_type(group.get("sort_order"), str, f"{prefix}.sort_order", errors)
    _check_type(group.get("watch_state"), str, f"{prefix}.watch_state", errors)
    _check_type(group.get("item_type"), str, f"{prefix}.item_type", errors)
    _check_type(group.get("schedule"), str, f"{prefix}.schedule", errors)
    for bool_field in ("schedule_enabled", "seasonal_enabled", "create_as_collection"):
        _check_type(group.get(bool_field), bool, f"{prefix}.{bool_field}", errors)

    # Validate source_type is a recognised value so an invalid type fails fast
    # at config-save time instead of surfacing later as "Unknown source type"
    # during a sync.
    source_type = group.get("source_type")
    if (
        isinstance(source_type, str)
        and source_type
        and source_type not in _ALLOWED_PREVIEW_TYPES
    ):
        errors.append(
            f"{prefix}.source_type must be one of: "
            f"{', '.join(sorted(_ALLOWED_PREVIEW_TYPES))}",
        )

    # Validate sort_order is a recognised value (Jellyfin sort key or an
    # external-list order) so a typo is caught immediately rather than being
    # silently ignored during sorting.
    sort_order = group.get("sort_order")
    if (
        isinstance(sort_order, str)
        and sort_order
        and sort_order not in SORT_MAP
        and sort_order not in _VALID_LIST_ORDER_VALUES
    ):
        valid_sorts = sorted(set(SORT_MAP) | set(_VALID_LIST_ORDER_VALUES))
        errors.append(
            f"{prefix}.sort_order must be one of: {', '.join(valid_sorts)}",
        )

    # Validate seasonal date format (MM-DD) when provided
    for date_field in ("seasonal_start", "seasonal_end"):
        val = group.get(date_field)
        if val is not None and not isinstance(val, str):
            errors.append(f"{prefix}.{date_field} must be a string")
        elif isinstance(val, str) and val and not is_valid_mmdd(val):
            errors.append(
                f"{prefix}.{date_field} must be an existing MM-DD date"
                f" (e.g. 10-31, 02-29), got {val!r}",
            )

    # Validate rules field (complex query rules)
    rules = group.get("rules")
    if rules is not None and not isinstance(rules, list):
        errors.append(f"{prefix}.rules must be a list")
    elif isinstance(rules, list):
        _validate_group_rules(rules, prefix, errors)


#: Maximum number of groupings accepted in one configuration.
#: Documented in ``docs/API.md`` ("groups must be a list (max 200)"); the
#: limit exists so one save cannot queue an unbounded amount of sync work.
_MAX_GROUPS: int = 200


def _validate_group_names(groups: list[Any]) -> list[str]:
    """Validate the name of every group in *groups*.

    ``docs/API.md`` promises that ``POST /api/config`` enforces "unique
    non-empty names", but only the *type* of ``name`` was checked. Two groups
    sharing a name are indistinguishable downstream: they write into the same
    target directory, the second silently overwrites the first, and the
    per-group scheduler registers the job under ``group_sync_<name>`` so one
    of them never runs. An empty or whitespace-only name has no directory to
    write to at all, and the group fails at sync time instead of at save time.

    Names are compared after stripping surrounding whitespace, mirroring the
    normalisation used when creating the folder, so ``"Action "`` and
    ``"Action"`` count as duplicates.

    Args:
        groups: The ``groups`` list from the request body. Entries are not
            assumed to be dicts; non-dicts are ignored here because
            :func:`_validate_group_types` already reports them.

    Returns:
        A list of error messages; empty when every name is usable.

    """
    errors: list[str] = []
    seen: dict[str, int] = {}

    for i, group in enumerate(groups):
        if not isinstance(group, dict):
            continue
        name = group.get("name")
        if not isinstance(name, str):
            # Type errors and the missing-name case are reported elsewhere;
            # a ``null`` name is treated as absent, not as a duplicate.
            continue
        stripped = name.strip()
        if not stripped:
            errors.append(f"groups[{i}].name must not be empty")
            continue
        if stripped in seen:
            errors.append(
                f"groups[{i}].name duplicates groups[{seen[stripped]}].name "
                f"({stripped!r})",
            )
            continue
        seen[stripped] = i

    return errors


def _validate_config_types(new_config: dict[str, Any]) -> list[str]:
    """Validate basic types in *new_config*, returning a list of errors.

    Args:
        new_config: The new configuration dict to validate.

    """
    errors: list[str] = []

    # Top-level string fields
    for str_field in (
        "jellyfin_url",
        "api_key",
        "target_path",
        "media_path_in_jellyfin",
        "media_path_on_host",
        "target_path_in_jellyfin",
        "anilist_api_url",
        "trakt_client_id",
        "tmdb_api_key",
        "mal_client_id",
    ):
        _check_type(new_config.get(str_field), str, str_field, errors)

    # Top-level list fields
    _check_type(new_config.get("groups"), list, "groups", errors)

    # Top-level boolean fields
    for bool_field in (
        "auto_create_libraries",
        "auto_set_library_covers",
        "setup_done",
    ):
        _check_type(new_config.get(bool_field), bool, bool_field, errors)

    # Scheduler sub-object
    sched = new_config.get("scheduler")
    if sched is not None:
        _validate_scheduler_types(sched, errors)

    # Groups
    groups = new_config.get("groups")
    if isinstance(groups, list):
        if len(groups) > _MAX_GROUPS:
            errors.append(
                f"'groups' may contain at most {_MAX_GROUPS} entries, "
                f"got {len(groups)}",
            )
        for i, group in enumerate(groups):
            _validate_group_types(group, f"groups[{i}]", errors)
        errors.extend(_validate_group_names(groups))

    # Validate jellyfin_url format when provided
    jellyfin_url = new_config.get("jellyfin_url")
    if isinstance(jellyfin_url, str) and jellyfin_url:
        if not jellyfin_url.startswith(("http://", "https://")):
            errors.append("'jellyfin_url' must start with http:// or https://")
        else:
            # Validate well-formed URL with urllib
            try:
                parsed = urllib.parse.urlparse(jellyfin_url)
                if not parsed.netloc:
                    errors.append(
                        "'jellyfin_url' is not a well-formed URL (missing hostname)",
                    )
            except (ValueError, AttributeError, TypeError):
                errors.append("'jellyfin_url' contains unparseable characters")

    # Validate target_path exists and is writable when provided
    target_path_val = new_config.get("target_path")
    if isinstance(target_path_val, str) and target_path_val:
        try:
            tp = Path(target_path_val)
            if not tp.exists():
                errors.append(
                    f"'target_path' path does not exist: {_short(target_path_val)}",
                )
            elif not tp.is_dir():
                errors.append(
                    f"'target_path' is not a directory: {_short(target_path_val)}",
                )
            elif not os.access(str(tp), os.W_OK | os.X_OK):
                errors.append(
                    f"'target_path' is not writable: {_short(target_path_val)}",
                )
        except (OSError, ValueError) as exc:
            errors.append(
                f"'target_path' validation error: {_os_error_reason(exc)}",
            )

    # Validate media_path_on_host is readable when provided
    media_path_val = new_config.get("media_path_on_host")
    if isinstance(media_path_val, str) and media_path_val:
        try:
            mp = Path(media_path_val)
            if not mp.exists():
                errors.append(
                    "'media_path_on_host' path does not exist: "
                    f"{_short(media_path_val)}",
                )
            elif not mp.is_dir():
                errors.append(
                    f"'media_path_on_host' is not a directory: "
                    f"{_short(media_path_val)}",
                )
            elif not os.access(str(mp), os.R_OK | os.X_OK):
                errors.append(
                    f"'media_path_on_host' is not readable: {_short(media_path_val)}",
                )
        except (OSError, ValueError) as exc:
            errors.append(
                f"'media_path_on_host' validation error: {_os_error_reason(exc)}",
            )

    return errors


@bp.route("/api/config", methods=["POST"])
def update_config() -> ResponseReturnValue:
    """Persist a new application configuration supplied in the request body.

    The entire configuration object is replaced with the POSTed JSON.

    Returns:
        JSON with ``status`` and the saved ``config``, or a 500 error if the
        config file could not be written.

    """
    new_config = request.get_json(silent=True)
    if not isinstance(new_config, dict):
        return _error("Request body must be a JSON object", 400)

    cron_errors = _validate_cron_expressions(new_config)
    if cron_errors:
        return _error("Invalid cron expression(s)", 400, errors=cron_errors)

    type_errors = _validate_config_types(new_config)
    if type_errors:
        return _error("Invalid config field type(s)", 400, errors=type_errors)

    # The frontend loads the masked config and posts the whole object back on
    # save, so any secret field still holding the mask must be replaced with
    # its stored value; otherwise the real API key would be overwritten with
    # "****". Internal, non-persistent keys are dropped at the same time.
    new_config = _restore_masked_secrets(new_config)

    try:
        save_config(new_config)
    except OSError as exc:
        logger.exception("Failed to write config file")
        return _error(f"Config file write failed: {exc}", 500)

    # Clear any cached Jellyfin data — the server URL or API key may have changed
    clear_library_cache()

    try:
        update_scheduler_jobs()
    except (ValueError, KeyError, OSError, RuntimeError) as exc:
        logger.exception("Failed to update scheduler jobs")
        return _error(
            f"Config saved but scheduler could not be updated: {exc!s}",
            500,
            config=new_config,
        )

    return _success("", config=new_config)


# ---------------------------------------------------------------------------
# Connection test
# ---------------------------------------------------------------------------


@bp.route("/api/test-server", methods=["POST"])
def test_server() -> ResponseReturnValue:
    """Verify connectivity to a Jellyfin server.

    Expects a JSON body with ``jellyfin_url`` and ``api_key`` fields.

    Returns:
        JSON with ``status`` and a human-readable ``message``.

    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _error("Request body must be a JSON object", 400)
    url: str = str(data.get("jellyfin_url") or "").rstrip("/")
    api_key: str = str(data.get("api_key") or "")

    # The sidebar tests the connection using the value shown in the form,
    # which is the mask when the config was loaded from the server. Resolve
    # it to the stored key instead of failing the test with "****".
    if api_key == _CONFIG_MASK:
        api_key = str(load_stored_config().get("api_key") or "")

    if not url or not api_key:
        return _error("URL and API Key are required", 400)

    try:
        response = network.get(
            f"{url}/System/Info",
            headers={"X-Emby-Token": api_key},
            timeout=_TEST_SERVER_TIMEOUT,
        )
        if response.status_code == 200:
            return _success("Connected to Jellyfin successfully!")
        return _error(f"Server returned status {response.status_code}", 400)
    except (ValueError, TypeError):
        return _error("Invalid server URL or API key format", 400)
    except requests.exceptions.RequestException as exc:
        return _error(f"Connection error: {exc!s}", 400)


# ---------------------------------------------------------------------------
# Jellyfin metadata
# ---------------------------------------------------------------------------


def _fetch_jellyfin_endpoint(
    base_url: str,
    api_key: str,
    endpoint: str,
    *,
    timeout: int = 15,
    extra_params: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Fetch all items from a Jellyfin list endpoint (Genres, Studios, etc.).

    Handles paginated responses, collecting all items across all pages.
    If a request fails part-way through, already-fetched items are returned
    rather than raising (partial data is better than nothing for metadata).

    Args:
        base_url: Jellyfin server base URL.
        api_key: Jellyfin API key.
        endpoint: Name of the dedicated endpoint (e.g. ``Genres``, ``Studios``).
        timeout: HTTP request timeout per page.
        extra_params: Additional query-string parameters per request.

    Returns:
        A list of all item dictionaries from the endpoint.

    """
    items: list[dict[str, Any]] = []
    try:
        for page in _paginate_jellyfin(
            base_url,
            api_key,
            endpoint,
            extra_params,
            limit=_PAGE_LIMIT,
            timeout=timeout,
        ):
            items.extend(page)
    except RuntimeError:
        if items:
            logger.debug(
                "Partial fetch for %s — returning %s items after error",
                endpoint,
                len(items),
            )
            return items
        logger.exception("Failed to fetch any items from %s", endpoint)
        raise
    except requests.RequestException:
        if items:
            logger.debug(
                "Partial fetch for %s — returning %s items after request error",
                endpoint,
                len(items),
            )
            return items
        raise
    return items


@bp.route("/api/jellyfin/metadata", methods=["GET"])
def get_jellyfin_metadata() -> ResponseReturnValue:
    """Return aggregated metadata (genres, studios, tags, actors) from Jellyfin.

    Uses Jellyfin's dedicated ``/Genres``, ``/Studios``, ``/Persons``, and
    ``/Tags`` endpoints fetched in parallel, which is orders of magnitude
    faster than scanning all items recursively.

    Returns:
        JSON with ``status`` and a ``metadata`` object containing ``genre``,
        ``studio``, ``tag``, and ``actor`` lists.

    """
    url, api_key = _get_jellyfin_config()

    result: dict[str, list[str]] = {}
    failed = 0

    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures: dict[str, Any] = {
                "genre": pool.submit(_fetch_jellyfin_endpoint, url, api_key, "Genres"),
                "studio": pool.submit(
                    _fetch_jellyfin_endpoint,
                    url,
                    api_key,
                    "Studios",
                ),
                "actor": pool.submit(
                    _fetch_jellyfin_endpoint,
                    url,
                    api_key,
                    "Persons",
                    extra_params={"PersonTypes": "Actor"},
                ),
                "tag": pool.submit(_fetch_jellyfin_endpoint, url, api_key, "Tags"),
            }
            for key, future in futures.items():
                try:
                    items = future.result()
                    result[key] = [
                        item.get("Name", "") for item in items if item.get("Name")
                    ]
                except (RuntimeError, ValueError):
                    logger.warning(
                        "Failed to process metadata key %r",
                        key,
                        exc_info=True,
                    )
                    result[key] = []
                    failed += 1

        if failed >= len(futures):
            return _error("Failed to fetch metadata from Jellyfin", 400)

        return _success("", metadata=result)
    except (RuntimeError, OSError) as exc:
        logger.exception("Unexpected error fetching Jellyfin metadata")
        return _error(str(exc), 500)


# ---------------------------------------------------------------------------
# Jellyfin users
# ---------------------------------------------------------------------------


@bp.route("/api/jellyfin/users", methods=["GET"])
def get_jellyfin_users() -> ResponseReturnValue:
    """Return a list of users from Jellyfin.

    Returns:
        JSON with ``status`` and a ``users`` object containing ``id`` and ``name``.

    """
    url, api_key = _get_jellyfin_config()

    try:
        users_list = get_users(url, api_key)
        return _success(
            "",
            users=[{"id": u.get("Id"), "name": u.get("Name")} for u in users_list],
        )
    except RuntimeError as exc:
        return _error(str(exc), 400)


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------


@bp.route("/api/upload_cover", methods=["POST"])
def upload_cover() -> ResponseReturnValue:
    """Save a base64-encoded cover image for a group.

    Expects a JSON body with ``group_name`` and ``image`` (data URL).
    Decodes and saves the image to a location determined by
    :func:`sync.get_cover_path`: it saves to
    ``target_base/.covers/[md5(group_name)].jpg`` when the target directory
    exists, otherwise it falls back to ``config/covers/[md5(group_name)].jpg``.
    The file name used is md5(group_name) + .jpg. Reference
    :func:`sync.get_cover_path` for the detailed storage precedence.

    Returns:
        JSON with ``status`` and ``message``.

    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _error("Request body must be JSON", 400)

    group_name = data.get("group_name")
    image_data = data.get("image")
    if not isinstance(group_name, str) or not isinstance(image_data, str):
        return _error("group_name and image must be strings", 400)

    if not image_data.startswith("data:image/"):
        return _error("Invalid image format — must be a data URL", 400)

    # Validate MIME type against allowed list
    mime_type = image_data[5:].split(",", 1)[0].split(";", 1)[0].strip()
    if mime_type not in _ALLOWED_COVER_MIME_TYPES:
        return _error(
            f"Unsupported image type '{mime_type}'. "
            f"Allowed: {', '.join(sorted(_ALLOWED_COVER_MIME_TYPES))}",
            400,
        )

    ext = _MIME_TO_EXT.get(mime_type, "jpg")

    try:
        _header, encoded = image_data.split(",", 1)

        if len(encoded) > MAX_B64_SIZE:
            return _error("Payload too large", 413)

        decoded = base64.b64decode(encoded)

        # Determine cover storage path using the shared helper
        cfg = load_config()
        target_path = str(cfg.get("target_path", ""))

        cover_path = get_cover_path(
            group_name,
            target_path,
            check_exists=False,
            ext=ext,
        )
        if cover_path is None:
            return _error("Could not resolve cover storage path", 500)

        Path(cover_path).parent.mkdir(parents=True, exist_ok=True)
        with Path(cover_path).open("wb") as f:
            f.write(decoded)

        return _success("Cover saved successfully")
    except (ValueError, binascii.Error):
        return _error("Malformed image data", 400)
    except (OSError, RuntimeError) as exc:
        logger.exception("Failed to save cover image")
        return _error(f"Server error: {exc!s}", 500)


def _run_sync_handler(dry_run: bool = False) -> ResponseReturnValue:
    """Run sync (or preview) and return a JSON response.

    Args:
        dry_run: If True, perform a dry run without side effects.

    """
    rate_limited = _check_sync_rate_limit()
    if rate_limited is not None:
        return rate_limited
    try:
        config: dict[str, Any] = load_config()
        sync_results = run_sync(config, dry_run=dry_run)
        if dry_run:
            return _success(
                "Preview generated successfully",
                results=sync_results,
            )
        return _success(
            "Synchronization complete",
            results=sync_results,
        )
    except ValueError as exc:
        return _error(f"{exc!s}", 400)
    except (RuntimeError, OSError) as exc:
        prefix = "Sync preview failed" if dry_run else "Sync failed"
        return _error(f"{prefix}: {exc!s}", 500)


@bp.route("/api/sync", methods=["POST"])
def sync_groupings() -> ResponseReturnValue:
    """Trigger a full synchronisation of all configured groupings.

    Reads the current configuration, delegates to :func:`sync.run_sync`, and
    returns per-group results.
    """
    return _run_sync_handler(dry_run=False)


@bp.route("/api/sync/preview_all", methods=["POST"])
def preview_all_sync() -> ResponseReturnValue:
    """Preview a full synchronisation of all configured groupings\
 without creating symlinks.

    Reads the current configuration, delegates to
    :func:`sync.run_sync` with dry_run=True,
    and returns per-group preview results.
    """
    return _run_sync_handler(dry_run=True)


@bp.route("/api/grouping/preview", methods=["POST"])
def preview_grouping() -> ResponseReturnValue:
    """Preview what items a grouping rule would include.

    Accepts a JSON body with 'type' and 'value'. If the 'value' contains
    logical operators (AND, OR, etc.), it is parsed as a complex query.
    Otherwise, it is treated as a simple metadata filter.

    Returns:
        JSON with 'status', 'count' of matched items, and 'preview_items'
        (a list of the first 15 matched titles).

    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _error("Request body must be JSON", 400)

    url, api_key = _get_jellyfin_config()

    # Validate and normalize "type"
    type_raw = data.get("type")
    if not isinstance(type_raw, str):
        return _error("Missing or invalid 'type'", 400)

    type_name = type_raw.lower().strip()
    if not type_name or type_name not in _ALLOWED_PREVIEW_TYPES:
        return _error(f"Invalid metadata type: {type_raw}", 400)

    # Validate value
    val_raw = data.get("value")
    if not isinstance(val_raw, str):
        return _error("Value must be a string", 400)

    val = val_raw.strip()
    if not val:
        return _error("Value cannot be empty", 400)

    watch_state = _optional_lower_str(data, "watch_state")
    if watch_state is None:
        return _error("'watch_state' must be a string", 400)
    item_type = _optional_lower_str(data, "item_type")
    if item_type is None:
        return _error("'item_type' must be a string", 400)

    # Load config for external list API keys
    config = load_config()
    trakt_client_id = str(config.get("trakt_client_id") or "").strip()
    tmdb_api_key = str(config.get("tmdb_api_key") or "").strip()
    mal_client_id = str(config.get("mal_client_id") or "").strip()
    # A hand-edited config.json can hold a non-string here; treat it as unset
    # rather than letting .strip() turn the whole preview into a 500.
    raw_url = config.get("anilist_api_url")
    if raw_url is not None and not isinstance(raw_url, str):
        logger.warning(
            "Ignoring malformed 'anilist_api_url' config (expected string, got %s)",
            type(raw_url).__name__,
        )
        raw_url = None
    anilist_api_url = raw_url.strip() if raw_url else None

    try:
        # Resolve items using the public sync API
        items, error, status_code = preview_group(
            type_name,
            val,
            url,
            api_key,
            watch_state,
            trakt_client_id=trakt_client_id,
            tmdb_api_key=tmdb_api_key,
            mal_client_id=mal_client_id,
            anilist_api_url=anilist_api_url,
            item_type=item_type,
        )

        if error is not None:
            return _error(error, status_code)

        # Return summary count and first few items
        results = [
            {"Name": i.get("Name", "Unknown"), "Year": i.get("ProductionYear", "")}
            for i in items[:15]
        ]

        return _success("", count=len(items), preview_items=results)
    except (ValueError, RuntimeError) as exc:
        logger.exception("Failed to generate grouping preview")
        return _error(f"Preview failed: {exc!s}", 500)


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------


@bp.route("/api/cleanup", methods=["GET"])
def get_cleanup_items() -> ResponseReturnValue:
    """Return a list of logical folders in the target directory."""
    config: dict[str, Any] = load_config()
    target_base: str = str(config.get("target_path") or "")
    if not target_base or not _safe_exists(target_base):
        return _success("", items=[])

    configured_groups: set[str] = set()
    # Parents of nested groups ("Anime" for "Anime/Action") are structural, not
    # leftovers — listing them as deletable would offer to wipe every child.
    parent_dirs: set[str] = set()
    for g in config.get("groups", []):
        rel = normalize_group_relpath(str(g.get("name") or ""))
        if not rel:
            continue
        configured_groups.add(rel)
        parts = rel.split("/")
        for depth in range(1, len(parts)):
            parent_dirs.add("/".join(parts[:depth]))

    max_depth = max((len(g.split("/")) for g in configured_groups), default=1)

    def _walk(directory: Path, prefix: str, depth: int) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        # A directory this process may not read (a root-owned library folder, a
        # mount that dropped away mid-walk) raised out of ``iterdir()`` and the
        # caller's single ``except OSError`` turned the *whole* listing into a
        # 500 — the user lost every other deletable folder because of one
        # unreadable one. Skip just that subtree and keep listing.
        try:
            children = list(directory.iterdir())
        except OSError as exc:
            logger.warning("cleanup: cannot read %s: %s", directory, exc)
            return found
        for entry in children:
            # is_dir() follows symlinks, so exclude links explicitly — a
            # symlink pointing outside the target must never be offered as a
            # deletable cleanup item (mirrors the browse endpoint).
            try:
                if (
                    entry.is_symlink()
                    or not entry.is_dir()
                    or entry.name.startswith(".")
                ):
                    continue
            except OSError as exc:
                # ``stat`` failed (dangling link, symlink loop, permission):
                # the entry cannot be classified, so it is not safe to offer it
                # for deletion.
                logger.warning("cleanup: cannot stat %s: %s", entry, exc)
                continue
            rel = f"{prefix}/{entry.name}" if prefix else entry.name
            if rel in parent_dirs and depth < max_depth:
                # Structural parent: descend instead of offering it for deletion.
                found.extend(_walk(entry, rel, depth + 1))
            else:
                found.append({"name": rel, "is_configured": rel in configured_groups})
        return found

    # ``_walk`` is total: every filesystem call it makes is guarded, so an
    # unreadable subtree is logged and skipped rather than raised here. The
    # previous single ``except OSError`` around the whole walk is what turned
    # one inaccessible folder into a 500 for the entire listing.
    entries = _walk(Path(target_base), "", 1)
    return _success("", items=sorted(entries, key=lambda x: str(x["name"])))


def _delete_folder(
    name: str,
    target_base: str,
    auto_create_libraries: bool,
    url: str,
    api_key: str,
) -> tuple[bool, str | None]:
    """Delete a single folder and optionally its Jellyfin library.

    Args:
        name: Folder name (validated against path traversal).
        target_base: Absolute base path for the target directory.
        auto_create_libraries: Whether to also clean up the Jellyfin library.
        url: Jellyfin server URL.
        api_key: Jellyfin API key.

    Returns:
        ``(deleted, error_message)`` where *deleted* is True if the folder
        was removed successfully.

    """
    # Group names may be nested ("Anime/Action"); normalisation rejects
    # absolute paths and ``.``/``..`` segments, so the result always stays
    # below target_base. The resolve() check below is the second line of
    # defence against symlinked sub-directories.
    relpath = normalize_group_relpath(name)
    if relpath is None:
        return False, f"Invalid folder name: {name}"
    path = Path(target_base).joinpath(*relpath.split("/"))
    # Resolve the path to ensure it is still within target_base (symlink-safe)
    try:
        resolved = path.resolve()
    except (OSError, RuntimeError):
        resolved = path
    try:
        base_resolved = Path(target_base).resolve()
    except (OSError, RuntimeError):
        base_resolved = Path(target_base)
    try:
        resolved.relative_to(base_resolved)
    except ValueError:
        return False, f"Path traversal detected for: {name}"
    try:
        exists_and_is_dir = path.exists() and path.is_dir()
    except OSError as exc:
        # ``exists()``/``is_dir()`` run ``stat`` and raise for a name the
        # kernel rejects — ``ENAMETOOLONG`` for a component past ``NAME_MAX``,
        # or ``EIO``/``ELOOP`` for a damaged entry. The caller expects
        # ``(deleted, error)`` and turns an unhandled ``OSError`` into an
        # HTTP 500 for the whole request, so report it as this folder's
        # failure instead.
        # ``OSError``'s own message repeats the offending path verbatim, which
        # for a rejected long name is thousands of characters. Report only the
        # reason and the already-elided name.
        reason = exc.strerror or type(exc).__name__
        logger.warning("cleanup: cannot stat %s: %s", _short(name), reason)
        return False, f"Failed to inspect {_short(name)}: {reason}"
    if not exists_and_is_dir:
        return False, None
    # Reject symlinks explicitly. ``path.is_dir()`` follows symlinks, so a
    # symlink pointing at a directory would otherwise pass the check above
    # and then hit ``shutil.rmtree``'s confusing "Cannot call rmtree on a
    # symbolic link" error. The cleanup GET endpoint already excludes
    # symlinks; this is the second line of defence for direct POSTs.
    if path.is_symlink():
        return False, f"Refusing to delete symlink: {name}"
    try:
        shutil.rmtree(path)
        _prune_empty_parents(path.parent, Path(target_base))
        if auto_create_libraries and url and api_key:
            try:
                delete_virtual_folder(url, api_key, name)
            except (RuntimeError, OSError) as e:
                logger.warning("Failed to delete Jellyfin library '%s': %s", name, e)
    except OSError as exc:
        return False, f"Failed to delete {name}: {exc}"
    else:
        return True, None


def _prune_empty_parents(directory: Path, base: Path) -> None:
    """Remove now-empty parent directories left behind by a nested group.

    Walks upwards from *directory* and removes each directory that became
    empty, stopping at *base* (which is never removed).

    Args:
        directory: The first parent to consider.
        base: The target root; the walk never goes at or above it.

    """
    try:
        base_resolved = base.resolve()
    except (OSError, RuntimeError):
        return

    current = directory
    while True:
        try:
            resolved = current.resolve()
        except (OSError, RuntimeError):
            return
        if resolved == base_resolved or base_resolved not in resolved.parents:
            return
        try:
            next(current.iterdir())
        except StopIteration:
            pass  # empty -> remove it
        except OSError:
            return
        else:
            return  # still holds entries
        try:
            current.rmdir()
        except OSError:
            return
        current = current.parent


@bp.route("/api/cleanup", methods=["POST"])
def perform_cleanup() -> ResponseReturnValue:
    """Delete the selected folders from the target directory."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _error("Request body must be JSON", 400)

    folders = data.get("folders", [])
    if not isinstance(folders, list):
        return _error("'folders' must be a list", 400)

    config: dict[str, Any] = load_config()
    target_base: str = str(config.get("target_path") or "")
    if not target_base or not _safe_exists(target_base):
        return _error("Target path not found", 404)

    auto_create_libraries: bool = bool(config.get("auto_create_libraries"))
    url: str = str(config.get("jellyfin_url") or "").rstrip("/")
    api_key: str = str(config.get("api_key") or "")

    deleted: int = 0
    errors: list[str] = []
    seen: set[str] = set()
    for name in folders:
        if not isinstance(name, str):
            errors.append("Folder name must be a string")
            continue
        if name in seen:
            continue
        seen.add(name)
        # Validation (including nested-path support and path-traversal
        # rejection) happens inside _delete_folder via normalize_group_relpath.
        # A separate _is_valid_folder_name check here would wrongly reject
        # nested group names like "Anime/Action" that the cleanup UI offers.
        removed, err = _delete_folder(
            name,
            target_base,
            auto_create_libraries,
            url,
            api_key,
        )
        if removed:
            deleted += 1
        elif err:
            errors.append(err)

    if errors:
        return jsonify(
            {"status": "partial_success", "deleted": deleted, "errors": errors},
        ), 207
    return _success("", deleted=deleted)


# ---------------------------------------------------------------------------
# Auto-detect paths
# ---------------------------------------------------------------------------


def _search_local_filesystem(
    filename: str,
    search_roots: list[str],
    *,
    timeout: int = _AUTO_DETECT_TIMEOUT,
    max_files: int = _AUTO_DETECT_MAX_FILES,
) -> str | None:
    """Walk *search_roots* looking for *filename*.

    Prunes mount points (except the root itself), enforces a *timeout* and
    *max_files* cap, and stops at _AUTO_DETECT_MAX_DEPTH path-component depth
    measured relative to each search root.

    Returns the absolute path of the first match found, or ``None``.

    Args:
        filename: The filename to search for.
        search_roots: List of root directories to search in.

    """
    walk_start = time.monotonic()
    files_scanned = 0
    for root in search_roots:
        if not Path(root).is_dir():
            continue
        # Measure depth relative to the search root so the _AUTO_DETECT_MAX_DEPTH
        # cap is consistent regardless of where the root lives in the filesystem
        # (e.g. "/media" vs "/home/user").  Previously the depth was measured
        # from the filesystem root, so the effective limit varied with the root's
        # own depth.
        root_depth = len(Path(root).parts)
        for dirpath, dirnames, filenames in os.walk(root):
            # Compute depth once per directory entry
            dir_depth = len(Path(dirpath).parts) - root_depth
            try:
                is_mount = os.path.ismount(dirpath)
            except OSError:
                # Permission denied or inaccessible — skip this directory
                dirnames.clear()
                continue
            if is_mount and dirpath != root:
                # Check files in the mount point directory itself before
                # pruning subdirectories from the walk.
                if filename in filenames:
                    return str(Path(dirpath) / filename)
                dirnames.clear()
                continue
            if time.monotonic() - walk_start > timeout:
                logger.warning(
                    "auto-detect timed out after %ds, %d files scanned",
                    timeout,
                    files_scanned,
                )
                return None
            files_scanned += len(filenames)
            if files_scanned > max_files:
                logger.warning(
                    "auto-detect hit file limit (%d), stopping scan",
                    max_files,
                )
                return None
            if filename in filenames:
                return str(Path(dirpath) / filename)
            if dir_depth > _AUTO_DETECT_MAX_DEPTH:
                dirnames.clear()
    return None


def _compute_common_root(
    jellyfin_path: str,
    host_path: str,
) -> tuple[str | None, str | None]:
    """Infer the common root prefixes from a Jellyfin path and its host match.

    Counts matching trailing path components and returns the inferred
    ``(jellyfin_root, host_root)`` pair.

    Args:
        jellyfin_path: Jellyfin-side media path.
        host_path: Host-side media path.

    """
    j_parts = Path(jellyfin_path).parts
    h_parts = Path(host_path).parts
    common_count = 0
    while (
        common_count < len(j_parts)
        and common_count < len(h_parts)
        and j_parts[-(common_count + 1)] == h_parts[-(common_count + 1)]
    ):
        common_count += 1

    if common_count > 0:
        j_slice = j_parts[:-common_count]
        h_slice = h_parts[:-common_count]
        j_root = str(Path(*j_slice)) if j_slice else os.sep
        h_root = str(Path(*h_slice)) if h_slice else os.sep
        return j_root, h_root
    return None, None


@bp.route("/api/jellyfin/auto-detect-paths", methods=["POST"])
def auto_detect_paths() -> ResponseReturnValue:
    """Attempt to automatically detect Jellyfin and host media root paths.

    Fetches a sample of movie paths from Jellyfin and then searches the local
    filesystem (home directory, ``/media``, ``/mnt``) for the matching files.
    The common path prefix between the Jellyfin path and the local path is
    returned as the suggested ``media_path_in_jellyfin`` /
    ``media_path_on_host`` pair.

    Returns:
        JSON with ``status`` and a ``detected`` object containing
        ``media_path_in_jellyfin``, ``media_path_on_host``, and
        ``target_path``.

    """
    url, api_key = _get_jellyfin_config(
        missing_msg="Server settings required for detection",
    )

    try:
        items = fetch_jellyfin_items(
            url,
            api_key,
            {
                "Recursive": RECURSIVE_TRUE,
                "IncludeItemTypes": "Movie",
                "Limit": str(_AUTO_DETECT_SAMPLE_LIMIT),
                "Fields": "Path",
            },
            timeout=_AUTO_DETECT_JELLYFIN_TIMEOUT,
        )
    except RuntimeError as exc:
        return _error(str(exc), 400)

    if not items:
        return _error("No media found in Jellyfin to detect paths", 400)

    home_dir = str(Path.home())
    detected_j_root: str | None = None
    detected_h_root: str | None = None

    for item in items:
        j_path = item.get("Path")
        if not j_path:
            continue

        match_found = _search_local_filesystem(
            Path(j_path).name,
            list(_DEFAULT_SEARCH_ROOTS),
        )
        if match_found:
            detected_j_root, detected_h_root = _compute_common_root(j_path, match_found)
            if detected_j_root:
                break

    suggested_target = str(Path(home_dir) / "jellyfin-groupings-virtual")
    if not os.access(home_dir, os.W_OK):
        suggested_target = str(Path.cwd() / "jellyfin-groupings-virtual")

    return _success(
        "",
        detected={
            "media_path_in_jellyfin": detected_j_root,
            "media_path_on_host": detected_h_root,
            "target_path": suggested_target,
            "target_path_in_jellyfin": suggested_target,
        },
    )


# ---------------------------------------------------------------------------
# Filesystem browser
# ---------------------------------------------------------------------------


@bp.route("/api/browse", methods=["GET"])
def browse_directory() -> ResponseReturnValue:
    """Return the immediate (non-hidden) subdirectories of a given path.

    Used by the frontend folder picker to navigate the host filesystem.
    Access is restricted to paths under the whitelisted roots (home directory,
    ``/media``, ``/mnt``).

    Query Parameters:
        path (str): Absolute path to list.  Defaults to the user's home
            directory.

    Returns:
        JSON with ``status``, ``current`` path, nullable ``parent`` path, and
        ``dirs`` (sorted list of subdirectory names).

    """
    raw: str = request.args.get("path", "")
    try:
        # ``resolve()`` can raise OSError (e.g. symlink loops) or RuntimeError
        # for certain malformed paths; treat those as a bad request rather
        # than surfacing an unhandled 500 to the client.
        path: str = str(Path(raw).resolve()) if raw else str(Path.home())
    except (OSError, RuntimeError, ValueError):
        return _error("Invalid path", 400)

    # Fall back to parent if the supplied path resolves to a file.
    #
    # ``is_dir()`` runs ``stat``, which raises ``OSError`` for a path the
    # kernel refuses outright — most visibly ``ENAMETOOLONG`` for a component
    # over ``NAME_MAX``. ``resolve()`` above does not catch that case because
    # it only resolves the parts that exist, so a long ``?path=`` aborted the
    # handler with an unhandled 500 instead of the 400 that every other
    # malformed path gets.
    try:
        is_dir = Path(path).is_dir()
    except OSError as exc:
        logger.warning(
            "browse: cannot stat %s: %s", _short(path), _os_error_reason(exc)
        )
        return _error("Invalid path", 400)
    if not is_dir:
        path = str(Path(path).parent)

    if not _path_is_allowed(path):
        return _error("Access to this path is not permitted", 403)

    try:
        candidates = list(Path(path).iterdir())
    except PermissionError:
        candidates = []
    except OSError as exc:
        return _error(str(exc), 400)

    # ``is_dir()`` follows a ``stat`` and raises for an entry it cannot
    # classify (a stale handle on a dropped mount, an I/O error). Letting that
    # escape the comprehension discarded every sibling the user could browse,
    # so each entry is judged on its own and a bad one is skipped.
    entries: list[str] = []
    for entry in candidates:
        if entry.name.startswith("."):
            continue
        try:
            # is_dir() follows symlinks, so exclude links explicitly — a link
            # pointing outside the browse roots must never be navigable.
            if entry.is_symlink() or not entry.is_dir():
                continue
        except OSError as exc:
            logger.warning("browse: cannot stat %s: %s", entry, exc)
            continue
        entries.append(entry.name)

    entries.sort()

    parent: str | None = str(Path(path).parent) if path != os.sep else None

    return _success("", current=path, parent=parent, dirs=entries)


# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------


@bp.route("/api/version", methods=["GET"])
def version() -> ResponseReturnValue:
    """Return the current application version.

    Returns:
        JSON with ``version`` string.

    """
    return jsonify({"version": __version__})


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@bp.route("/api/health", methods=["GET"])
def health_check() -> ResponseReturnValue:
    """Provide a health check endpoint for Docker / Kubernetes probes.

    Returns a JSON response with:

    * Service status and uptime
    * Configuration sanity check
    * Scheduler status (running, job count, next run times)
    * Jellyfin server reachability (quick connectivity test)
    * Active environment overrides

    Returns:
        JSON with ``status``, ``healthcheck`` block, ``server`` metadata,
        ``scheduler`` status, and ``jellyfin`` reachability.

    """
    try:
        config: dict[str, Any] = load_config()
        url: str = str(config.get("jellyfin_url") or "")
        api_key: str = str(config.get("api_key") or "")
        configured: bool = bool(url and api_key and config.get("target_path"))

        # Scheduler information
        scheduler_info: dict[str, Any] = {
            "running": False,
            "job_count": 0,
            "next_run_times": [],
        }
        try:
            if hasattr(_scheduler, "running") and _scheduler.running:
                scheduler_info["running"] = True
                jobs = _scheduler.get_jobs()
                # Ensure we have a real list of dict-serializable entries
                if isinstance(jobs, list):
                    scheduler_info["job_count"] = len(jobs)
                    next_runs: list[dict[str, str]] = []
                    for job in jobs:
                        try:
                            jid = str(getattr(job, "id", ""))
                            jname = str(getattr(job, "name", ""))
                            run_time = getattr(job, "next_run_time", None)
                            entry: dict[str, str] = {
                                "id": jid,
                                "name": jname,
                            }
                            if run_time is not None:
                                entry["next_run"] = str(run_time.isoformat())
                            next_runs.append(entry)
                        except (AttributeError, TypeError, ValueError, RuntimeError):
                            continue
                    scheduler_info["next_run_times"] = next_runs
        except (ValueError, OSError, RuntimeError):
            logger.debug("Could not fetch scheduler details", exc_info=True)

        # Jellyfin reachability check (lightweight ping)
        jellyfin_reachable: bool | None = None
        if url:
            try:
                resp = network.get(
                    f"{url}/System/Ping",
                    timeout=_TEST_SERVER_TIMEOUT,
                )
                jellyfin_reachable = resp.status_code < 500
            except (requests.RequestException, OSError, ValueError):
                jellyfin_reachable = False

        return jsonify(
            {
                "status": "ok",
                "version": __version__,
                "healthcheck": {
                    "ok": True,
                    "configured": configured,
                    "groups": len(config.get("groups", [])),
                    "env_overrides": list(_active_env_overrides().keys()),
                },
                "server": {
                    "uptime_seconds": math.ceil(time.time() - _APP_START_TIME),
                    "started_at": time.strftime(
                        "%Y-%m-%dT%H:%M:%SZ",
                        time.gmtime(_APP_START_TIME),
                    ),
                },
                "scheduler": scheduler_info,
                "jellyfin": {
                    "reachable": jellyfin_reachable,
                },
            },
        )
    except Exception:
        logger.exception("Health check failed")
        return jsonify(
            {
                "status": "error",
                "healthcheck": {
                    "ok": False,
                    "error": "internal_error",
                },
            },
        ), 500


# ---------------------------------------------------------------------------
# Test Dashboard
# ---------------------------------------------------------------------------


@bp.route("/api/test/results", methods=["GET"])
def get_test_results() -> ResponseReturnValue:
    """Return the contents of the latest test output logs."""
    results = {}
    for filename in _TEST_RESULT_FILENAMES:
        if Path(filename).exists():
            try:
                with Path(filename).open(encoding="utf-8") as f:
                    results[filename] = f.read()
            except (OSError, UnicodeDecodeError):
                results[filename] = "Error reading file."
        else:
            results[filename] = "No output found."

    return _success("", results=results)


# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------


@bp.route("/")
def index() -> ResponseReturnValue:
    """Serve the single-page frontend.

    Returns:
        The rendered ``templates/base.html`` Jinja2 template.

    """
    return render_template("base.html")
