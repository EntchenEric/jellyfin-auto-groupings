import pytest
from unittest.mock import MagicMock, patch
import requests

import trakt
from trakt import (
    fetch_trakt_list,
    _parse_trakt_list_url,
    _build_trakt_headers,
    _fetch_trakt_page,
    _extract_imdb_ids_from_page,
)


def test_parse_trakt_list_url_valid():
    url = "[https://trakt.tv/users/john_doe/lists/favorite-movies](https://trakt.tv/users/john_doe/lists/favorite-movies)"
    username, slug = _parse_trakt_list_url(url)
    assert username == "john_doe"
    assert slug == "favorite-movies"

    shorthand = "john_doe/favorite-movies"
    username, slug = _parse_trakt_list_url(shorthand)
    assert username == "john_doe"
    assert slug == "favorite-movies"


def