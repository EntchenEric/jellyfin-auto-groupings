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
from pathlib import Path

from flask import Flask

import network  # noqa: F401 — monkey-patches requests.get/post/delete with retry
from config import CONFIG_FILE, DEFAULT_CONFIG, save_config
from routes import bp
from scheduler import start_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

__all__ = ["app"]

app = Flask(__name__, template_folder="templates", static_folder="static")
app.register_blueprint(bp)

# Start the background sync scheduler
if not app.testing and (not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true"):
    start_scheduler()

# ---------------------------------------------------------------------------
# Entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Create a default config file on first run so the UI has something to load
    if not Path(CONFIG_FILE).exists():
        save_config(DEFAULT_CONFIG.copy())

    port = int(os.environ.get("FLASK_PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", debug=debug, port=port)
