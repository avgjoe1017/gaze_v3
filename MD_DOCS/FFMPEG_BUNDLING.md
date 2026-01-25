# FFmpeg Bundling Guide

This document explains how FFmpeg binaries are bundled as Tauri sidecars in SafeKeeps Vault.

## Overview

FFmpeg and FFprobe are bundled alongside the application to eliminate the need for users to install them separately. This makes SafeKeeps Vault truly turn-key - users can install and run without any additional setup.

## Architecture

### Tauri Sidecars

Tauri sidecars are external binaries that are bundled with the application. They are:
- Extracted to a temporary directory at runtime
- Accessible via Tauri's sidecar API
- Automatically included in installers (MSI, DMG, AppImage, etc.)

### Path Resolution

The application uses a two-tier path resolution:

1. **Environment Variables** (bundled sidecars):
   - `GAZE_FFMPEG_PATH` - Path to bundled FFmpeg
   - `GAZE_FFPROBE_PATH` - Path to bundled FFprobe
   - Set by Rust code when launching the engine

2. **PATH Fallback** (system installation):
   - If env vars not set or binaries missing, falls back to system PATH
   - Supports development builds and users who prefer system-wide FFmpeg

### Code Flow

```
Tauri App (Rust)
  ↓
Resolve sidecar paths using Tauri API
  ↓
Set GAZE_FFMPEG_PATH and GAZE_FFPROBE_PATH env vars
  ↓
Launch Python engine with env vars
  ↓
Python checks env vars first, then PATH
  ↓
All FFmpeg calls use resolved paths
```

## Adding FFmpeg Binaries

### Windows

**Automated (Recommended):**
```powershell
.\scripts\download-ffmpeg-binaries.ps1
```

**Manual:**
1. Visit https://www.gyan.dev/ffmpeg/builds/
2. Download `ffmpeg-release-essentials.zip` (LGPL build)
3. Extract and copy `ffmpeg.exe` and `ffprobe.exe` from the `bin` folder
4. Place in `app/src-tauri/binaries/`
5. Rename to:
   - `ffmpeg-x86_64-pc-windows-msvc.exe`
   - `ffprobe-x86_64-pc-windows-msvc.exe`

### macOS

**Using Homebrew (Recommended):**
```bash
brew install ffmpeg
cp $(which ffmpeg) app/src-tauri/binaries/ffmpeg-$(uname -m | sed 's/x86_64/x86_64/' | sed 's/arm64/aarch64/')-apple-darwin
cp $(which ffprobe) app/src-tauri/binaries/ffprobe-$(uname -m | sed 's/x86_64/x86_64/' | sed 's/arm64/aarch64/')-apple-darwin
chmod +x app/src-tauri/binaries/ffmpeg-* app/src-tauri/binaries/ffprobe-*
```

**Manual:**
1. Visit https://evermeet.cx/ffmpeg/ (LGPL builds)
2. Download `ffmpeg` and `ffprobe`
3. Place in `app/src-tauri/binaries/` with correct naming
4. Make executable: `chmod +x ffmpeg-* ffprobe-*`

### Linux

**Using System Package Manager:**
```bash
sudo apt install ffmpeg  # or your package manager
cp $(which ffmpeg) app/src-tauri/binaries/ffmpeg-x86_64-unknown-linux-gnu
cp $(which ffprobe) app/src-tauri/binaries/ffprobe-x86_64-unknown-linux-gnu
chmod +x app/src-tauri/binaries/ffmpeg-* app/src-tauri/binaries/ffprobe-*
```

**Static Builds:**
1. Visit https://johnvansickle.com/ffmpeg/ (LGPL static builds)
2. Download and extract
3. Copy `ffmpeg` and `ffprobe` to `app/src-tauri/binaries/` with correct naming

## Naming Convention

Tauri sidecars must follow a specific naming pattern:
- `{name}-{target-triple}`

Where `{target-triple}` is:
- Windows: `x86_64-pc-windows-msvc`
- macOS ARM: `aarch64-apple-darwin`
- macOS Intel: `x86_64-apple-darwin`
- Linux: `x86_64-unknown-linux-gnu`

## License Compliance

**Critical**: Only LGPL builds are used, not GPL-only builds.

### Verifying LGPL Build

```bash
ffmpeg -buildconf | grep -i "license"
```

Look for "lgpl" in the output. If you see "gpl" without "lgpl", it's a GPL-only build and cannot be used.

### Sources for LGPL Builds

- **Windows**: https://www.gyan.dev/ffmpeg/builds/ (release builds are LGPL)
- **macOS**: https://evermeet.cx/ffmpeg/ (LGPL builds available)
- **Linux**: Most distributions ship LGPL builds by default

### Building from Source (LGPL)

```bash
./configure --enable-gpl=no --enable-nonfree=no
make
```

## Testing

### Verify Binaries Present

```powershell
# Windows
.\scripts\verify-binaries.ps1

# macOS/Linux
./scripts/verify-binaries.sh
```

### Test Clean Install

1. Build the application: `scripts/build-app.ps1` or `scripts/build-app.sh`
2. Install on a clean machine (no FFmpeg in PATH)
3. Launch the application
4. Verify FFmpeg is detected (check health endpoint or logs)
5. Test video indexing to ensure FFmpeg works

### Expected Behavior

- **With bundled binaries**: FFmpeg detected immediately, no user action needed
- **Without bundled binaries**: Falls back to PATH, shows "Repair" UI if not found
- **Logs show source**: "bundled" vs "system" in health check logs

## Troubleshooting

### Binaries Not Found

1. Check file names match exactly (case-sensitive on Linux/macOS)
2. Verify binaries are in `app/src-tauri/binaries/` directory
3. Ensure binaries are executable (Linux/macOS: `chmod +x`)
4. Check `tauri.conf.json` includes them in `externalBin`

### Wrong License

If you get a GPL-only build:
1. Download/build an LGPL version
2. Replace the binaries
3. Verify with `ffmpeg -buildconf | grep license`

### Antivirus Quarantine

Some antivirus software may quarantine FFmpeg binaries:
1. Add exception for the binaries directory
2. Or add exception for the entire application
3. Re-download if binaries were deleted

## Build Integration

The build scripts automatically:
1. Check for required binaries
2. Warn if FFmpeg binaries are missing (non-fatal for dev builds)
3. Bundle all binaries into the installer

See `scripts/build-app.ps1` and `scripts/build-app.sh` for details.

## Future Enhancements

Potential improvements:
- Auto-download FFmpeg during build (if not present)
- Support for multiple architectures in single build
- FFmpeg version checking and updates
- Automatic LGPL license verification
