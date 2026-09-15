import logging
import re
from typing import Any, Dict, List, Optional, Union
import requests

logger = logging.getLogger(__name__)


class JellyfinAPIError(Exception):
    """Exception raised for Jellyfin API errors."""
    pass


class JellyfinClient:
    def __init__(self, server_url: str, api_key: str, user_id: Optional[str] = None):
        self.server_url = server_url.rstrip("/")
        self.api_key = api_key
        self.user_id = user_id
        self.session = requests.Session()
        self.headers = {
            "X-Emby-Token": self.api_key,
            "Content-Type": "application/json",
        }
        self.session.headers.update(self.headers)

    def _get(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
        url = f"{self.server_url}{endpoint}"
        try:
            resp = requests.get(url, headers=self.headers, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.error(f"Error fetching {url}: {e}")
            raise

    def _post(self, endpoint: str, params: Optional[Dict[str, Any]] = None, data: Optional[Dict[str, Any]] = None) -> Any:
        url = f"{self.server_url}{endpoint}"
        try:
            resp = requests.post(url, headers=self.headers, params=params, json=data, timeout=30)
            resp.raise_for_status()
            if not resp.text.strip():
                return None
            try:
                return resp.json()
            except ValueError:
                return resp.text
        except requests.RequestException as e:
            logger.error(f"Error posting to {url}: {e}")
            raise

    def _delete(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
        url = f"{self.server_url}{endpoint}"
        try:
            resp = requests.delete(url, headers=self.headers, params=params, timeout=30)
            resp.raise_for_status()
            if not resp.text.strip():
                return None
            try:
                return resp.json()
            except ValueError:
                return resp.text
        except requests.RequestException as e:
            logger.error(f"Error deleting {url}: {e}")
            raise

    def get_users(self) -> List[Dict[str, Any]]:
        return self._get("/Users")

    def get_first_admin_user_id(self) -> str:
        users = self.get_users()
        if not users:
            raise RuntimeError("No users found on the Jellyfin server.")
        for u in users:
            if u.get("Policy", {}).get("IsAdministrator"):
                return u["Id"]
        return users[0]["Id"]

    def get_all_items(self, item_types: Optional[List[str]] = None, parent_id: Optional[str] = None) -> List[Dict[str, Any]]:
        if not self.user_id:
            self.user_id = self.get_first_admin_user_id()
        params = {
            "Recursive": "true",
            "Fields": "Tags,Genres,ProductionYear,PremiereDate,Overview",
        }
        if item_types:
            params["IncludeItemTypes"] = ",".join(item_types)
        if parent_id:
            params["ParentId"] = parent_id
        data = self._get(f"/Users/{self.user_id}/Items", params=params)
        return data.get("Items", [])

    def get_items(self, library_id: Optional[str] = None) -> List[Dict[str, Any]]:
        try:
            if not self.user_id:
                self.user_id = self.get_first_admin_user_id()
            params = {
                "Recursive": "true",
                "Fields": "Tags,Genres,ProductionYear,PremiereDate,Overview",
            }
            if library_id:
                params["ParentId"] = library_id
            endpoint = f"/Users/{self.user_id}/Items"
            data = self._get(endpoint, params=params)
            return data.get("Items", [])
        except Exception as e:
            raise JellyfinAPIError(f"API request GET /Items failed: {e}") from e

    def get_collections(self) -> List[Dict[str, Any]]:
        return self.get_all_items(item_types=["BoxSet"])

    def get_collection_items(self, collection_id: str) -> List[Dict[str, Any]]:
        return self.get_all_items(parent_id=collection_id)

    def get_movies(self) -> List[Dict[str, Any]]:
        return self.get_all_items(item_types=["Movie"])

    def create_collection(self, name: str, item_ids: List[str]) -> Dict[str, Any]:
        if not item_ids:
            return {}
        params = {
            "Name": name,
            "Ids": ",".join(item_ids),
        }
        res = self._post("/Collections", params=params)
        return res if isinstance(res, dict) else {"Id": str(res)}

    def add_to_collection(self, collection_id: str, item_ids: List[str]) -> Dict[str, Any]:
        if not item_ids:
            return {}
        params = {"Ids": ",".join(item_ids)}
        res = self._post(f"/Collections/{collection_id}/Items", params=params)
        return res if isinstance(res, dict) else {}

    def remove_from_collection(self, collection_id: str, item_ids: List[str]) -> Dict[str, Any]:
        if not item_ids:
            return {}
        params = {"Ids": ",".join(item_ids)}
        res = self._delete(f"/Collections/{collection_id}/Items", params=params)
        return res if isinstance(res, dict) else {}

    def update_item_sort_name(self, item_id: str, sort_name: str) -> None:
        url = f"{self.server_url}/Items/{item_id}"
        try:
            self.session.post(url, json={"ForcedSortName": sort_name}, timeout=30)
        except Exception:
            pass


def group_items_by_pattern(
    items: List[Dict[str, Any]],
    pattern: str,
    attribute: str = "Name"
) -> Dict[str, List[Dict[str, Any]]]:
    compiled = re.compile(pattern, re.IGNORECASE)
    groups: Dict[str, List[Dict[str, Any]]] = {}

    for item in items:
        val = item.get(attribute)
        if isinstance(val, list):
            target_vals = [str(x) for x in val]
        elif val is not None:
            target_vals = [str(val)]
        else:
            continue

        for target in target_vals:
            match = compiled.search(target)
            if match:
                group_name = match.group(1) if match.groups() else match.group(0)
                group_name = group_name.strip()
                if group_name:
                    groups.setdefault(group_name, []).append(item)
                break
    return groups


def sync_groupings(
    client: JellyfinClient,
    groups: Dict[str, List[Dict[str, Any]]],
    dry_run: bool = False,
    min_items: int = 1
) -> Dict[str, List[str]]:
    summary: Dict[str, List[str]] = {}
    existing_collections = {
        col["Name"]: col["Id"]
        for col in client.get_all_items(item_types=["BoxSet"])
        if "Name" in col and "Id" in col
    }

    for group_name, items in groups.items():
        if len(items) < min_items:
            continue
        item_ids = [str(item["Id"]) for item in items if "Id" in item]
        if not item_ids:
            continue

        summary[group_name] = item_ids

        if dry_run:
            logger.info(f"[DRY-RUN] Would sync {len(item_ids)} items to collection '{group_name}'")
            continue

        if group_name in existing_collections:
            col_id = existing_collections[group_name]
            logger.info(f"Adding {len(item_ids)} items to existing collection '{group_name}' ({col_id})")
            client.add_to_collection(col_id, item_ids)
        else:
            logger.info(f"Creating collection '{group_name}' with {len(item_ids)} items")
            client.create_collection(group_name, item_ids)

    return summary


def get_decade_groups(items: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
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
    tag_groups: Dict[str, List[Dict[str, Any]]] = {}
    for item in items:
        for tag in item.get("Tags", []):
            tag_groups.setdefault(tag, []).append(item)
    return {tag: val for tag, val in tag_groups.items() if len(val) >= min_group_size}


def group_movies_by_genre(items: List[Dict[str, Any]], min_group_size: int = 2) -> Dict[str, List[Dict[str, Any]]]:
    genre_groups: Dict[str, List[Dict[str, Any]]] = {}
    for item in items:
        for genre in item.get("Genres", []):
            genre_groups.setdefault(genre, []).append(item)
    return {genre: val for genre, val in genre_groups.items() if len(val) >= min_group_size}


def process_groupings(client: Any, library_id: Any = None, items: Optional[List[Dict[str, Any]]] = None, dry_run: bool = True) -> Any:
    if hasattr(client, "get_collection_items"):
        collections = client.get_collections() if hasattr(client, "get_collections") else []
        changes = []
        for col in collections:
            col_name = col.get("Name", "Collection")
            col_items = client.get_collection_items(col.get("Id", ""))
            sorted_items = sorted(col_items, key=lambda x: x.get("PremiereDate", ""))
            for idx, item in enumerate(sorted_items, start=1):
                expected_sort_name = f"{col_name} {idx:02d}"
                current_sort = item.get("ForcedSortName", "")
                if current_sort != expected_sort_name:
                    changes.append((item.get("Id"), item.get("Name"), expected_sort_name))
                    if not dry_run and hasattr(client, "update_item_sort_name"):
                        client.update_item_sort_name(item.get("Id"), expected_sort_name)
        if changes or not isinstance(library_id, str):
            return changes

    if isinstance(client, JellyfinClient):
        if items is None and isinstance(library_id, str) and library_id:
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
    return {}


def create_groupings(
    client_or_items: Any,
    library_id: Optional[str] = None,
    items: Optional[List[Dict[str, Any]]] = None,
    min_group_size: int = 2
) -> Any:
    if isinstance(client_or_items, list) and library_id is None:
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
