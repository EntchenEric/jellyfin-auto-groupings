"""Tests for the ``APP_PASSWORD`` gate in :mod:`routes`.

Two behaviours are pinned here:

* A password containing non-ASCII characters must not break authentication.
  ``hmac.compare_digest`` raises ``TypeError`` for ``str`` arguments with
  non-ASCII characters, so an operator who set ``APP_PASSWORD=pässwort`` used
  to get HTTP 500 on *every* authenticated request — the whole UI was
  unreachable, not just that one credential.
* The comparison must still reject wrong passwords and still be constant
  time, which is why the fix encodes to bytes rather than falling back to
  ``==``.
"""

import base64

import pytest

import routes


def _basic(password: str, user: str = "ignored") -> dict[str, str]:
    """Build an ``Authorization: Basic`` header for *user* / *password*."""
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


@pytest.fixture
def protected_client(monkeypatch):
    """A test client whose app requires ``APP_PASSWORD``.

    The password is set on the imported module attribute (not the environment)
    because :mod:`routes` reads it once at import time.
    """
    from app import app as flask_app

    monkeypatch.setattr(routes, "_APP_PASSWORD", "pässwort-ümlaut")
    previous_testing = flask_app.config.get("TESTING")
    flask_app.config.update({"TESTING": True})
    client = flask_app.test_client()
    yield client
    flask_app.config["TESTING"] = previous_testing


def test_non_ascii_password_is_accepted(protected_client):
    """A non-ASCII password authenticates instead of raising HTTP 500."""
    response = protected_client.get("/api/config", headers=_basic("pässwort-ümlaut"))

    assert response.status_code == 200
    # The config payload itself, i.e. authentication passed and the handler ran.
    assert "jellyfin_url" in response.get_json()


def test_non_ascii_password_is_not_bypassed(protected_client):
    """A wrong non-ASCII password is still rejected with 401."""
    response = protected_client.get("/api/config", headers=_basic("pässwort-falsch"))

    assert response.status_code == 401


def test_ascii_password_still_works(protected_client, monkeypatch):
    """The byte-wise comparison keeps plain ASCII passwords working."""
    monkeypatch.setattr(routes, "_APP_PASSWORD", "correct horse")

    assert (
        protected_client.get("/api/config", headers=_basic("correct horse")).status_code
        == 200
    )
    assert (
        protected_client.get("/api/config", headers=_basic("wrong")).status_code == 401
    )


def test_missing_credentials_are_rejected(protected_client):
    """No ``Authorization`` header at all yields the challenge, not a 500."""
    response = protected_client.get("/api/config")

    assert response.status_code == 401
    assert "Basic" in response.headers["WWW-Authenticate"]


def test_health_check_stays_public_for_container_probes(protected_client):
    """The Docker healthcheck hits ``/api/health`` without credentials."""
    assert protected_client.get("/api/health").status_code == 200
