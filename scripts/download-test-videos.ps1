# Download test videos from YouTube playlist for performance testing
# Uses yt-dlp to download 100 videos from the playlist

$ErrorActionPreference = "Stop"

# Get script directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir

# Test library directory
$TestLibDir = Join-Path $RootDir "test-library"
$DownloadArchive = Join-Path $TestLibDir "downloaded.txt"

# Playlist URL
$PlaylistUrl = "https://www.youtube.com/playlist?list=PLLd8OpOlwVZs1U_-wTtB00Y-nhX1zIi22"

Write-Host "Downloading test videos for Gaze V3 performance testing..." -ForegroundColor Cyan
Write-Host "Playlist: $PlaylistUrl" -ForegroundColor Yellow
Write-Host "Output directory: $TestLibDir" -ForegroundColor Yellow
Write-Host ""

# Check yt-dlp is installed
Write-Host "Checking yt-dlp..." -ForegroundColor Yellow
try {
    $ytdlpVersion = yt-dlp --version
    Write-Host "yt-dlp version: $ytdlpVersion" -ForegroundColor Green
} catch {
    Write-Host "ERROR: yt-dlp not found. Install it with:" -ForegroundColor Red
    Write-Host "  scoop install yt-dlp" -ForegroundColor Yellow
    Write-Host "  or: pip install yt-dlp" -ForegroundColor Yellow
    exit 1
}

# Create test library directory
if (-not (Test-Path $TestLibDir)) {
    New-Item -ItemType Directory -Path $TestLibDir | Out-Null
    Write-Host "Created test library directory: $TestLibDir" -ForegroundColor Green
}

# Download videos
Write-Host ""
Write-Host "Starting download (this may take a while for 100+ videos)..." -ForegroundColor Cyan
Write-Host ""

yt-dlp `
    -f "bv*+ba/b" `
    --merge-output-format mp4 `
    -o "$TestLibDir/%(uploader)s/%(title)s.%(ext)s" `
    --download-archive $DownloadArchive `
    $PlaylistUrl

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "Download complete!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Cyan
    Write-Host "1. Add library in Gaze V3: $TestLibDir" -ForegroundColor Yellow
    Write-Host "2. Wait for scan to complete" -ForegroundColor Yellow
    Write-Host "3. Click 'Start Indexing' to begin processing" -ForegroundColor Yellow
    Write-Host "4. Monitor progress in the Status Panel" -ForegroundColor Yellow
} else {
    Write-Host ""
    Write-Host "Download failed. Check error messages above." -ForegroundColor Red
    exit 1
}