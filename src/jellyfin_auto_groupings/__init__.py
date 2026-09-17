import sys
import os

# Ensure src directory is in sys.path
_src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

try:
    from jellyfin_auto_groupings.client import JellyfinClient, JellyfinAPIError
except ImportError:
    try:
        from .client import JellyfinClient, JellyfinAPIError
    except ImportError:
        JellyfinClient = None
        JellyfinAPIError = None

__all__ = ["JellyfinClient", "JellyfinAPIError"]
