#!/bin/bash
# Full build script for Gaze V3 (macOS/Linux)
# Builds the engine binary and the Tauri application

set -e

# Get paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
APP_DIR="$ROOT_DIR/app"

echo -e "\033[36mBuilding Gaze V3 Application...\033[0m"
echo -e "\033[36m===============================\033[0m"

# Step 1: Build the engine
echo -e "\n\033[33m[1/4] Building Python engine...\033[0m"
"$SCRIPT_DIR/build-engine.sh" || {
    echo -e "\033[31mEngine build failed\033[0m"
    exit 1
}

# Step 2: Verify engine binary exists
echo -e "\n\033[33m[2/4] Verifying engine binary...\033[0m"
if [[ "$OSTYPE" == "darwin"* ]]; then
    ARCH=$(uname -m)
    if [[ "$ARCH" == "arm64" ]]; then
        BINARY_NAME="gaze-engine-aarch64-apple-darwin"
    else
        BINARY_NAME="gaze-engine-x86_64-apple-darwin"
    fi
else
    BINARY_NAME="gaze-engine-x86_64-unknown-linux-gnu"
fi

BINARY_PATH="$ROOT_DIR/app/src-tauri/binaries/$BINARY_NAME"
if [ ! -f "$BINARY_PATH" ]; then
    echo -e "\033[31mEngine binary not found at: $BINARY_PATH\033[0m"
    exit 1
fi
echo -e "\033[32mEngine binary found\033[0m"

# Step 3: Install npm dependencies
echo -e "\n\033[33m[3/4] Installing npm dependencies...\033[0m"
cd "$APP_DIR"
npm install --silent || {
    echo -e "\033[31mnpm install failed\033[0m"
    exit 1
}
echo -e "\033[32mnpm dependencies installed\033[0m"

# Step 4: Build Tauri application
echo -e "\n\033[33m[4/4] Building Tauri application...\033[0m"
npm run tauri build || {
    echo -e "\033[31mTauri build failed\033[0m"
    exit 1
}

# Find output
BUNDLE_DIR="$APP_DIR/src-tauri/target/release/bundle"
echo -e "\n\033[36m===============================\033[0m"
echo -e "\033[32mBuild complete!\033[0m"
echo -e "\n\033[36mOutput location:\033[0m"

if [[ "$OSTYPE" == "darwin"* ]]; then
    if [ -d "$BUNDLE_DIR/macos" ]; then
        echo -e "\033[90m  App: $(ls "$BUNDLE_DIR/macos/"*.app 2>/dev/null | head -1)\033[0m"
    fi
    if [ -d "$BUNDLE_DIR/dmg" ]; then
        echo -e "\033[90m  DMG: $(ls "$BUNDLE_DIR/dmg/"*.dmg 2>/dev/null | head -1)\033[0m"
    fi
else
    if [ -d "$BUNDLE_DIR/deb" ]; then
        echo -e "\033[90m  DEB: $(ls "$BUNDLE_DIR/deb/"*.deb 2>/dev/null | head -1)\033[0m"
    fi
    if [ -d "$BUNDLE_DIR/appimage" ]; then
        echo -e "\033[90m  AppImage: $(ls "$BUNDLE_DIR/appimage/"*.AppImage 2>/dev/null | head -1)\033[0m"
    fi
fi

echo -e "\n\033[36mTo install, run the appropriate installer for your platform.\033[0m"
