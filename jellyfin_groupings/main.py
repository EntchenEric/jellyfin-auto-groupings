from .client import JellyfinClient
from .groupings import group_movies_by_tag, group_movies_by_genre

class JellyfinGroupings:
    def __init__(self, *args, **kwargs):
        pass

__all__ = ["JellyfinGroupings", "main", "JellyfinClient", "group_movies_by_tag", "group_movies_by_genre"]
