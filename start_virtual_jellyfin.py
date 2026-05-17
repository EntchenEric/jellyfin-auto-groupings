#!/usr/bin/env python3
"""Helper script to run the virtual Jellyfin mock server for development and testing.

Provides a dashboard at http://localhost:8096.
"""

from __future__ import annotations

import logging
import os

from tests.virtual_jellyfin import app

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    logger.info("Starting Virtual Jellyfin Mock Server...")
    logger.info("Dashboard: http://localhost:8096")
    logger.info("Press Ctrl+C to stop.")
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=8096, debug=debug)
