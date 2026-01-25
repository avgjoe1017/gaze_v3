#!/bin/bash
# Shell script to download FFmpeg binaries for macOS and Linux
# Downloads LGPL builds

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BINARIES_DIR="$SCRIPT_DIR/../app/src-tauri/binaries"
mkdir -p "$BINARIES_DIR"

echo "Downloading FFmpeg binaries (LGPL builds)..."

# Detect platform
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS
    ARCH=$(uname -m)
    if [[ "$ARCH" == "arm64" ]]; then
        TARGET="aarch64-apple-darwin"
    else
        TARGET="x86_64-apple-darwin"
    fi
    
    echo "Detected macOS ($ARCH), target: $TARGET"
    echo ""
    echo "For macOS, please download FFmpeg manually:"
    echo "1. Visit https://evermeet.cx/ffmpeg/ (LGPL builds)"
    echo "2. Download ffmpeg and ffprobe"
    echo "3. Copy to $BINARIES_DIR with names:"
    echo "   - ffmpeg-$TARGET"
    echo "   - ffprobe-$TARGET"
    echo "4. Make executable: chmod +x ffmpeg-$TARGET ffprobe-$TARGET"
    echo ""
    echo "Or build from source:"
    echo "  brew install ffmpeg"
    echo "  cp $(which ffmpeg) $BINARIES_DIR/ffmpeg-$TARGET"
    echo "  cp $(which ffprobe) $BINARIES_DIR/ffprobe-$TARGET"
    
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    # Linux
    TARGET="x86_64-unknown-linux-gnu"
    
    echo "Detected Linux, target: $TARGET"
    echo ""
    echo "For Linux, you can:"
    echo "1. Use system FFmpeg (if installed):"
    echo "   sudo apt install ffmpeg  # or your package manager"
    echo "   cp $(which ffmpeg) $BINARIES_DIR/ffmpeg-$TARGET"
    echo "   cp $(which ffprobe) $BINARIES_DIR/ffprobe-$TARGET"
    echo ""
    echo "2. Or download static build from:"
    echo "   https://johnvansickle.com/ffmpeg/ (LGPL builds)"
    echo "   Extract and copy ffmpeg and ffprobe to $BINARIES_DIR"
    echo ""
    echo "3. Or build from source with --enable-gpl=no"
    
else
    echo "Unsupported platform: $OSTYPE"
    exit 1
fi

echo ""
echo "After adding binaries, make them executable:"
echo "  chmod +x $BINARIES_DIR/ffmpeg-* $BINARIES_DIR/ffprobe-*"
