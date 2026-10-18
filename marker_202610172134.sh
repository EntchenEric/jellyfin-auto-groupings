#!/bin/bash
# Marker cleanup script for Jellyfin Groupings Improvement Bot
# Usage: marker.sh delete <ID>

if [[ "$1" == "delete" && -n "$2" ]]; then
    ID="$2"
    # Create a backup before deletion
    if [[ -f "/home/admin/.openclaw/workspace/jellyfin-auto-groupings/marker_$ID.sh" ]]; then
        mv "/home/admin/.openclaw/workspace/jellyfin-auto-groupings/marker_$ID.sh" "/home/admin/.openclaw/workspace/jellyfin-auto-groupings/marker_$ID.sh.backup"
    fi
    # Delete the marker
    rm -f "/home/admin/.openclaw/workspace/jellyfin-auto-groupings/marker_$ID.sh"
    echo "Marker for ID $ID deleted successfully."
else
    echo "Usage: marker.sh delete <ID>"
    exit 1
fi
