import sys
import os

class JellyfinClient:
    def __init__(self, base_url, api_key):
        self.base_url = base_url
        self.api_key = api_key
        self.headers = {"X-Emby-Token": api_key}

    def get_movies(self):
        import requests
        response = requests.get(f"{self.base_url}/Items", headers=self.headers)
        response.raise_for_status()
        return response.json().get("Items", [])

def group_movies_by_tag(movies):
    groups = {}
    for m in movies:
        mid = m.get("Id")
        if not mid:
            continue
        for tag in m.get("Tags", []):
            if tag.startswith("Group:"):
                gname = tag.split(":", 1)[1]
                groups.setdefault(gname, []).append(mid)
    return groups

def group_movies_by_genre(movies, min_count=1):
    genre_counts = {}
    genre_movies = {}
    for m in movies:
        mid = m.get("Id")
        if not mid:
            continue
        for genre in m.get("Genres", []):
            genre_movies.setdefault(genre, []).append(mid)
    return {g: ids for g, ids in genre_movies.items() if len(ids) >= min_count}

def main():
    print("Jellyfin Groupings CLI")
