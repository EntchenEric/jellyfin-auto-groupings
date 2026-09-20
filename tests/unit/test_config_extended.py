import pytest
from config import Config

def test_config_defaults():
    cfg = Config()
    assert cfg is not None
