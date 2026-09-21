import pytest

def test_common_import():
    import _common
    assert _common is not None
