"""Tests for nested group directories in _process_group."""

from pathlib import Path
from typing import Any

from sync import _process_group


def _run(group: dict[str, Any], target: Path) -> dict[str, Any]:
    """Invoke _process_group with a source that resolves to no items."""
    return _process_group(
        group,
        str(target),
        "http://jellyfin.invalid",
        "key",
        "/data",
        "/data",
        "",
        "",
        "",
        dry_run=False,
    )


class TestNestedGroupDirectories:
    """A group name with '/' creates the corresponding folder tree."""

    def test_nested_name_creates_directory_tree(self, tmp_path, monkeypatch) -> None:
        """'Anime/Action' produces <target>/Anime/Action."""
        monkeypatch.setattr(
            "sync._resolve_group_source", lambda *a, **k: ([], None, None)
        )
        target = tmp_path / "groupings"
        target.mkdir()

        result = _run(
            {"name": "Anime/Action", "source_type": "genre", "source_value": "Action"},
            target,
        )

        assert "error" not in result or result.get("error") is None
        assert (target / "Anime" / "Action").is_dir()

    def test_deeply_nested_name(self, tmp_path, monkeypatch) -> None:
        """More than two levels are supported."""
        monkeypatch.setattr(
            "sync._resolve_group_source", lambda *a, **k: ([], None, None)
        )
        target = tmp_path / "groupings"
        target.mkdir()

        _run(
            {
                "name": "Anime/By Studio/Ghibli",
                "source_type": "genre",
                "source_value": "Action",
            },
            target,
        )

        assert (target / "Anime" / "By Studio" / "Ghibli").is_dir()

    def test_traversal_name_is_rejected(self, tmp_path, monkeypatch) -> None:
        """A name escaping the target base errors out and touches nothing.

        This matters because the group directory is rmtree()d before it is
        recreated — an unchecked name would delete an arbitrary directory.
        """
        monkeypatch.setattr(
            "sync._resolve_group_source", lambda *a, **k: ([], None, None)
        )
        target = tmp_path / "groupings"
        target.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "precious.txt").write_text("keep me")

        result = _run(
            {"name": "../outside", "source_type": "genre", "source_value": "Action"},
            target,
        )

        assert result["error"] == "Invalid group name"
        assert result["links"] == 0
        assert (outside / "precious.txt").exists()

    def test_plain_name_still_works(self, tmp_path, monkeypatch) -> None:
        """Non-nested names behave exactly as before."""
        monkeypatch.setattr(
            "sync._resolve_group_source", lambda *a, **k: ([], None, None)
        )
        target = tmp_path / "groupings"
        target.mkdir()

        _run(
            {"name": "Action", "source_type": "genre", "source_value": "Action"}, target
        )

        assert (target / "Action").is_dir()


class TestParentGroupPreservesChildren:
    """A group whose directory also parents nested groups must not wipe them."""

    def test_parent_sync_keeps_child_group_links(self, tmp_path, monkeypatch) -> None:
        """Syncing 'Action' leaves 'Action/Filme' and its symlinks alone."""
        monkeypatch.setattr(
            "sync._resolve_group_source", lambda *a, **k: ([], None, None)
        )
        target = tmp_path / "groupings"
        target.mkdir()

        # The child group synced first and left its links behind.
        child = target / "Action" / "Filme"
        child.mkdir(parents=True)
        (child / "0001 - Movie.mkv").symlink_to(tmp_path / "movie.mkv")

        # The parent group's own stale link, which should be cleared.
        (target / "Action" / "0001 - Stale.mkv").symlink_to(tmp_path / "stale.mkv")

        _run(
            {"name": "Action", "source_type": "genre", "source_value": "Action"},
            target,
        )

        assert (child / "0001 - Movie.mkv").is_symlink()
        assert not (target / "Action" / "0001 - Stale.mkv").exists()

    def test_parent_sync_removes_its_own_cover(self, tmp_path, monkeypatch) -> None:
        """Regular files in the group directory are still cleared."""
        monkeypatch.setattr(
            "sync._resolve_group_source", lambda *a, **k: ([], None, None)
        )
        target = tmp_path / "groupings"
        target.mkdir()
        group_dir = target / "Action"
        group_dir.mkdir()
        (group_dir / "poster.jpg").write_text("old cover")

        _run(
            {"name": "Action", "source_type": "genre", "source_value": "Action"},
            target,
        )

        assert not (group_dir / "poster.jpg").exists()
