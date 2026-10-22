"""Tests for external metadata providers (Anilist, Trakt, Mal, TMDB, Letterboxd, IMDB)."""

from unittest.mock import MagicMock, patch

import pytest

import _common
import anilist
import imdb
import letterboxd
import mal
import tmdb
import trakt


def test_anilist_fetch():
    with patch("anilist.network.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": {
                "MediaListCollection": {
                    "lists": [{"name": "Completed", "entries": [{"mediaId": 12345}]}]
                }
            }
        }
        mock_post.return_value = mock_resp
        res = anilist.fetch_anilist_list("testuser")
        assert res == [12345]


def test_trakt_get_headers():
    headers = trakt._build_trakt_headers("test_client_id")
    assert headers.get("trakt-api-key") == "test_client_id"


def test_mal_fetch():
    with patch("mal.network.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": [{"node": {"id": 1, "title": "Test Anime"}}],
            "paging": {},
        }
        mock_get.return_value = mock_resp
        res = mal.fetch_mal_list("testuser", "test_client_id")
        assert res == [1]


# --- _common.py tests ---


def test_normalize_group_relpath():
    assert _common.normalize_group_relpath("Anime/Action") == "Anime/Action"
    assert _common.normalize_group_relpath("  Anime // Action  ") == "Anime/Action"
    assert _common.normalize_group_relpath("Anime\\Action") == "Anime/Action"
    assert _common.normalize_group_relpath("../outside") is None
    assert _common.normalize_group_relpath(".") is None
    assert _common.normalize_group_relpath("C:\\Windows\\System32") is None
    assert _common.normalize_group_relpath("") is None
    assert _common.normalize_group_relpath(None) is None
    assert _common.normalize_group_relpath("Test\x00Null") is None


# --- tmdb.py tests ---


def test_tmdb_fetch_list():
    with patch("tmdb.network.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "items": [{"id": 101}, {"id": 102}],
            "total_pages": 1,
        }
        mock_get.return_value = mock_resp
        ids = tmdb.fetch_tmdb_list("12345", "fake_api_key")
        assert ids == ["101", "102"]


def test_tmdb_fetch_list_validation():
    with pytest.raises(ValueError):
        tmdb.fetch_tmdb_list("12345", "")
    with pytest.raises(ValueError):
        tmdb.fetch_tmdb_list("", "fake_key")


