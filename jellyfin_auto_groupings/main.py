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


def create_groupings(client_or_items: Any, library_id: Optional[str] = None, items: Optional[List[Dict[str, Any]]] = None, min_group_size: int = 2) -> Any:
    """Create collections or grouping mapping for items matching criteria."""
    if isinstance(client_or_items, list) and library_id is None:
        # Called as create_groupings(items)
        sample_items = client_or_items
        res: Dict[str, List[Dict[str, Any]]] = {}
        mcu = get_movies_by_query(sample_items, "MCU")
        if mcu:
            res["Marvel Cinematic Universe"] = mcu
        sw = get_movies_by_query(sample_items, "Star Wars")
        if sw:
            res["Star Wars Collection"] = sw
        scifi = get_movies_by_query(sample_items, "Sci-Fi", tags=["sci-fi", "classic"])
        if scifi:
            res["Sci-Fi Classics"] = scifi
        decades = get_decade_groups(sample_items)
        res.update(decades)
        return res

    # Called as create_groupings(client, library_id, items, min_group_size)
    client = client_or_items
    items = items or []
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


def get_decade_groups(items: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Group items by decade based on ProductionYear or PremiereDate."""
    decades: Dict[str, List[Dict[str, Any]]] = {}
    for item in items:
        year = item.get("ProductionYear")
        if not year and item.get("PremiereDate"):
            date_str = str(item.get("PremiereDate"))
            if len(date_str) >= 4 and date_str[:4].isdigit():
                year = int(date_str[:4])
        if year:
            decade = (year // 10) * 10
            key = f"{decade}s Movies"
            decades.setdefault(key, []).append(item)
    return decades


def get_year_groups(items: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Group items by release year."""
    years: Dict[str, List[Dict[str, Any]]] = {}
    for item in items:
        year = item.get("ProductionYear")
        if not year and item.get("PremiereDate"):
            date_str = str(item.get("PremiereDate"))
            if len(date_str) >= 4 and date_str[:4].isdigit():
                year = int(date_str[:4])
        if year:
            key = f"Best of {year}"
            years.setdefault(key, []).append(item)
    return years


def get_movies_by_query(items: List[Dict[str, Any]], query: str, tags: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Filter items matching a query string in Name/Overview and optional tags."""
    matching = []
    query_lower = query.lower()
    for item in items:
        name = str(item.get("Name", "")).lower()
        overview = str(item.get("Overview", "")).lower()
        item_tags = [t.lower() for t in item.get("Tags", [])]
        if query_lower in name or query_lower in overview:
            if tags:
                if all(t.lower() in item_tags for t in tags):
                    matching.append(item)
            else:
                matching.append(item)
    return matching


def group_movies_by_tag(items: List[Dict[str, Any]], min_group_size: int = 2) -> Dict[str, List[Dict[str, Any]]]:
    """Group items by tag."""
    tag_groups: Dict[str, List[Dict[str, Any]]] = {}
    for item in items:
        for tag in item.get("Tags", []):
            tag_groups.setdefault(tag, []).append(item)
    return {tag: val for tag, val in tag_groups.items() if len(val) >= min_group_size}


def group_movies_by_genre(items: List[Dict[str, Any]], min_group_size: int = 2) -> Dict[str, List[Dict[str, Any]]]:
    """Group items by genre."""
    genre_groups: Dict[str, List[Dict[str, Any]]] = {}
    for item in items:
        for genre in item.get("Genres", []):
            genre_groups.setdefault(genre, []).append(item)
    return {genre: val for genre, val in genre_groups.items() if len(val) >= min_group_size}
