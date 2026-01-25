#!/bin/bash
# Verification script for Tauri sidecar binaries
# Checks that all required binaries are present

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BINARIES_DIR="$ROOT_DIR/app/src-tauri/binaries"

echo "Verifying Tauri sidecar binaries..."
echo "===================================="
echo ""

# Detect target
if [[ "$OSTYPE" == "darwin"* ]]; then
    ARCH=$(uname -m)
    if [[ "$ARCH" == "arm64" ]]; then
        TARGET="aarch64-apple-darwin"
    else
        TARGET="x86_64-apple-darwin"
    fi
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    TARGET="x86_64-unknown-linux-gnu"
else
    echo "Unsupported platform: $OSTYPE"
    exit 1
fi

ALL_PRESENT=true
MISSING=()

# Required binaries
REQUIRED_BINARIES=(
    "gaze-engine-$TARGET"
    "ffmpeg-$TARGET"
    "ffprobe-$TARGET"
)

for binary in "${REQUIRED_BINARIES[@]}"; do
    path="$BINARIES_DIR/$binary"
    if [ -f "$path" ]; then
        size=$(du -h "$path" | cut -f1)
        echo "✓ $binary ($size)"
    else
        echo "✗ $binary (MISSING)"
        MISSING+=("$binary")
        ALL_PRESENT=false
    fi
done

echo ""

if [ "$ALL_PRESENT" = false ]; then
    echo "Missing binaries detected!"
    echo ""
    echo "To fix:"
    echo "1. Engine binary: Run scripts/build-engine.sh"
    echo "2. FFmpeg binaries: Run scripts/download-ffmpeg-binaries.sh"
    echo "   Or see: app/src-tauri/binaries/README.md for manual instructions"
    echo ""
    exit 1
else
    echo "✓ All binaries present and ready for build!"
    echo ""
    exit 0
fi
