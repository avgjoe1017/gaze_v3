#!/bin/bash
# Build script for Gaze Engine (macOS/Linux)
# Creates a standalone executable using PyInstaller

set -e

# Get paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
ENGINE_DIR="$ROOT_DIR/engine"
OUTPUT_DIR="$ROOT_DIR/app/src-tauri/binaries"

echo -e "\033[36mBuilding Gaze Engine...\033[0m"
echo -e "\033[90mEngine dir: $ENGINE_DIR\033[0m"
echo -e "\033[90mOutput dir: $OUTPUT_DIR\033[0m"

# Check Python
echo -e "\n\033[33mChecking Python...\033[0m"
python3 --version || {
    echo -e "\033[31mPython not found. Please install Python 3.11+\033[0m"
    exit 1
}

# Create virtual environment if needed
VENV_DIR="$ENGINE_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
    echo -e "\n\033[33mCreating virtual environment...\033[0m"
    python3 -m venv "$VENV_DIR"
fi

# Activate virtual environment
source "$VENV_DIR/bin/activate"

# Install dependencies
echo -e "\n\033[33mInstalling Python dependencies...\033[0m"
cd "$ENGINE_DIR"

# Install package with all extras
pip install -e ".[ml,dev]" --quiet || {
    echo -e "\033[31mFailed to install dependencies\033[0m"
    exit 1
}

# Verify PyInstaller is available
pyinstaller --version 2>/dev/null || {
    echo -e "\033[33mPyInstaller not found, installing...\033[0m"
    pip install pyinstaller
}
echo -e "\033[90mPyInstaller: $(pyinstaller --version)\033[0m"

# Clean previous builds
echo -e "\n\033[33mCleaning previous builds...\033[0m"
rm -rf "$ENGINE_DIR/dist" "$ENGINE_DIR/build"

# Run PyInstaller
echo -e "\n\033[33mRunning PyInstaller...\033[0m"
pyinstaller gaze-engine.spec --noconfirm || {
    echo -e "\033[31mPyInstaller build failed\033[0m"
    exit 1
}

# Determine platform suffix
if [[ "$OSTYPE" == "darwin"* ]]; then
    ARCH=$(uname -m)
    if [[ "$ARCH" == "arm64" ]]; then
        PLATFORM_SUFFIX="aarch64-apple-darwin"
    else
        PLATFORM_SUFFIX="x86_64-apple-darwin"
    fi
else
    PLATFORM_SUFFIX="x86_64-unknown-linux-gnu"
fi

EXE_NAME="gaze-engine-$PLATFORM_SUFFIX"
BUILT_EXE="$ENGINE_DIR/dist/$EXE_NAME"

# Verify output exists
if [ ! -f "$BUILT_EXE" ]; then
    echo -e "\033[31mBuild failed: $BUILT_EXE not found\033[0m"
    echo -e "\033[33mContents of dist:\033[0m"
    ls -la "$ENGINE_DIR/dist"
    exit 1
fi

EXE_SIZE=$(du -h "$BUILT_EXE" | cut -f1)
echo -e "\033[32mBuilt: $EXE_NAME ($EXE_SIZE)\033[0m"

# Create output directory
if [ ! -d "$OUTPUT_DIR" ]; then
    echo -e "\n\033[33mCreating binaries directory...\033[0m"
    mkdir -p "$OUTPUT_DIR"
fi

# Copy to output directory
echo -e "\n\033[33mCopying to Tauri binaries...\033[0m"
DEST_PATH="$OUTPUT_DIR/$EXE_NAME"
cp "$BUILT_EXE" "$DEST_PATH"
chmod +x "$DEST_PATH"
echo -e "\033[90mCopied to: $DEST_PATH\033[0m"

# Quick verification
echo -e "\n\033[33mVerifying executable...\033[0m"
if "$DEST_PATH" --help >/dev/null 2>&1; then
    echo -e "\033[32mExecutable verified successfully\033[0m"
else
    echo -e "\033[33mWarning: Executable may have issues\033[0m"
fi

echo -e "\n\033[32mEngine build complete!\033[0m"
echo -e "\033[36mOutput: $DEST_PATH\033[0m"
