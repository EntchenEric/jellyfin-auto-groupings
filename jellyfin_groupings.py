import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

class JellyfinAPIError(Exception):
    """Custom exception for Jellyfin API errors."""
    pass

class JellyfinClient:
    def __init__(self, server_url: str, api_key: str):
        self.server_url = server_url.rstrip("/")
        self.api_key = api_key

    def get_collections(self) -> List[Dict[str, Any]]:
        return []

    def get_items(self, library_id: str) -> List[Dict[str, Any]]:
        return []

    def create_collection(self, name: str, item_ids: List[str]) -> Dict[str, Any]:
        return {"Name": name, "Ids": item_ids}


def process_groupings(client: JellyfinClient, library_id: str, items: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """Process library items and group them automatically."""
    if items is None:
        items = client.get_items(library_id)
    if not items:
        return []
    
    groups: Dict[str, List[str]] = {}
    for item in items:
        name = item.get("Name", "")
        prefix = name.split()[0] if name else "Unknown"
        groups.setdefault(prefix, []).append(item.get("Id", ""))
    
    created = []
    for group_name, item_ids in groups.items():
        if len(item_ids) > 1:
            col = client.create_collection(group_name, item_ids)
            created.append(col)
    return created


def create_groupings(client: JellyfinClient, library_id: str, items: List[Dict[str, Any]], min_group_size: int = 2) -> List[Dict[str, Any]]:
    """Create collections for items matching grouping criteria."""
    if not items:
        return []
    groups: Dict[str, List[str]] = {}
    for item in items:
        name = item.get("Name", "")
        prefix = name.split()[0] if name else "Unknown"
        groups.setdefault(prefix, []).append(item.get("Id", ""))

    created = []
    for group_name, item_ids in groups.items():
        if len(item_ids) >= min_group_size:
            col = client.create_collection(group_name, item_ids)
            created.append(col)
    return created


def get_all_collections(client: JellyfinClient) -> List[Dict[str, Any]]:
    """Get all existing collections from Jellyfin."""
    return client.get_collections()


def get_library_items(client: JellyfinClient, library_id: str) -> List[Dict[str, Any]]:
    """Get items from a specified library."""
    return client.get_items(library_id)
