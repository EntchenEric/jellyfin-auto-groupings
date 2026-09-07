import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class Config:
    """Configuration settings for Jellyfin Auto Groupings."""
    server_url: str
    api_key: str
    dry_run: bool = False


def load_config() -> Config:
    """Load configuration from environment variables.

    Raises:
        ValueError: If JELLYFIN_URL or JELLYFIN_API_KEY is not set.
    """
    server_url = os.environ.get("JELLYFIN_URL", "").strip()
    api_key = os.environ.get("JELLYFIN_API_KEY", "").strip()
    dry_run = os.environ.get("DRY_RUN", "false").lower() in ("true", "1", "yes")

    if not server_url or not api_key:
        raise ValueError("JELLYFIN_URL and JELLYFIN_API_KEY must be set in environment.")

    return Config(server_url=server_url, api_key=api_key, dry_run=dry_run)
