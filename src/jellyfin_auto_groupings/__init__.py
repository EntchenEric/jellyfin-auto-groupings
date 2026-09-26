from pathlib import Path

# Ensure src directory is in sys.path
_src_dir = Path(__file__).resolve().parent.parent
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

try:
    from jellyfin_auto_groupings.client import JellyfinAPIError, JellyfinClient
except ImportError:
    try:
        from .client import JellyfinAPIError, JellyfinClient
    except ImportError:
        JellyfinClient = None
        JellyfinAPIError = None

__all__ = ["JellyfinAPIError", "JellyfinClient"]
