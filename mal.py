"""
mal.py – MyAnimeList API client for fetching user lists.
"""

from __future__ import annotations

import requests
from typing import Any

MAL_API_BASE_URL = "https://api.myanimelist.net/v2"

def fetch_mal_list(username: str, client_id: str, status: str | None = None) -> list[int]:
    """
    Fetch anime IDs from a user's MyAnimeList profile.
    
    Args:
        username: The MAL username.
        client_id: The MAL API Client ID.
        status: The list status to fetch (e.g., "watching", "completed", "on_hold", "dropped", "plan_to_watch").
                If None, all lists are fetched.
                
    Returns:
        A list of MyAnimeList anime IDs (integers).
    """
    if not client_id:
        raise ValueError("MyAnimeList Client ID is required.")

    # Status normalization if needed. MAL expects these exact strings:
    # watching, completed, on_hold, dropped, plan_to_watch
    # We'll assume the input matches or we'll map common variants.
    valid_statuses = {"watching", "completed", "on_hold", "dropped", "plan_to_watch"}
    normalized_status = None
    if status:
        s = status.lower().replace(" ", "_").replace("-", "_")
        if s == "current":
            normalized_status = "watching"
        elif s == "planning":
            normalized_status = "plan_to_watch"
        elif s == "paused":
            normalized_status = "on_hold"
        elif s in valid_statuses:
            normalized_status = s
        elif status.upper() == "ALL":
            normalized_status = None
        else:
            normalized_status = s # Fallback to whatever user typed

    url = f"{MAL_API_BASE_URL}/users/{username}/animelist"
    params: dict[str, Any] = {
        "fields": "id",
        "limit": 100,
    }
    if normalized_status:
        params["status"] = normalized_status

    headers = {
        "X-MAL-CLIENT-ID": client_id
    }

    ids = []
    
    while url:
        response = requests.get(url, params=params, headers=headers, timeout=15)
        response.raise_for_status()
        
        data = response.json()
        for entry in data.get("data", []):
            node = entry.get("node", {})
            if node.get("id"):
                ids.append(node["id"])
        
        # MAL pagination uses a 'next' URL in the 'paging' object
        url = data.get("paging", {}).get("next")
        # Once we have the 'next' URL, params are already included in it by MAL
        params = {} 

    return ids
