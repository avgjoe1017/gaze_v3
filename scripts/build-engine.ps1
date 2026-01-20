# Build script for Gaze Engine (Windows)
# Creates a standalone executable using PyInstaller

$ErrorActionPreference = "Stop"

# Get paths
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir
$EngineDir = Join-Path $RootDir "engine"
$OutputDir = Join-Path $RootDir "app" "src-tauri" "binaries"

Write-Host "Building Gaze Engine..." -ForegroundColor Cyan
Write-Host "Engine dir: $EngineDir" -ForegroundColor Gray
Write-Host "Output dir: $OutputDir" -ForegroundColor Gray

# Check Python
Write-Host "`nChecking Python..." -ForegroundColor Yellow
$pythonVersion = python --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Python not found. Please install Python 3.11+" -ForegroundColor Red
    exit 1
}
Write-Host $pythonVersion -ForegroundColor Gray

# Create virtual environment if needed
$VenvDir = Join-Path $EngineDir ".venv"
if (-not (Test-Path $VenvDir)) {
    Write-Host "`nCreating virtual environment..." -ForegroundColor Yellow
    python -m venv $VenvDir
}

# Activate virtual environment
$ActivateScript = Join-Path $VenvDir "Scripts" "Activate.ps1"
. $ActivateScript

# Install dependencies
Write-Host "`nInstalling Python dependencies..." -ForegroundColor Yellow
Push-Location $EngineDir

# Install package with all extras
pip install -e ".[ml,dev]" --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to install dependencies" -ForegroundColor Red
    Pop-Location
    exit 1
}

# Verify PyInstaller is available
$pyinstallerVersion = pyinstaller --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "PyInstaller not found, installing..." -ForegroundColor Yellow
    pip install pyinstaller
}
Write-Host "PyInstaller: $pyinstallerVersion" -ForegroundColor Gray

# Clean previous builds
Write-Host "`nCleaning previous builds..." -ForegroundColor Yellow
$DistDir = Join-Path $EngineDir "dist"
$BuildDir = Join-Path $EngineDir "build"
if (Test-Path $DistDir) { Remove-Item -Recurse -Force $DistDir }
if (Test-Path $BuildDir) { Remove-Item -Recurse -Force $BuildDir }

# Run PyInstaller
Write-Host "`nRunning PyInstaller..." -ForegroundColor Yellow
pyinstaller gaze-engine.spec --noconfirm
if ($LASTEXITCODE -ne 0) {
    Write-Host "PyInstaller build failed" -ForegroundColor Red
    Pop-Location
    exit 1
}

# Determine output filename
$ExeName = "gaze-engine-x86_64-pc-windows-msvc.exe"
$BuiltExe = Join-Path $DistDir $ExeName

# Verify output exists
if (-not (Test-Path $BuiltExe)) {
    Write-Host "Build failed: $BuiltExe not found" -ForegroundColor Red
    Write-Host "Contents of dist:" -ForegroundColor Yellow
    Get-ChildItem $DistDir
    Pop-Location
    exit 1
}

$ExeSize = (Get-Item $BuiltExe).Length / 1MB
Write-Host "Built: $ExeName ($([math]::Round($ExeSize, 2)) MB)" -ForegroundColor Green

# Create output directory
if (-not (Test-Path $OutputDir)) {
    Write-Host "`nCreating binaries directory..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Path $OutputDir | Out-Null
}

# Copy to output directory
Write-Host "`nCopying to Tauri binaries..." -ForegroundColor Yellow
$DestPath = Join-Path $OutputDir $ExeName
Copy-Item $BuiltExe $DestPath -Force
Write-Host "Copied to: $DestPath" -ForegroundColor Gray

Pop-Location

# Quick verification
Write-Host "`nVerifying executable..." -ForegroundColor Yellow
$TestOutput = & $DestPath --help 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "Executable verified successfully" -ForegroundColor Green
} else {
    Write-Host "Warning: Executable may have issues" -ForegroundColor Yellow
}

Write-Host "`nEngine build complete!" -ForegroundColor Green
Write-Host "Output: $DestPath" -ForegroundColor Cyan
