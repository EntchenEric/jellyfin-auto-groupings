import sys
import os

# Ensure root directory is on sys.path for top-level module access
_root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root_dir not in sys.path:
    sys.path.insert(0, _root_dir)

try:
    import jellyfin_groupings as _jg
    JellyfinClient = getattr(_jg, "JellyfinClient", None)
    process_groupings = getattr(_jg, "process_groupings", None)
    group_movies_by_tag = getattr(_jg, "group_movies_by_tag", None)
    group_movies_by_genre = getattr(_jg, "group_movies_by_genre", None)
    main = getattr(_jg, "main", None)
except ImportError:
    JellyfinClient = None
    process_groupings = None
    group_movies_by_tag = None
    group_movies_by_genre = None
    main = None

__all__ = ["JellyfinClient", "process_groupings", "group_movies_by_tag", "group_movies_by_genre", "main"]
