"""
app.py – Application entry-point for Jellyfin Groupings.

Creates the Flask application, registers the route Blueprint defined in
:mod:`routes`, and starts the development server when run directly.

The bulk of the application logic lives in the following modules:

* :mod:`config`   – configuration persistence
* :mod:`imdb`     – IMDb list scraping
* :mod:`trakt`    – Trakt API list fetching
* :mod:`jellyfin` – Jellyfin API helpers and sort-order mapping
* :mod:`sync`     – synchronisation business logic
* :mod:`routes`   – Flask Blueprint with all HTTP route handlers
"""

from __future__ import annotations

from flask import Flask

from config import DEFAULT_CONFIG, CONFIG_FILE, save_config
from routes import bp

import os

# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

app = Flask(__name__)
app.register_blueprint(bp)

# ---------------------------------------------------------------------------
# Entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Create a default config file on first run so the UI has something to load
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG.copy())

    app.run(host="0.0.0.0", debug=True, port=5000)
