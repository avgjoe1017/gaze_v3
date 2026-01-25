# Full build script for Gaze V3 (Windows)
# Builds the engine binary and the Tauri application

$ErrorActionPreference = "Stop"

# Get paths
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir
$AppDir = Join-Path $RootDir "app"

Write-Host "Building Gaze V3 Application..." -ForegroundColor Cyan
Write-Host "===============================" -ForegroundColor Cyan

# Step 1: Build the engine
Write-Host "`n[1/4] Building Python engine..." -ForegroundColor Yellow
$BuildEngineScript = Join-Path $ScriptDir "build-engine.ps1"
& $BuildEngineScript
if ($LASTEXITCODE -ne 0) {
    Write-Host "Engine build failed" -ForegroundColor Red
    exit 1
}

# Step 2: Verify binaries exist
Write-Host "`n[2/4] Verifying binaries..." -ForegroundColor Yellow
$BinariesDir = Join-Path $RootDir "app" "src-tauri" "binaries"

# Check engine binary
$EngineBinary = Join-Path $BinariesDir "gaze-engine-x86_64-pc-windows-msvc.exe"
if (-not (Test-Path $EngineBinary)) {
    Write-Host "Engine binary not found at: $EngineBinary" -ForegroundColor Red
    exit 1
}
Write-Host "✓ Engine binary found" -ForegroundColor Green

# Check FFmpeg binaries (warn if missing, but don't fail build)
$FfmpegBinary = Join-Path $BinariesDir "ffmpeg-x86_64-pc-windows-msvc.exe"
$FfprobeBinary = Join-Path $BinariesDir "ffprobe-x86_64-pc-windows-msvc.exe"
if (-not (Test-Path $FfmpegBinary) -or -not (Test-Path $FfprobeBinary)) {
    Write-Host "⚠ FFmpeg binaries not found (optional for dev builds)" -ForegroundColor Yellow
    Write-Host "  Run: scripts\download-ffmpeg-binaries.ps1" -ForegroundColor Yellow
    Write-Host "  Or see: app\src-tauri\binaries\README.md" -ForegroundColor Yellow
} else {
    Write-Host "✓ FFmpeg binaries found" -ForegroundColor Green
}

# Step 3: Install npm dependencies
Write-Host "`n[3/4] Installing npm dependencies..." -ForegroundColor Yellow
Push-Location $AppDir
npm install --silent
if ($LASTEXITCODE -ne 0) {
    Write-Host "npm install failed" -ForegroundColor Red
    Pop-Location
    exit 1
}
Pop-Location
Write-Host "npm dependencies installed" -ForegroundColor Green

# Step 4: Build Tauri application
Write-Host "`n[4/4] Building Tauri application..." -ForegroundColor Yellow
Push-Location $AppDir
npm run tauri build
if ($LASTEXITCODE -ne 0) {
    Write-Host "Tauri build failed" -ForegroundColor Red
    Pop-Location
    exit 1
}
Pop-Location

# Find output
$InstallerDir = Join-Path $AppDir "src-tauri" "target" "release" "bundle"
Write-Host "`n===============================" -ForegroundColor Cyan
Write-Host "Build complete!" -ForegroundColor Green
Write-Host "`nOutput location:" -ForegroundColor Cyan

# List installer files
if (Test-Path (Join-Path $InstallerDir "msi")) {
    Write-Host "  MSI: $(Get-ChildItem (Join-Path $InstallerDir 'msi') -Filter '*.msi' | Select-Object -First 1 -ExpandProperty FullName)" -ForegroundColor Gray
}
if (Test-Path (Join-Path $InstallerDir "nsis")) {
    Write-Host "  NSIS: $(Get-ChildItem (Join-Path $InstallerDir 'nsis') -Filter '*.exe' | Select-Object -First 1 -ExpandProperty FullName)" -ForegroundColor Gray
}

Write-Host "`nTo install, run one of the installers above." -ForegroundColor Cyan
