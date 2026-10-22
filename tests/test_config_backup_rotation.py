"""Tests for backup rotation in :func:`config.save_config`.

Every save renames the previous ``config.json`` to a timestamped ``.bak``
file. Without pruning, an app that saves on each settings POST accumulates
one backup per save forever — a development checkout had grown to 774
backups / 3.1 MB. ``save_config`` now keeps only the newest
``config._BACKUP_KEEP`` rotation backups.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config

_STAMPS = (
    "20260101_000000",
    "20260102_000000",
    "20260103_000000",
    "20260104_000000",
    "20260105_000000",
    "20260106_000000",
    "20260107_000000",
    "20260108_000000",
)


def _use_temp_config(tmp_path, monkeypatch):
    """Point the config module at an isolated directory."""
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")


def _seed(tmp_path, count):
    """Write *count* rotation backups with known, lexically ordered names."""
    for stamp in _STAMPS[:count]:
        (tmp_path / f"config.json.{stamp}.bak").write_text("{}", encoding="utf-8")
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")


def _backups(tmp_path):
    return sorted(p.name for p in tmp_path.glob("config.json.*.bak"))


def test_backups_are_pruned_to_the_retention_limit(tmp_path, monkeypatch):
    _use_temp_config(tmp_path, monkeypatch)
    _seed(tmp_path, config._BACKUP_KEEP + 3)

    config.save_config({"jellyfin_url": "http://example.invalid"})

    assert len(_backups(tmp_path)) == config._BACKUP_KEEP


def test_pruning_keeps_the_newest_backups(tmp_path, monkeypatch):
    _use_temp_config(tmp_path, monkeypatch)
    _seed(tmp_path, len(_STAMPS))

    config.save_config({"jellyfin_url": "http://example.invalid"})

    remaining = _backups(tmp_path)
    assert "config.json.20260101_000000.bak" not in remaining
    assert "config.json.20260102_000000.bak" not in remaining
    assert "config.json.20260108_000000.bak" in remaining


def test_backups_below_the_limit_are_untouched(tmp_path, monkeypatch):
    _use_temp_config(tmp_path, monkeypatch)
    _seed(tmp_path, config._BACKUP_KEEP - 1)

    config.save_config({"jellyfin_url": "http://example.invalid"})

    # Seeded backups survive; the save rotates the previous config into one
    # more, which fills the budget exactly.
    remaining = _backups(tmp_path)
    assert len(remaining) == config._BACKUP_KEEP
    assert "config.json.20260101_000000.bak" in remaining


def test_corrupt_backups_are_not_pruned(tmp_path, monkeypatch):
    """Corrupt-file backups are diagnostic artifacts, not rotation backups."""
    _use_temp_config(tmp_path, monkeypatch)
    corrupt = tmp_path / "config.json.corrupt.20260101_000000.bak"
    corrupt.write_text("{ not json", encoding="utf-8")
    _seed(tmp_path, len(_STAMPS))

    config.save_config({"jellyfin_url": "http://example.invalid"})

    assert corrupt.exists()


def test_pruning_ignores_unrelated_files(tmp_path, monkeypatch):
    _use_temp_config(tmp_path, monkeypatch)
    keep_me = tmp_path / "config.json.notes.txt"
    keep_me.write_text("keep", encoding="utf-8")
    _seed(tmp_path, len(_STAMPS))

    config.save_config({"jellyfin_url": "http://example.invalid"})

    assert keep_me.exists()


def test_pruning_failure_does_not_break_the_save(tmp_path, monkeypatch):
    """A pruning error must never abort persisting the config."""
    _use_temp_config(tmp_path, monkeypatch)
    _seed(tmp_path, len(_STAMPS))

    original_unlink = Path.unlink

    def _fail_for_backups(self, *args, **kwargs):
        if ".bak" in self.name:
            msg = "simulated unlink failure"
            raise OSError(msg)
        return original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", _fail_for_backups)

    config.save_config({"jellyfin_url": "http://example.invalid"})

    saved = (tmp_path / "config.json").read_text(encoding="utf-8")
    assert "example.invalid" in saved