def test_tmdb_recommendations():
    with patch("tmdb.network.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"results": [{"id": 201}, {"id": 202}]}
        mock_get.return_value = mock_resp
        recs = tmdb.get_tmdb_recommendations([("101", "movie")], "fake_api_key")
        assert recs == ["201", "202"]


# --- imdb.py tests ---


def test_imdb_fetch_list():
    with patch("imdb.network.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '<html><a href="/title/tt1234567/">Movie</a></html>'
        mock_get.return_value = mock_resp
        ids = imdb.fetch_imdb_list("ls0000000")
        assert ids == ["tt1234567"]


def test_imdb_fetch_list_invalid():
    with pytest.raises(ValueError):
        imdb.fetch_imdb_list("")


# --- letterboxd.py tests ---


def test_letterboxd_fetch_list():
    with patch("letterboxd.network.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = (
            '<html><div data-film-slug="test-movie" data-tmdb-id="12345"></div></html>'
        )
        mock_get.return_value = mock_resp
        res = letterboxd.fetch_letterboxd_list(
            "https://letterboxd.com/user/list/test-list/"
        )
        assert res == ["12345"]


# Real Letterboxd markup wraps a film's attributes over several lines, and each
# film block is preceded by attributes of its own. Non-DOTALL patterns silently
# found nothing there, so every film fell back to an extra HTTP request.
_MULTILINE_LIST_HTML = """
<ul>
  <li class="poster-container">
    <div class="film-poster" data-film-slug="the-godfather"
         data-film-id="1">
      <a href="https://www.themoviedb.org/movie/238/">x</a>
    </div>
  </li>
  <li class="poster-container">
    <div class="film-poster" data-film-slug="parasite-2019"
         data-tmdb-id="496243"></div>
  </li>
  <li class="poster-container">
    <div class="film-poster" data-film-slug="imdb-only">
      <a href="https://www.imdb.com/title/tt0111161/">x</a>
    </div>
  </li>
</ul>
"""


def test_letterboxd_extract_ids_multiline_markup():
    found = letterboxd._extract_ids_from_list_page(_MULTILINE_LIST_HTML)
    assert found == {
        "the-godfather": "238",
        "parasite-2019": "496243",
        "imdb-only": "tt0111161",
    }


def test_letterboxd_extract_ids_does_not_bleed_between_films():
    html = (
        '<div data-film-slug="no-id-film"></div>'
        '<div data-film-slug="later-film" data-tmdb-id="999"></div>'
    )
    found = letterboxd._extract_ids_from_list_page(html)
    assert "no-id-film" not in found
    assert found == {"later-film": "999"}


def test_letterboxd_extract_ids_prefers_tmdb_attribute_over_links():
    html = (
        '<div data-film-slug="both" data-tmdb-id="555">'
        '<a href="https://www.imdb.com/title/tt0000001/">x</a></div>'
    )
    assert letterboxd._extract_ids_from_list_page(html) == {"both": "555"}


def test_letterboxd_list_page_ids_skip_per_film_fetch():
    with patch("letterboxd.network.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = _MULTILINE_LIST_HTML
        mock_get.return_value = mock_resp
        ids = letterboxd.fetch_letterboxd_list("https://letterboxd.com/u/list/x/")

    assert ids == ["238", "496243", "tt0111161"]
    assert mock_get.call_count == 1, "list-page IDs must not trigger film fetches"


# --- Letterboxd pagination -------------------------------------------------
# Letterboxd writes the next-page control as ``class="next "`` (trailing
# space) and disables it with ``class="next  is-disabled"``. Comparing the
# attribute against the literal ``class="next"`` therefore never matched, and
# every multi-page list was silently cut down to its first page.


def _letterboxd_page(number: int, pagination: str = "") -> str:
    """Build a one-film list page with the given pagination markup."""
    return (
        f'<div data-film-slug="film-{number}" data-tmdb-id="{number}"></div>'
        f"{pagination}"
    )


def _fetch_with_pages(pages: dict[int, str]) -> tuple[list[str], MagicMock]:
    """Serve *pages* by request order and return the fetched IDs and mock."""
    with (
        patch("letterboxd.network.get") as mock_get,
        # Pagination pauses 0.5 s between pages to be polite to Letterboxd;
        # a multi-page test should not spend real time on it.
        patch("letterboxd.time.sleep"),
    ):
        responses = []
        for page in sorted(pages):
            resp = MagicMock()
            resp.status_code = 200
            resp.text = pages[page]
            responses.append(resp)
        mock_get.side_effect = responses
        ids = letterboxd.fetch_letterboxd_list("https://letterboxd.com/u/list/x/")
    return ids, mock_get


def test_letterboxd_paginates_on_class_with_trailing_space():
    """A trailing space in ``class="next "`` must not end pagination."""
    ids, mock_get = _fetch_with_pages(
        {
            1: _letterboxd_page(1, '<a class="next " href="/page/2/">Next</a>'),
            2: _letterboxd_page(2),
        },
    )

    assert ids == ["1", "2"]
    assert mock_get.call_count == 2


def test_letterboxd_paginates_on_class_with_extra_tokens():
    """State classes next to ``next`` must not end pagination either."""
    ids, mock_get = _fetch_with_pages(
        {
            1: _letterboxd_page(1, '<a class="next button" href="/page/2/">Next</a>'),
            2: _letterboxd_page(2),
        },
    )

    assert ids == ["1", "2"]
    assert mock_get.call_count == 2


def test_letterboxd_stops_on_disabled_next_control():
    """A disabled next control marks the last page and must stop the walk."""
    ids, mock_get = _fetch_with_pages(
        {
            1: _letterboxd_page(
                1,
                '<a class="next  is-disabled" href="/page/2/">Next</a>',
            ),
            2: _letterboxd_page(2),
        },
    )

    assert ids == ["1"]
    assert mock_get.call_count == 1


def test_letterboxd_ignores_unrelated_class_containing_next():
    """``class="next-door"`` is not a pagination control."""
    ids, mock_get = _fetch_with_pages(
        {1: _letterboxd_page(1, '<a class="next-door" href="/x/">x</a>')},
    )

    assert ids == ["1"]
    assert mock_get.call_count == 1


def test_letterboxd_pagination_respects_page_limit(caplog):
    """Hitting the page cap is reported instead of looking like the list end."""
    endless = '<a class="next " href="/page/2/">Next</a>'
    pages = {
        page: _letterboxd_page(page, endless)
        for page in range(1, letterboxd._MAX_PAGES + 1)
    }

    with caplog.at_level("WARNING", logger="letterboxd"):
        _, mock_get = _fetch_with_pages(pages)

    assert mock_get.call_count == letterboxd._MAX_PAGES
    assert "safety limit" in caplog.text


def test_letterboxd_disabled_control_beats_rel_next():
    """A disabled next control ends the list even if ``rel="next"`` appears."""
    html = (
        '<a class="next  is-disabled" href="/page/2/" rel="next">Next</a>'
        '<div data-film-slug="only" data-tmdb-id="7"></div>'
    )

    assert letterboxd._has_next_page(html) is False
