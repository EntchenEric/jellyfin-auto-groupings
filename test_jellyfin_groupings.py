import pytest
from jellyfin_groupings import (
    create_groupings,
    get_decade_groups,
    get_movies_by_query,
    get_year_groups,
)


@pytest.fixture
def sample_items():
    return [
        {
            "Name": "Iron Man",
            "Overview": "An MCU superhero origin story",
            "ProductionYear": 2008,
            "Tags": ["mcu", "action"],
        },
        {
            "Name": "The Avengers",
            "Overview": "Earth's mightiest heroes in MCU",
            "ProductionYear": 2012,
            "Tags": ["mcu", "action"],
        },
        {
            "Name": "Avengers: Endgame",
            "Overview": "The epic MCU finale",
            "ProductionYear": 2019,
            "Tags": ["mcu", "action"],
        },
        {
            "Name": "Star Wars: A New Hope",
            "Overview": "A long time ago...",
            "ProductionYear": 1977,
            "Tags": ["sci-fi", "classic"],
        },
        {
            "Name": "Star Wars: Empire Strikes Back",
            "Overview": "The Empire strikes back",
            "ProductionYear": 1980,
            "Tags": ["sci-fi", "classic"],
        },
        {
            "Name": "Sci-Fi Classic Movie 1",
            "Overview": "A great Sci-Fi classic",
            "ProductionYear": 1995,
            "Tags": ["sci-fi", "classic"],
        },
        {
            "Name": "Sci-Fi Classic Movie 2",
            "Overview": "Another Sci-Fi classic",
            "PremiereDate": "1998-05-12T00:00:00Z",
            "Tags": ["sci-fi", "classic"],
        },
        {
            "Name": "Random Movie",
            "Overview": "Just a movie",
            "PremiereDate": "invalid-date",
            "Tags": [],
        },
    ]


def test_get_movies_by_query(sample_items):
    mcu_movies = get_movies_by_query(sample_items, "MCU")
    assert len(mcu_movies) == 3


def test_get_movies_by_query_with_tags(sample_items):
    scifi_classics = get_movies_by_query(
        sample_items, "Sci-Fi", tags=["sci-fi", "classic"]
    )
    assert len(scifi_classics) == 2


def test_get_decade_groups(sample_items):
    decades = get_decade_groups(sample_items)
    assert "2000s Movies" in decades
    assert "2010s Movies" in decades
    assert "1970s Movies" in decades
    assert "1990s Movies" in decades
    assert len(decades["2010s Movies"]) == 2


def test_get_year_groups(sample_items):
    years = get_year_groups(sample_items)
    # 2008, 2012, 2019, 1977, 1980, 1995, 1998 each have 1 movie
    assert "Best of 2008" in years
    assert len(years["Best of 2008"]) == 1


def test_create_groupings(sample_items):
    groups = create_groupings(sample_items)
    assert "Marvel Cinematic Universe" in groups
    assert "Star Wars Collection" in groups
    assert "Sci-Fi Classics" in groups
    assert "2010s Movies" in groups
