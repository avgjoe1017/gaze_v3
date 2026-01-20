# Development script for Windows
# Starts both the Python engine and Tauri dev server

$ErrorActionPreference = "Stop"

# Get script directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir

Write-Host "Starting Gaze V3 development environment..." -ForegroundColor Cyan

# Check Python
Write-Host "Checking Python..." -ForegroundColor Yellow
python --version
if ($LASTEXITCODE -ne 0) {
    Write-Host "Python not found. Please install Python 3.11+" -ForegroundColor Red
    exit 1
}

# Install Python dependencies
Write-Host "Installing Python dependencies..." -ForegroundColor Yellow
Push-Location "$RootDir\engine"
pip install -e . --quiet
Pop-Location

# Check Node
Write-Host "Checking Node.js..." -ForegroundColor Yellow
node --version
if ($LASTEXITCODE -ne 0) {
    Write-Host "Node.js not found. Please install Node.js 18+" -ForegroundColor Red
    exit 1
}

# Install npm dependencies
Write-Host "Installing npm dependencies..." -ForegroundColor Yellow
Push-Location "$RootDir\app"
npm install --silent
Pop-Location

# Check Rust/Cargo (required for Tauri)
Write-Host "Checking Rust/Cargo..." -ForegroundColor Yellow
# Refresh PATH to include Scoop and cargo paths (if not already loaded)
$userPath = [System.Environment]::GetEnvironmentVariable("PATH", "User")
if ($userPath) {
    $env:PATH = "$userPath;$env:PATH"
}

$cargoCmd = Get-Command cargo -ErrorAction SilentlyContinue
if (-not $cargoCmd) {
    Write-Host "Rust/Cargo not found. Please install Rust:" -ForegroundColor Red
    Write-Host "  Windows: Download rustup-init.exe from https://rustup.rs/" -ForegroundColor Yellow
    Write-Host "  Or use: scoop install rust" -ForegroundColor Yellow
    Write-Host "  After installation, restart your terminal and try again." -ForegroundColor Yellow
    exit 1
}
$cargoVersion = cargo --version
Write-Host $cargoVersion

# Create engine stub for development (real binary not needed in dev mode)
Write-Host "Ensuring engine stub exists for Tauri build..." -ForegroundColor Yellow
$BinaryDir = Join-Path $RootDir "app" "src-tauri" "binaries"
$StubPath = Join-Path $BinaryDir "gaze-engine-x86_64-pc-windows-msvc.exe"
if (-not (Test-Path $BinaryDir)) {
    New-Item -ItemType Directory -Path $BinaryDir | Out-Null
}
if (-not (Test-Path $StubPath)) {
    # Create a minimal valid Windows PE executable (just enough to pass Tauri's check)
    # In dev mode, Python is used instead of this binary
    Write-Host "Creating development stub..." -ForegroundColor Yellow
    $minimalPE = [byte[]]@(
        0x4D, 0x5A, 0x90, 0x00, 0x03, 0x00, 0x00, 0x00, 0x04, 0x00, 0x00, 0x00, 0xFF, 0xFF, 0x00, 0x00,
        0xB8, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x40, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x80, 0x00, 0x00, 0x00,
        0x0E, 0x1F, 0xBA, 0x0E, 0x00, 0xB4, 0x09, 0xCD, 0x21, 0xB8, 0x01, 0x4C, 0xCD, 0x21, 0x44, 0x65,
        0x76, 0x20, 0x73, 0x74, 0x75, 0x62, 0x24, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
    )
    [System.IO.File]::WriteAllBytes($StubPath, $minimalPE)
    Write-Host "Dev stub created at: $StubPath" -ForegroundColor Gray
}

# Start Tauri dev server (which will also start the engine via commands)
Write-Host "Starting Tauri dev server..." -ForegroundColor Green
Push-Location "$RootDir\app"
npm run tauri dev
Pop-Location
