import sys
import os
from pathlib import Path

# Ensure root directory is on sys.path so both jellyfin_groupings.py and packages work
root_dir = str(Path(__file__).resolve().parent.parent)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

import jellyfin_groupings as _jg
from jellyfin_groupings.main import JellyfinGroupings, main

JellyfinClient = _jg.JellyfinClient
group_movies_by_genre = _jg.group_movies_by_genre
group_movies_by_tag = _jg.group_movies_by_tag
process_groupings = _jg.process_groupings

__all__ = [
    "JellyfinClient",
    "JellyfinGroupings",
    "group_movies_by_genre",
    "group_movies_by_tag",
    "main",
    "process_groupings",
]
