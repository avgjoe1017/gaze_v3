# Verification script for Tauri sidecar binaries
# Checks that all required binaries are present

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir
$BinariesDir = Join-Path $RootDir (Join-Path "app" (Join-Path "src-tauri" "binaries"))

Write-Host "Verifying Tauri sidecar binaries..." -ForegroundColor Cyan
Write-Host "====================================" -ForegroundColor Cyan
Write-Host ""

$AllPresent = $true
$Missing = @()

# Required binaries for Windows
$RequiredBinaries = @(
    "gaze-engine-x86_64-pc-windows-msvc.exe",
    "ffmpeg-x86_64-pc-windows-msvc.exe",
    "ffprobe-x86_64-pc-windows-msvc.exe"
)

foreach ($binary in $RequiredBinaries) {
    $path = Join-Path $BinariesDir $binary
    if (Test-Path $path) {
        $size = (Get-Item $path).Length / 1MB
        $sizeRounded = [math]::Round($size, 2)
        Write-Host "[OK] $binary ($sizeRounded MB)" -ForegroundColor Green
    } else {
        Write-Host "[MISSING] $binary" -ForegroundColor Red
        $Missing += $binary
        $AllPresent = $false
    }
}

Write-Host ""

if (-not $AllPresent) {
    Write-Host "Missing binaries detected!" -ForegroundColor Red
    Write-Host ""
    Write-Host "To fix:" -ForegroundColor Yellow
    Write-Host "1. Engine binary: Run scripts\build-engine.ps1" -ForegroundColor Yellow
    Write-Host "2. FFmpeg binaries: Run scripts\download-ffmpeg-binaries.ps1" -ForegroundColor Yellow
    Write-Host "   Or see: app\src-tauri\binaries\README.md for manual instructions" -ForegroundColor Yellow
    Write-Host ""
    exit 1
} else {
    Write-Host "[SUCCESS] All binaries present and ready for build!" -ForegroundColor Green
    Write-Host ""
    exit 0
}
