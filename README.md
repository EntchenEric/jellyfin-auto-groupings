# Jellyfin Auto-Groupings

Automatically create and manage Jellyfin collections (groupings) based on metadata rules such as **genres**, **studios**, and **directors**.

## Features

- Automatic genre collection creation based on configurable item threshold count.
- Automatic studio collection creation for studios with multiple titles.
- Automatic director collection creation for directors with multiple titles.
- Full type hints and error handling.
- Unit test suite included.

## Configuration

Set the following environment variables before running:

| Variable | Description | Required | Default |
| --- | --- | --- | --- |
| `JELLYFIN_URL` | Base URL of your Jellyfin server | No | `http://localhost:8096` |
| `JELLYFIN_API_KEY` | API Key generated in Jellyfin Admin dashboard | **Yes** | N/A |
| `JELLYFIN_USER_ID` | Jellyfin User ID (optional) | No | None |

## Usage

```bash
export JELLYFIN_URL="http://jellyfin.local:8096"
export JELLYFIN_API_KEY="your_api_key_here"

python3 jellyfin_groupings.py
```

## Running Tests

```bash
python3 -m unittest discover
```
