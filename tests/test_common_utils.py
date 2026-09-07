import time
import pytest
from network import get, post, _build_retry_session
from sync import normalize_title, extract_year

def test_normalize_title_edge_cases():
    assert normalize_title("") == ""
    assert normalize_title(None) == ""
    assert normalize_title("  Hello,  World!!!  ") == "hello world"
    assert normalize_title("Star Wars: Episode IV - A New Hope") == "star wars episode iv a new hope"

def test_extract_year_edge_cases():
    assert extract_year(None) == None
    assert extract_year("") == None
    assert extract_year("2026-09-07") == 2026
    assert extract_year("1999") == 1999
    assert extract_year("1850") == None  # Out of 1900-2099 range in extract_year regex
    assert extract_year("Released in 2024 by studio") == 2024

def test_build_retry_session():
    session = _build_retry_session()
    assert session is not None
