# Jellyfin Auto Groupings

Automated script to categorize and group Jellyfin library items into curated collections such as franchises, genres, decades, exact release years, and custom tagged groups.

## Features

- **Special Collections**: Auto-detect franchises like MCU, Star Wars, Harry Potter, Lord of the Rings, and James Bond.
- **Custom Tag Groups**: Create collections based on keyword matching and tags (e.g. Sci-Fi Classics, Oscar Winners, 90s Action).
- **Decade Collections**: Automatically group movies into decade collections (e.g. `2010s Movies`, `1990s Movies`) using `ProductionYear` or `PremiereDate`.
- **Year Collections**: Dynamically group items into year collections (e.g. `Best of 2024`).

## Usage

```python
from jellyfin_groupings import create_groupings

items = [
    {"Name": "Iron Man", "Overview": "MCU origin", "ProductionYear": 2008},
    {"Name": "The Avengers", "Overview": "MCU teamup", "ProductionYear": 2012},
    {"Name": "Avengers: Endgame", "Overview": "MCU finale", "ProductionYear": 2019},
]

groupings = create_groupings(items)
print(groupings)
```

## Running Tests

Run test suite and check code coverage:

```bash
pytest --cov=jellyfin_groupings
```
