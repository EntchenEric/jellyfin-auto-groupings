import logging
from typing import Any, Dict, List, Optional
import requests

logger = logging.getLogger(__name__)


class JellyfinClient:
    def __init__(self, server_url: str, api_key: str, user_id: Optional[str] = None):
        self.server_url = server_url.rstrip("/")
        self.base_url = self.server_url
        self.api_key = api_key
        self.user_id = user_id
        self.headers = {
            "X-Emby-Token": self.api_key,
            "Content-Type": "application/json",
        }

    def get_movies(self) -> List[Dict[str, Any]]:
        url = f"{self.server_url}/Items"
        params = {"IncludeItemTypes": "Movie", "Recursive": "true"}
        resp = requests.get(url, headers=self.headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data.get("Items", [])

    def create_collection(self, name: str, item_ids: List[str]) -> Dict[str, Any]:
        url = f"{self.server_url}/Collections"
        params = {"Name": name, "Ids": ",".join(item_ids)}
        resp = requests.post(url, headers=self.headers, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
