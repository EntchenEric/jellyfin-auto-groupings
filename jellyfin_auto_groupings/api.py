from typing import Any, Dict, List

import requests


class JellyfinAPI:
    """Wrapper client for Jellyfin REST API."""

    def __init__(self, server_url: str, api_key: str, timeout: int = 30) -> None:
        self.server_url = server_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def _get_headers(self) -> Dict[str, str]:
        return {
            "X-Emby-Token": self.api_key,
            "Content-Type": "application/json",
        }

    def get_collections(self) -> List[Dict[str, Any]]:
        """Fetch all boxset/collection items from Jellyfin."""
        url = f"{self.server_url}/Items"
        params = {
            "IncludeItemTypes": "BoxSet",
            "Recursive": "true",
        }
        res = requests.get(url, headers=self._get_headers(), params=params, timeout=self.timeout)
        res.raise_for_status()
        data = res.json()
        return data.get("Items", [])

    def get_collection_items(self, collection_id: str) -> List[Dict[str, Any]]:
        """Fetch items belonging to a given collection."""
        url = f"{self.server_url}/Items"
        params = {
            "ParentId": collection_id,
            "Recursive": "true",
        }
        res = requests.get(url, headers=self._get_headers(), params=params, timeout=self.timeout)
        res.raise_for_status()
        data = res.json()
        return data.get("Items", [])
