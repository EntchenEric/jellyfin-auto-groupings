"""Guards that keep the documentation truthful about routes and env vars.

The docs are not executed, so nothing fails when a route is renamed or removed
and ``docs/ARCHITECTURE.md`` keeps advertising it, or when a route appears and
neither ``docs/API.md`` nor the README mentions it. This module reads the
Flask blueprint and the Python sources and compares them against the prose.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ROUTES_PY = ROOT / "routes.py"
API_DOC = ROOT / "docs" / "API.md"
ARCHITECTURE_DOC = ROOT / "docs" / "ARCHITECTURE.md"
README = ROOT / "README.md"
ENV_EXAMPLE = ROOT / ".env.example"

_ROUTE_RE = re.compile(
    r'@\w+\.route\(\s*"([^"]+)"\s*,\s*methods=\[([^\]]*)\]',
)

#: Env vars read by the app that the README must document somewhere.
_REQUIRED_ENV_DOCS = [
    "JELLYFIN_API_KEY",
    "APP_PASSWORD",
    "SCHEDULER_ENABLED",
    "LOG_LEVEL",
    "GUNICORN_WORKERS",
    "GUNICORN_TIMEOUT",
    "NETWORK_RETRY_TOTAL",
    "NETWORK_RETRY_BACKOFF_FACTOR",
    "NETWORK_RETRY_STATUS_FORCELIST",
    "ALLOWED_NON_CSRF_ENDPOINTS",
]


def _declared_routes() -> set[tuple[str, str]]:
    """Return every ``(METHOD, path)`` pair the blueprint actually serves."""
    source = ROUTES_PY.read_text(encoding="utf-8")
    routes: set[tuple[str, str]] = set()
    for path, raw_methods in _ROUTE_RE.findall(source):
        for method in re.findall(r'"([A-Z]+)"', raw_methods):
            routes.add((method, path))
    return routes


def _read_env_names(path: Path) -> set[str]:
    return set(
        re.findall(r"\b([A-Z][A-Z0-9_]{3,})\b", path.read_text(encoding="utf-8"))
    )


def test_blueprint_declares_routes():
    """A parser that silently matched nothing would make every other test pass."""
    routes = _declared_routes()
    assert routes, "no routes parsed from routes.py — the decorator regex is stale"
    assert ("GET", "/api/health") in routes
    assert ("POST", "/api/sync") in routes


@pytest.mark.parametrize(
    ("method", "path"),
    sorted(_declared_routes()),
)
def test_every_route_is_documented_in_api_md(method: str, path: str):
    """A route a client can call but the API reference omits is undiscoverable."""
    doc = API_DOC.read_text(encoding="utf-8")
    assert f"{method} {path}" in doc, (
        f"{method} {path} is served by routes.py but missing from docs/API.md"
    )


def test_api_md_documents_no_removed_routes():
    """The reverse drift: docs promising an endpoint that no longer exists."""
    doc = API_DOC.read_text(encoding="utf-8")
    documented = set(
        re.findall(r"^## `(GET|POST|PUT|DELETE|PATCH) (/[^`]*)`", doc, re.MULTILINE)
    )
    declared = _declared_routes()
    stale = documented - declared
    assert not stale, (
        f"docs/API.md documents routes that routes.py does not serve: {sorted(stale)}"
    )


def test_architecture_md_does_not_claim_absent_endpoints():
    """ARCHITECTURE.md listed proxy, export/import, and wizard routes as endpoints.

    None of those exist: export, import, and the wizard are client-side and
    persist through ``POST /api/config``. Naming them under "all HTTP
    endpoints" sent readers looking for handlers that were never written.
    """
    text = ARCHITECTURE_DOC.read_text(encoding="utf-8")
    for absent in ("/api/export", "/api/import", "/api/wizard", "/api/collections"):
        assert absent not in text, f"ARCHITECTURE.md still advertises {absent}"


def test_env_example_variables_are_documented_in_readme():
    """`.env.example` tells the user to "see README.md for full documentation"."""
    readme = README.read_text(encoding="utf-8")
    example = _read_env_names(ENV_EXAMPLE)
    # `ENV` scaffolding words and prose are not variables.
    skip = {"README", "API", "HTTP", "URL", "JSON", "CSRF", "UI", "MAL", "TMDb"}
    missing = sorted(
        name
        for name in example - skip
        if "_" in name and not name.islower() and name not in readme
    )
    assert not missing, f".env.example documents variables the README omits: {missing}"


@pytest.mark.parametrize("name", _REQUIRED_ENV_DOCS)
def test_key_env_vars_documented_in_readme(name: str):
    readme = README.read_text(encoding="utf-8")
    assert name in readme, f"{name} is read by the app but absent from README.md"


def test_readme_configuration_section_covers_security():
    """APP_PASSWORD gates the whole UI; a README that omits it hides the feature."""
    readme = README.read_text(encoding="utf-8")
    config_section = readme.split("## Configuration", 1)[1].split("\n## ", 1)[0]
    assert "APP_PASSWORD" in config_section
    assert "Basic Auth" in config_section


def _auth_exempt_endpoints() -> set[str]:
    """Return the endpoint names ``_check_auth`` lets through unauthenticated."""
    source = ROUTES_PY.read_text(encoding="utf-8")
    handler = source.split("def _check_auth", 1)[1].split("\ndef ", 1)[0]
    return set(re.findall(r'request\.endpoint == "([^"]+)"', handler))


def test_api_md_auth_notes_match_the_enforced_exemptions():
    """Documented auth must match ``_check_auth``, which exemptions silently break.

    ``/api/health`` is exempted in ``routes.py`` so container probes work without
    credentials, but its API.md section claimed auth was required while the
    overview paragraph said it was public — a contradiction a reader cannot
    resolve. Derive the truth from the code instead of trusting the prose.
    """
    exempt = _auth_exempt_endpoints()
    assert exempt, "no exemptions parsed from _check_auth — the regex is stale"

    # ``main.index`` serves the SPA at ``/``; the rest are ``/api/*`` routes.
    doc = API_DOC.read_text(encoding="utf-8")
    route_functions = dict(
        re.findall(
            r'@\w+\.route\(\s*"(/api/[^"]+)"[^)]*\)\s*\ndef (\w+)',
            ROUTES_PY.read_text(encoding="utf-8"),
        )
    )

    for endpoint in exempt:
        function_name = endpoint.removeprefix("main.")
        path = next(
            (p for p, f in route_functions.items() if f == function_name),
            None,
        )
        if path is None:
            continue
        section = doc.split(f"## `GET {path}`", 1)
        assert len(section) == 2, f"docs/API.md has no section for public {path}"
        auth_line = next(
            (line for line in section[1].splitlines() if line.startswith("**Auth:**")),
            "",
        )
        assert auth_line, f"docs/API.md section for {path} has no **Auth:** note"
        assert "Not required" in auth_line, (
            f"{path} is exempt from auth in routes.py but docs/API.md still "
            f"claims auth is required: {auth_line!r}"
        )
