#!/bin/bash
# Download test videos from YouTube playlist for performance testing
# Uses yt-dlp to download 100 videos from the playlist

set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

# Test library directory
TEST_LIB_DIR="$ROOT_DIR/test-library"
DOWNLOAD_ARCHIVE="$TEST_LIB_DIR/downloaded.txt"

# Playlist URL
PLAYLIST_URL="https://www.youtube.com/playlist?list=PLLd8OpOlwVZs1U_-wTtB00Y-nhX1zIi22"

echo "Downloading test videos for Gaze V3 performance testing..."
echo "Playlist: $PLAYLIST_URL"
echo "Output directory: $TEST_LIB_DIR"
echo ""

# Check yt-dlp is installed
echo "Checking yt-dlp..."
if ! command -v yt-dlp &> /dev/null; then
    echo "ERROR: yt-dlp not found. Install it with:"
    echo "  pip install yt-dlp"
    echo "  or: brew install yt-dlp (macOS)"
    exit 1
fi

YTDLP_VERSION=$(yt-dlp --version)
echo "yt-dlp version: $YTDLP_VERSION"
echo ""

# Create test library directory
mkdir -p "$TEST_LIB_DIR"

# Download videos
echo "Starting download (this may take a while for 100+ videos)..."
echo ""

yt-dlp \
    -f "bv*+ba/b" \
    --merge-output-format mp4 \
    -o "$TEST_LIB_DIR/%(uploader)s/%(title)s.%(ext)s" \
    --download-archive "$DOWNLOAD_ARCHIVE" \
    "$PLAYLIST_URL"

if [ $? -eq 0 ]; then
    echo ""
    echo "Download complete!"
    echo ""
    echo "Next steps:"
    echo "1. Add library in Gaze V3: $TEST_LIB_DIR"
    echo "2. Wait for scan to complete"
    echo "3. Click 'Start Indexing' to begin processing"
    echo "4. Monitor progress in the Status Panel"
else
    echo ""
    echo "Download failed. Check error messages above."
    exit 1
fi