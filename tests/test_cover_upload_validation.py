"""Cover uploads must reject payloads that are not the image they claim to be.

``POST /api/upload_cover`` decoded the base64 body with
``base64.b64decode(encoded)``, which ignores every character it does not
recognise instead of raising. A body of pure garbage (``"@@@"``) therefore
decoded to ``b""``, the handler wrote a zero-byte file, and the API answered
``{"status": "success"}``. The broken cover only appeared later in the UI, with
nothing pointing at the upload that caused it.

The declared MIME type was also never compared with the bytes: any payload
could be stored under a ``.png`` or ``.jpg`` name as long as the data URL said
``image/png``. Both checks now happen before the file is written, and an empty
``group_name`` is refused because the cover file name is ``md5(group_name)`` —
every unnamed group shared one file.
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from app import app as flask_app

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 24
_WEBP = b"RIFF" + b"\x00" * 4 + b"WEBP" + b"\x00" * 24


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Flask client whose config stores covers under an isolated directory."""
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    (tmp_path / "config.json").write_text(
        json.dumps({"target_path": str(tmp_path)}),
        encoding="utf-8",
    )
    flask_app.config.update(TESTING=False)
    return flask_app.test_client()


def _post(client, name: str, image: str):
    return client.post(
        "/api/upload_cover",
        json={"group_name": name, "image": image},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )


def _data_url(mime: str, payload: bytes) -> str:
    return f"data:{mime};base64,{base64.b64encode(payload).decode('ascii')}"


def _stored_covers(tmp_path: Path) -> list[Path]:
    return sorted((tmp_path / ".covers").glob("*"))


def test_garbage_base64_is_rejected(client, tmp_path):
    """A body that decodes to nothing must not be stored as a cover."""
    response = _post(client, "Movies", "data:image/png;base64,@@@")

    assert response.status_code == 400
    assert response.get_json()["status"] == "error"
    assert "Malformed image data" in response.get_json()["message"]
    assert _stored_covers(tmp_path) == []


def test_empty_base64_body_is_rejected(client, tmp_path):
    """An empty payload is not a zero-byte cover, it is a broken request."""
    response = _post(client, "Movies", "data:image/png;base64,")

    assert response.status_code == 400
    assert _stored_covers(tmp_path) == []


def test_declared_mime_must_match_the_bytes(client, tmp_path):
    """JPEG bytes declared as PNG must not be saved as a ``.png`` cover."""
    response = _post(client, "Movies", _data_url("image/png", _JPEG))

    assert response.status_code == 400
    assert "not a valid image/png file" in response.get_json()["message"]
    assert _stored_covers(tmp_path) == []


def test_plain_text_is_not_an_image(client, tmp_path):
    """``"hello"`` is valid base64 but is not an image of any accepted type."""
    response = _post(client, "Movies", "data:image/png;base64,aGVsbG8=")

    assert response.status_code == 400
    assert _stored_covers(tmp_path) == []


def test_riff_that_is_not_webp_is_rejected(client, tmp_path):
    """``RIFF`` alone also matches WAV/AVI, so the ``WEBP`` marker is required."""
    wave = b"RIFF" + b"\x00" * 4 + b"WAVE" + b"\x00" * 16

    response = _post(client, "Movies", _data_url("image/webp", wave))

    assert response.status_code == 400
    assert _stored_covers(tmp_path) == []


def test_empty_group_name_is_rejected(client, tmp_path):
    """Covers are named ``md5(group_name)``, so a blank name has no owner."""
    response = _post(client, "   ", _data_url("image/png", _PNG))

    assert response.status_code == 400
    assert "group_name must not be empty" in response.get_json()["message"]
    assert _stored_covers(tmp_path) == []


@pytest.mark.parametrize(
    ("mime", "payload", "suffix"),
    [
        ("image/png", _PNG, ".png"),
        ("image/jpeg", _JPEG, ".jpg"),
        ("image/webp", _WEBP, ".webp"),
    ],
)
def test_valid_images_are_still_saved(client, tmp_path, mime, payload, suffix):
    """The stricter checks must not reject a real, correctly labelled image."""
    response = _post(client, "Movies", _data_url(mime, payload))

    assert response.status_code == 200
    assert response.get_json()["status"] == "success"
    stored = _stored_covers(tmp_path)
    assert [path.suffix for path in stored] == [suffix]
    assert stored[0].read_bytes() == payload


def test_wrapped_base64_is_accepted(client, tmp_path):
    """A base64 body broken across lines is valid and must still be saved.

    Line breaks are stripped before the strict decode, so formatting added by a
    proxy or a hand-written request does not fail the upload for the wrong
    reason (a stray ``+`` or ``@`` still does).
    """
    encoded = base64.b64encode(_PNG).decode("ascii")
    wrapped = "\n".join(encoded[i : i + 8] for i in range(0, len(encoded), 8))

    response = _post(client, "Movies", f"data:image/png;base64,{wrapped}")

    assert response.status_code == 200
    assert _stored_covers(tmp_path)[0].read_bytes() == _PNG
