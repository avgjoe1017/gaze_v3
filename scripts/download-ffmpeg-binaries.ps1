# PowerShell script to download FFmpeg binaries for Windows
# Downloads LGPL builds from gyan.dev

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir
$BinariesDir = Join-Path $RootDir "app\src-tauri\binaries"
New-Item -ItemType Directory -Force -Path $BinariesDir | Out-Null

Write-Host "Downloading FFmpeg binaries for Windows (LGPL builds)..." -ForegroundColor Cyan
Write-Host "=========================================================" -ForegroundColor Cyan
Write-Host ""

# Gyan.dev provides LGPL release builds
# Using the "essentials" build which is LGPL-compliant
$BaseUrl = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
$TempZip = Join-Path $env:TEMP "ffmpeg-essentials.zip"
$TempExtract = Join-Path $env:TEMP "ffmpeg-extract"

try {
    Write-Host "Downloading FFmpeg essentials package..." -ForegroundColor Yellow
    Write-Host "Source: $BaseUrl" -ForegroundColor Gray
    Invoke-WebRequest -Uri $BaseUrl -OutFile $TempZip -UseBasicParsing

    Write-Host "Extracting archive..." -ForegroundColor Yellow
    if (Test-Path $TempExtract) {
        Remove-Item -Recurse -Force $TempExtract
    }
    Expand-Archive -Path $TempZip -DestinationPath $TempExtract -Force

    # Find the bin directory
    $BinPath = Get-ChildItem -Path $TempExtract -Recurse -Directory -Filter "bin" | Select-Object -First 1
    if (-not $BinPath) {
        throw "Could not find bin directory in extracted archive"
    }

    Write-Host ""
    Write-Host "Copying binaries..." -ForegroundColor Yellow

    # Copy and rename FFmpeg
    $SourceFfmpeg = Join-Path $BinPath.FullName "ffmpeg.exe"
    $DestFfmpeg = Join-Path $BinariesDir "ffmpeg-x86_64-pc-windows-msvc.exe"
    if (Test-Path $SourceFfmpeg) {
        Copy-Item -Path $SourceFfmpeg -Destination $DestFfmpeg -Force
        $Size = [math]::Round((Get-Item $DestFfmpeg).Length / 1MB, 2)
        Write-Host "  [OK] ffmpeg.exe -> ffmpeg-x86_64-pc-windows-msvc.exe ($Size MB)" -ForegroundColor Green
    } else {
        throw "ffmpeg.exe not found in extracted archive"
    }

    # Copy and rename FFprobe
    $SourceFfprobe = Join-Path $BinPath.FullName "ffprobe.exe"
    $DestFfprobe = Join-Path $BinariesDir "ffprobe-x86_64-pc-windows-msvc.exe"
    if (Test-Path $SourceFfprobe) {
        Copy-Item -Path $SourceFfprobe -Destination $DestFfprobe -Force
        $Size = [math]::Round((Get-Item $DestFfprobe).Length / 1MB, 2)
        Write-Host "  [OK] ffprobe.exe -> ffprobe-x86_64-pc-windows-msvc.exe ($Size MB)" -ForegroundColor Green
    } else {
        throw "ffprobe.exe not found in extracted archive"
    }

    Write-Host ""
    Write-Host "[SUCCESS] FFmpeg binaries downloaded successfully!" -ForegroundColor Green
    Write-Host "Location: $BinariesDir" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Note: These are LGPL builds from gyan.dev" -ForegroundColor Gray
    Write-Host "License compliance: See THIRD_PARTY_NOTICES.md" -ForegroundColor Gray

} catch {
    Write-Host ""
    Write-Host "[ERROR] $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "Manual download instructions:" -ForegroundColor Yellow
    Write-Host "1. Visit https://www.gyan.dev/ffmpeg/builds/" -ForegroundColor Yellow
    Write-Host "2. Download 'ffmpeg-release-essentials.zip' (LGPL build)" -ForegroundColor Yellow
    Write-Host "3. Extract the archive" -ForegroundColor Yellow
    Write-Host "4. Copy ffmpeg.exe and ffprobe.exe from the 'bin' folder to:" -ForegroundColor Yellow
    Write-Host "   $BinariesDir" -ForegroundColor Cyan
    Write-Host "5. Rename to:" -ForegroundColor Yellow
    Write-Host "   - ffmpeg-x86_64-pc-windows-msvc.exe" -ForegroundColor Yellow
    Write-Host "   - ffprobe-x86_64-pc-windows-msvc.exe" -ForegroundColor Yellow
    Write-Host ""
    exit 1
} finally {
    # Cleanup
    if (Test-Path $TempZip) {
        Remove-Item -Path $TempZip -Force -ErrorAction SilentlyContinue
    }
    if (Test-Path $TempExtract) {
        Remove-Item -Recurse -Force $TempExtract -ErrorAction SilentlyContinue
    }
}
