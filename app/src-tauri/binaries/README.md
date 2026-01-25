# FFmpeg Binaries for Tauri Sidecars

This directory should contain FFmpeg and FFprobe binaries for each target platform.

## Required Files

### Windows (x86_64-pc-windows-msvc)
- `ffmpeg-x86_64-pc-windows-msvc.exe`
- `ffprobe-x86_64-pc-windows-msvc.exe`

### macOS (aarch64-apple-darwin)
- `ffmpeg-aarch64-apple-darwin`
- `ffprobe-aarch64-apple-darwin`

### macOS (x86_64-apple-darwin) - Intel Macs
- `ffmpeg-x86_64-apple-darwin`
- `ffprobe-x86_64-apple-darwin`

### Linux (x86_64-unknown-linux-gnu)
- `ffmpeg-x86_64-unknown-linux-gnu`
- `ffprobe-x86_64-unknown-linux-gnu`

## Important: LGPL Builds Only

**You must use LGPL builds, not GPL-only builds**, for license compliance.

### Where to Get LGPL Builds

1. **Windows:**
   - https://www.gyan.dev/ffmpeg/builds/ (use "release builds" - these are LGPL)
   - Or build from source with `--enable-gpl=no` flag

2. **macOS:**
   - https://evermeet.cx/ffmpeg/ (LGPL builds available)
   - Or build from source: `brew install ffmpeg` (default is LGPL)

3. **Linux:**
   - Most distributions ship LGPL builds by default
   - Or build from source with `--enable-gpl=no`

### Verification

To verify a build is LGPL (not GPL-only), run:
```bash
ffmpeg -buildconf | grep -i "license"
```

Look for "lgpl" in the output. If you see "gpl" without "lgpl", it's a GPL-only build.

## Setup Instructions

1. Download or build FFmpeg/FFprobe for each target platform
2. Rename the executables to match the naming convention above
3. Place them in this directory (`app/src-tauri/binaries/`)
4. Ensure binaries are executable (Linux/macOS: `chmod +x ffmpeg-* ffprobe-*`)

## Build Scripts

See `scripts/download-ffmpeg-binaries.sh` (Linux/macOS) or `scripts/download-ffmpeg-binaries.ps1` (Windows) for automated download scripts.

## Testing

After adding binaries, test the build:
```bash
npm run tauri build
```

The binaries should be automatically bundled into the installer.
