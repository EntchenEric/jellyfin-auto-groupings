"""app.py - Application entry-point for Jellyfin Groupings.

Creates the Flask application, registers the route Blueprint defined in
:mod:`routes`, and starts the development server when run directly.

The bulk of the application logic lives in the following modules:

* :mod:`config`   - configuration persistence
* :mod:`imdb`     - IMDb list scraping
* :mod:`trakt`    - Trakt API list fetching
* :mod:`jellyfin` - Jellyfin API helpers and sort-order mapping
* :mod:`sync`     - synchronisation business logic
* :mod:`routes`   - Flask Blueprint with all HTTP route handlers
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from flask import Flask

from config import CONFIG_FILE, DEFAULT_CONFIG, _env_flag, save_config
from routes import bp
from scheduler import start_scheduler


def _resolve_log_level(name: str) -> int:
    """Resolve an environment variable to a Python logging level.

    Accepts case-insensitive level names (DEBUG, INFO, WARNING, ERROR,
    CRITICAL) and returns the corresponding :mod:`logging` constant.
    Falls back to ``logging.INFO`` for unset, empty, or unrecognised values.


    Args:
            name: The name of the logging level constant.

    """
    raw = os.environ.get(name, "").strip().upper()
    level = getattr(logging, raw, None)
    if isinstance(level, int):
        return level
    return logging.INFO


def _configure_logging() -> None:
    """Configure logging with both console and rotating file output.

    The log level can be controlled via the ``LOG_LEVEL`` environment variable
    (default: ``INFO``).  Accepted values are ``DEBUG``, ``INFO``, ``WARNING``,
    ``ERROR``, and ``CRITICAL``.
    """
    log_level = _resolve_log_level("LOG_LEVEL")

    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(exist_ok=True)

    file_handler = RotatingFileHandler(
        str(log_dir / "jellyfin-groupings.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=3,
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ),
    )

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(),
            file_handler,
        ],
    )


_configure_logging()

logger = logging.getLogger(__name__)

__all__ = ["app"]

app = Flask(__name__, template_folder="templates", static_folder="static")
app.register_blueprint(bp)

# Start the background sync scheduler
if (
    not app.testing
    and _env_flag("SCHEDULER_ENABLED", default=True)
    and (not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true")
):
    try:
        start_scheduler()
    except Exception:
        logger.exception(
            "Failed to start background scheduler — "
            "scheduled syncs will not run.",
        )


# ---------------------------------------------------------------------------
# Entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Create a default config file on first run so the UI has something to load
    if not Path(CONFIG_FILE).exists():
        save_config(DEFAULT_CONFIG.copy())

    port = int(os.environ.get("FLASK_PORT", "5000"))
    debug = _env_flag("FLASK_DEBUG")
    app.run(host="0.0.0.0", debug=debug, port=port)
