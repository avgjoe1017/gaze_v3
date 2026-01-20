#!/bin/bash
# Development script for macOS/Linux
# Starts both the Python engine and Tauri dev server

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

echo -e "\033[36mStarting Gaze V3 development environment...\033[0m"

# Check Python
echo -e "\033[33mChecking Python...\033[0m"
python3 --version || { echo "Python not found. Please install Python 3.11+"; exit 1; }

# Install Python dependencies
echo -e "\033[33mInstalling Python dependencies...\033[0m"
cd "$ROOT_DIR/engine"
pip install -e . --quiet

# Check Node
echo -e "\033[33mChecking Node.js...\033[0m"
node --version || { echo "Node.js not found. Please install Node.js 18+"; exit 1; }

# Install npm dependencies
echo -e "\033[33mInstalling npm dependencies...\033[0m"
cd "$ROOT_DIR/app"
npm install --silent

# Check Rust/Cargo (required for Tauri)
echo -e "\033[33mChecking Rust/Cargo...\033[0m"
cargo --version || { 
    echo "Rust/Cargo not found. Please install Rust:"
    echo "  Visit https://rustup.rs/ or run: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"
    exit 1
}

# Create engine stub for development (real binary not needed in dev mode)
echo -e "\033[33mEnsuring engine stub exists for Tauri build...\033[0m"
BINARY_DIR="$ROOT_DIR/app/src-tauri/binaries"
mkdir -p "$BINARY_DIR"

# Determine platform suffix
if [[ "$OSTYPE" == "darwin"* ]]; then
    ARCH=$(uname -m)
    if [[ "$ARCH" == "arm64" ]]; then
        STUB_NAME="gaze-engine-aarch64-apple-darwin"
    else
        STUB_NAME="gaze-engine-x86_64-apple-darwin"
    fi
else
    STUB_NAME="gaze-engine-x86_64-unknown-linux-gnu"
fi

STUB_PATH="$BINARY_DIR/$STUB_NAME"
if [ ! -f "$STUB_PATH" ]; then
    # Create a minimal executable stub for development
    echo -e "\033[33mCreating development stub...\033[0m"
    echo '#!/bin/sh
echo "ERROR: This is a development stub."
echo "In development mode, the engine runs via Python."
echo "For production builds, run scripts/build-engine.sh first."
exit 1' > "$STUB_PATH"
    chmod +x "$STUB_PATH"
    echo -e "\033[90mDev stub created at: $STUB_PATH\033[0m"
fi

# Start Tauri dev server
echo -e "\033[32mStarting Tauri dev server...\033[0m"
npm run tauri dev
