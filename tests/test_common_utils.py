import time
import pytest
from network import get, post, _build_retry_session

def test_build_retry_session():
    session = _build_retry_session()
    assert session is not None
