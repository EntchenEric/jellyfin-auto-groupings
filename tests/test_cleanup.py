import os
import pytest
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
    os.symlink(str(real_file), str(healthy_link))
    
    # Create a broken symlink (target doesn't exist)
    broken_link = target_base / "broken.txt"
    os.symlink(str(tmp_path / "nonexistent.txt"), str(broken_link))
    
    # Create a broken symlink in a subdirectory
    sub_dir = target_base / "subdir"
    sub_dir.mkdir()
    broken_sub_link = sub_dir / "broken_sub.txt"
    os.symlink(str(tmp_path / "nonexistent_sub.txt"), str(broken_sub_link))
    
    # Verify initial state
    assert healthy_link.is_symlink()
    assert os.path.exists(healthy_link)
    assert broken_link.is_symlink()
    assert not os.path.exists(broken_link)
    assert broken_sub_link.is_symlink()
    assert not os.path.exists(broken_sub_link)
    
    # Run cleanup
    config = {"target_path": str(target_base), "groups": []}
    deleted_count = run_cleanup_broken_symlinks(config)
    
    # Verify final state
    assert deleted_count == 2
    assert healthy_link.exists()
    assert not broken_link.exists()
    assert not broken_sub_link.exists()

def test_run_cleanup_invalid_path():
    """Test cleanup with a non-existent path."""
    config = {"target_path": "/non/existent/path/at/all", "groups": []}
    deleted_count = run_cleanup_broken_symlinks(config)
    assert deleted_count == 0
