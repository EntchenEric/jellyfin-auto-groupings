from sync import run_cleanup_broken_symlinks


def test_run_cleanup_broken_symlinks(tmp_path):
    """Test that broken symlinks are removed and healthy ones are kept."""
    target_base = tmp_path / "target"
    target_base.mkdir()
    # Create a real file
    real_file = tmp_path / "original.txt"
    real_file.write_text("hello")
    # Create a healthy symlink
    healthy_link = target_base / "healthy.txt"
    healthy_link.symlink_to(real_file)
    # Create a broken symlink (target doesn't exist)
    broken_link = target_base / "broken.txt"
    broken_link.symlink_to(tmp_path / "nonexistent.txt")
    # Create a broken symlink in a subdirectory
    sub_dir = target_base / "subdir"
    sub_dir.mkdir()
    broken_sub_link = sub_dir / "broken_sub.txt"
    broken_sub_link.symlink_to(tmp_path / "nonexistent_sub.txt")
    # Verify initial state
    assert healthy_link.is_symlink()
    assert healthy_link.exists()
    assert broken_link.is_symlink()
    assert not broken_link.exists()
    assert broken_sub_link.is_symlink()
    assert not broken_sub_link.exists()
    # Run cleanup
    config = {"target_path": str(target_base), "groups": []}
    deleted_count = run_cleanup_broken_symlinks(config)
    # Verify final state
    assert deleted_count == 2
    assert healthy_link.exists()
    assert not broken_link.is_symlink()
    assert not broken_sub_link.is_symlink()


def test_run_cleanup_invalid_path():
    """Test cleanup with a non-existent path."""
    config = {"target_path": "/non/existent/path/at/all", "groups": []}
    deleted_count = run_cleanup_broken_symlinks(config)
    assert deleted_count == 0
