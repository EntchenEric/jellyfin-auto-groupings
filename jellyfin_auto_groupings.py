"""Auto-group Jellyfin collections, genres, or tags based on configurable rules."""
import logging
import os
import re
import sys
from typing import Any, Dict, List, Optional, Set, Tuple
import urllib.parse
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("jellyfin-auto-groupings")


class JellyfinClient:
    """Simple Jellyfin API client."""

    def __init__(self, server_url: str, api_key: str, user_id: Optional[str] = None) -> None:
        self.server_url = server_url.rstrip("/")
        self.api_key = api_key
        self.user_id = user_id
        self.headers = {
            "X-Emby-Token": api_key,
            "Content-Type": "application/json",
        }

    def _get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self.server_url}{endpoint}"
        resp = requests.get(url, headers=self.headers, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _post(self, endpoint: str, params: Optional[Dict[str, Any]] = None, json_data: Optional[Any] = None) -> Any:
        url = f"{self.server_url}{endpoint}"
        resp = requests.post(url, headers=self.headers, params=params, json=json_data, timeout=30)
        resp.raise_for_status()
        if resp.text:
            try:
                return resp.json()
            except ValueError:
                return resp.text
        return None

    def _delete(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> None:
        url = f"{self.server_url}{endpoint}"
        resp = requests.delete(url, headers=self.headers, params=params, timeout=30)
        resp.raise_for_status()

    def get_users(self) -> List[Dict[str, Any]]:
        """Get list of users."""
        return self._get("/Users")

    def get_first_admin_user_id(self) -> str:
        """Get the ID of the first admin user."""
        users = self.get_users()
        for u in users:
            if u.get("Policy", {}).get("IsAdministrator"):
                return u["Id"]
        if users:
            return users[0]["Id"]
        raise RuntimeError("No users found on Jellyfin server.")

    def get_all_items(self, item_types: Optional[List[str]] = None, parent_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all items matching item_types."""
        uid = self.user_id or self.get_first_admin_user_id()
        params = {
            "Recursive": "true",
            "Fields": "Genres,Tags,CollectionFolder,ProviderIds",
        }
        if item_types:
            params["IncludeItemTypes"] = ",".join(item_types)
        if parent_id:
            params["ParentId"] = parent_id

        res = self._get(f"/Users/{uid}/Items", params=params)
        return res.get("Items", [])

    def create_collection(self, name: str, item_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """Create a collection with given name and initial item IDs."""
        params = {"Name": name}
        if item_ids:
            params["Ids"] = ",".join(item_ids)
        return self._post("/Collections", params=params)

    def add_to_collection(self, collection_id: str, item_ids: List[str]) -> None:
        """Add items to an existing collection."""
        params = {"Ids": ",".join(item_ids)}
        self._post(f"/Collections/{collection_id}/Items", params=params)

    def remove_from_collection(self, collection_id: str, item_ids: List[str]) -> None:
        """Remove items from a collection."""
        params = {"Ids": ",".join(item_ids)}
        self._delete(f"/Collections/{collection_id}/Items", params=params)


def group_items_by_pattern(
    items: List[Dict[str, Any]], pattern: str, attribute: str = "Name"
) -> Dict[str, List[Dict[str, Any]]]:
    """Group items based on a regex pattern extract from an attribute."""
    groups: Dict[str, List[Dict[str, Any]]] = {}
    regex = re.compile(pattern, re.IGNORECASE)
    for item in items:
        val = item.get(attribute, "")
        if isinstance(val, list):
            vals = val
        else:
            vals = [val]

        for v in vals:
            if not isinstance(v, str):
                continue
            match = regex.search(v)
            if match:
                # If regex has capture groups, use group 1, else use full match
                group_key = match.group(1) if match.groups() else match.group(0)
                group_key = group_key.strip()
                if group_key:
                    groups.setdefault(group_key, []).append(item)
                    break  # Matched once for this item
    return groups


def sync_groupings(
    client: JellyfinClient,
    groups: Dict[str, List[Dict[str, Any]]],
    dry_run: bool = True,
    min_items: int = 1,
) -> Dict[str, List[str]]:
    """Sync calculated groups with Jellyfin collections."""
    summary: Dict[str, List[str]] = {}

    # Get existing collections
    existing_collections = client.get_all_items(item_types=["BoxSet"])
    collection_map = {c["Name"]: c["Id"] for c in existing_collections}

    for group_name, items in groups.items():
        if len(items) < min_items:
            logger.info(f"Skipping group '{group_name}' because it has fewer than {min_items} items ({len(items)})")
            continue

        item_ids = [item["Id"] for item in items]
        summary[group_name] = item_ids

        if group_name in collection_map:
            coll_id = collection_map[group_name]
            logger.info(f"[Existing Collection] '{group_name}' ID: {coll_id}. Target items count: {len(item_ids)}")
            if not dry_run:
                client.add_to_collection(coll_id, item_ids)
        else:
            logger.info(f"[New Collection] '{group_name}'. Target items count: {len(item_ids)}")
            if not dry_run:
                client.create_collection(group_name, item_ids)

    return summary
