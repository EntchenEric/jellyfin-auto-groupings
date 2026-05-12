#!/bin/bash
# Generate test media files for E2E testing
# Requires: ffmpeg
# Usage: ./e2e/generate_test_media.sh
# Creates small MKV files with metadata in e2e/test_media/

set -e

MEDIA_DIR="$(dirname "$0")/test_media"
mkdir -p "$MEDIA_DIR"

generate_movie() {
    local title="$1"
    local year="$2"
    local genre="$3"
    local dir="$MEDIA_DIR/$title ($year)"
    mkdir -p "$dir"
    local file="$dir/$title ($year).mkv"

    if [ -f "$file" ]; then
        echo "Skipping existing: $file"
        return
    fi

    echo "Generating: $title ($year) [$genre]"
    ffmpeg -y -f lavfi -i "testsrc=duration=3:size=640x360:rate=24" \
        -f lavfi -i "sine=frequency=440:duration=3" \
        -metadata title="$title" \
        -metadata date="$year" \
        -metadata genre="$genre" \
        -c:v libx264 -preset ultrafast -pix_fmt yuv420p \
        -c:a aac -b:a 64k \
        -shortest "$file" 2>/dev/null
}

generate_movie "The Matrix" "1999" "Action; Sci-Fi"
generate_movie "The Grand Budapest Hotel" "2014" "Comedy; Drama"
generate_movie "Spirited Away" "2001" "Animation; Fantasy"
generate_movie "Interstellar" "2014" "Sci-Fi; Drama"

echo ""
echo "Test media generated in: $MEDIA_DIR"
ls -la "$MEDIA_DIR"/*/
