import logging
import os
import sys
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


class JellyfinAPIError(Exception):
    """Custom exception for Jellyfin API errors."""
    pass


class JellyfinClient:
    def __init__(self, server_url: str, api_key: str, user_id: Optional[str] = None):
        self.server_url = server_url.rstrip("/")
        self.api_key = api_key
        self.user_id = user_id
        self.session = requests.Session()
        self.session.headers.update({
            "X-Emby-Token": self.api_key,
            "Content-Type": "application/json",
        })

    def get_users(self) -> List[Dict[str, Any]]:
        url = f"{self.server_url}/Users"
        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException:
            return []

    def get_first_admin_user_id(self) -> Optional[str]:
        users = self.get_users()
        if not users:
            return None
        for u in users:
            if u.get("Policy", {}).get("IsAdministrator"):
                return u.get("Id")
        return users[0].get("Id")

    def get_collections(self) -> List[Dict[str, Any]]:
        url = f"{self.server_url}/Items?IncludeItemTypes=BoxSet&Recursive=true"
        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            return data.get("Items", [])
        except requests.RequestException:
            return []

    def get_collection_items(self, collection_id: str) -> List[Dict[str, Any]]:
        url = f"{self.server_url}/Items?ParentId={collection_id}&Recursive=true"
        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            return data.get("Items", [])
        except requests.RequestException:
            return []

    def get_movies(self) -> List[Dict[str, Any]]:
        uid = self.user_id or self.get_first_admin_user_id()
        if not uid:
            return []
        url = f"{self.server_url}/Users/{uid}/Items?IncludeItemTypes=Movie&Recursive=true"
        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            return data.get("Items", [])
        except requests.RequestException:
            return []

    def get_items(self, library_id: Optional[str] = None) -> List[Dict[str, Any]]:
        return self.get_movies()

    def create_collection(self, name: str, item_ids: List[str]) -> Optional[Dict[str, Any]]:
        if not item_ids:
            return None
        url = f"{self.server_url}/Collections?Name={name}&Ids={",".join(item_ids)}"
        try:
            resp = self.session.post(url, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException:
            return None

    def update_item_sort_name(self, item_id: str, sort_name: str) -> None:
        url = f"{self.server_url}/Items/{item_id}"
        try:
            self.session.post(url, json={"ForcedSortName": sort_name}, timeout=30)
        except requests.RequestException:
            pass


def group_movies_by_tag(movies: List[Dict[str, Any]], tag_prefix: str = "Group:") -> Dict[str, List[str]]:
    groups: Dict[str, List[str]] = {}
    for movie in movies:
        item_id = movie.get("Id")
        if not item_id:
            continue
        for tag in movie.get("Tags", []):
            if tag.startswith(tag_prefix):
                group_name = tag[len(tag_prefix):].strip()
                if group_name:
                    groups.setdefault(group_name, []).append(item_id)
    return groups


def group_movies_by_genre(movies: List[Dict[str, Any]], min_count: int = 1) -> Dict[str, List[str]]:
    groups: Dict[str, List[str]] = {}
    for movie in movies:
        item_id = movie.get("Id")
        if not item_id:
            continue
        for genre in movie.get("Genres", []):
            groups.setdefault(genre, []).append(item_id)
    return {g: ids for g, ids in groups.items() if len(ids) >= min_count}


def process_groupings(client: JellyfinClient, dry_run: bool = True) -> List[tuple]:
    collections = client.get_collections()
    changes = []
    for col in collections:
        col_name = col.get("Name", "Collection")
        items = client.get_collection_items(col.get("Id", ""))
        sorted_items = sorted(items, key=lambda x: x.get("PremiereDate", ""))
        for idx, item in enumerate(sorted_items, start=1):
            expected_sort_name = f"{col_name} {idx:02d}"
            current_sort = item.get("ForcedSortName", "")
            if current_sort != expected_sort_name:
                changes.append((item.get("Id"), item.get("Name"), expected_sort_name))
                if not dry_run:
                    client.update_item_sort_name(item.get("Id"), expected_sort_name)
    return changes


def main() -> None:
    api_key = os.environ.get("JELLYFIN_API_KEY")
    if not api_key:
        print("Error: JELLYFIN_API_KEY environment variable is required.")
        sys.exit(1)
    url = os.environ.get("JELLYFIN_URL", "http://localhost:8096")
    client = JellyfinClient(url, api_key)
    movies = client.get_movies()
    groups = group_movies_by_tag(movies)
    for group_name, item_ids in groups.items():
        client.create_collection(group_name, item_ids)


if __name__ == "__main__":
    main()
