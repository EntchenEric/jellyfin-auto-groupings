# Jellyfin Auto Groupings

Automated library item grouping and collection management for Jellyfin media servers.

## Features
- Fetch and manage collections (`BoxSet` items).
- Automated grouping workflow.
- Configurable API timeouts and logging.

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `JELLYFIN_URL` | Base URL of your Jellyfin server (e.g., `http://localhost:8096`) | None |
| `JELLYFIN_API_KEY` | Valid API key generated in Jellyfin Dashboard | None |

## Usage

```python
from main import JellyfinGroupings

# Initialize with environment variables or explicit parameters
jg = JellyfinGroupings(server_url="http://localhost:8096", api_key="your_api_key")
result = jg.auto_group()
print(result)
```

## Running Tests

Run test suite using `pytest`:

```bash
pytest
```
