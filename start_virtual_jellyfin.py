#!/usr/bin/env python3
"""
Helper script to run the virtual Jellyfin mock server for development and testing.
Provides a dashboard at http://localhost:8096
"""

from tests.virtual_jellyfin import app

if __name__ == "__main__":
    print("Starting Virtual Jellyfin Mock Server...")
    print("Dashboard: http://localhost:8096")
    print("Press Ctrl+C to stop.")
    app.run(host="0.0.0.0", port=8096, debug=True)
