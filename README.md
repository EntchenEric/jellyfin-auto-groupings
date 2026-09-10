# Jellyfin Auto-Groupings

Automated collection creation and library item grouping tool for Jellyfin media servers.

## Features

- **Automated Collection Grouping**: Automatically groups movies and TV series into Jellyfin collections based on series metadata.
- **REST API Integration**: Interacts directly with Jellyfin API endpoints.
- **Robust Error Handling & Logging**: Uses structured logging and timeout safeguards.
- **Unit Tested**: Full test coverage for core functions using `unittest`.

## Requirements

- Python 3.8+
- `requests`

Install dependencies:
```bash
pip install requests
```

## Usage

```python
import jellyfin_groupings

server_url = "http://localhost:8096"
api_key = "your-api-key"
user_id = "your-user-id"

# Fetch library items
items = jellyfin_groupings.get_library_items(server_url, api_key, user_id)

# Group items into collection mapping
collections = jellyfin_groupings.group_items_by_collection(items)

# Create collection on Jellyfin
for name, group_items in collections.items():
    item_ids = [item["Id"] for item in group_items]
    jellyfin_groupings.create_collection(server_url, api_key, f"{name} Collection", item_ids)
```

## Running Tests

Execute unit tests with Python's built-in `unittest` runner:
```bash
python3 test_jellyfin_groupings.py
```
