import importlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

# Get the directory containing this package
_package_dir = Path(__file__).resolve().parent
# Get the project root directory (parent of package directory)
_root_dir = _package_dir.parent
# Path to the root-level jellyfin_groupings.py module
_module_path = _root_dir / "jellyfin_groupings.py"

# Load the root-level jellyfin_groupings.py module
_jg: ModuleType | None = None
_spec = importlib.util.spec_from_file_location("jellyfin_groupings_root", _module_path)
if _spec is not None and _spec.loader is not None:
    _jg = importlib.util.module_from_spec(_spec)
    sys.modules["jellyfin_groupings_root"] = _jg
    try:
        _spec.loader.exec_module(_jg)
    except Exception:
        _jg = None
else:
    _jg = None

if _jg is not None:
    JellyfinClient = getattr(_jg, "JellyfinClient", None)
    process_groupings = getattr(_jg, "process_groupings", None)
    group_movies_by_tag = getattr(_jg, "group_movies_by_tag", None)
    group_movies_by_genre = getattr(_jg, "group_movies_by_genre", None)
    main = getattr(_jg, "main", None)
else:
    JellyfinClient = None
    process_groupings = None
    group_movies_by_tag = None
    group_movies_by_genre = None
    main = None

__all__ = [
    "JellyfinClient",
    "group_movies_by_genre",
    "group_movies_by_tag",
    "main",
    "process_groupings",
]
