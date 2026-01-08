# npbackup Windows 7 Legacy Build Script (PowerShell)
# Requirements: Python 3.8.x (x86 or x64) - last version with Win7 support

param(
    [ValidateSet("cli", "gui", "viewer", "all")]
    [string]$BuildType = "gui",

    [switch]$Standalone,

    [ValidateSet("public", "private")]
    [string]$Audience = "public",

    [switch]$Help
)

$ErrorActionPreference = "Stop"

function Write-Header {
    param([string]$Message)
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host " $Message" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
}

function Test-PythonVersion {
    try {
        $version = python --version 2>&1
        if ($LASTEXITCODE -ne 0) { return $false }
        return $true
    } catch {
        return $false
    }
}

function Get-PythonArch {
    return (python -c "import struct; print(struct.calcsize('P') * 8)")
}

if ($Help) {
    Write-Host @"
npbackup Windows 7 Legacy Build Script

Usage: .\build-win7.ps1 [options]

Options:
    -BuildType <type>   Build type: cli, gui, viewer, or all (default: gui)
    -Standalone         Build standalone directory instead of single file
    -Audience <type>    Build audience: public or private (default: public)
    -Help               Show this help message

Examples:
    .\build-win7.ps1                    # Build GUI as single file
    .\build-win7.ps1 -BuildType all     # Build all variants
    .\build-win7.ps1 -Standalone        # Build GUI as standalone directory

Requirements:
    - Python 3.8.x (last version with Windows 7 support)
    - Git (for cloning npbackup if not present)
"@
    exit 0
}

Write-Header "npbackup Windows 7 Legacy Builder"

# Check Python
if (-not (Test-PythonVersion)) {
    Write-Host "ERROR: Python not found in PATH" -ForegroundColor Red
    Write-Host "Please install Python 3.8.x from https://www.python.org/downloads/release/python-3810/"
    exit 1
}

$pythonVersion = (python --version 2>&1).ToString().Split(" ")[1]
$pythonArch = Get-PythonArch

Write-Host "Python version: $pythonVersion"
Write-Host "Python architecture: $pythonArch-bit"

# Determine build architecture
if ($pythonArch -eq "32") {
    $arch = "x86"
    $resticPattern = "restic_*_windows_legacy_386.exe"
} else {
    $arch = "x64"
    $resticPattern = "restic_*_windows_legacy_amd64.exe"
}

Write-Host "Build architecture: $arch-legacy"
Write-Host ""

# Set paths
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectDir = Split-Path -Parent $scriptDir
$npbackupDir = Join-Path $projectDir "npbackup"

# Check if npbackup source exists
if (-not (Test-Path $npbackupDir)) {
    Write-Host "ERROR: npbackup source not found at $npbackupDir" -ForegroundColor Red
    Write-Host "Please clone the repository first:"
    Write-Host "  git clone https://github.com/netinvent/npbackup.git `"$npbackupDir`""
    exit 1
}

# Check for legacy restic binary
$resticDir = Join-Path $npbackupDir "RESTIC_SOURCE_FILES"
$resticFiles = Get-ChildItem -Path $resticDir -Filter $resticPattern -ErrorAction SilentlyContinue

if ($resticFiles.Count -eq 0) {
    Write-Host "ERROR: Legacy restic binary not found!" -ForegroundColor Red
    Write-Host "Expected: $resticDir\$resticPattern"
    exit 1
}

Write-Host "Legacy restic binary found: $($resticFiles[0].Name)" -ForegroundColor Green
Write-Host ""

# Install dependencies
Write-Header "Installing dependencies"

python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { exit 1 }

python -m pip install nuitka ordered-set zstandard
if ($LASTEXITCODE -ne 0) { exit 1 }

$requirementsFile = Join-Path $npbackupDir "npbackup\requirements.txt"
python -m pip install -r $requirementsFile
if ($LASTEXITCODE -ne 0) { exit 1 }

$requirementsWin32 = Join-Path $npbackupDir "npbackup\requirements-win32.txt"
if (Test-Path $requirementsWin32) {
    python -m pip install -r $requirementsWin32
    if ($LASTEXITCODE -ne 0) { exit 1 }
}

# Build
$onefileArg = if ($Standalone) { "" } else { "--onefile" }

function Invoke-Build {
    param([string]$Type)

    Write-Header "Building $Type ($arch-legacy)"

    Push-Location $npbackupDir
    try {
        $args = @("bin/compile.py", "--audience", $Audience, "--build-type", $Type)
        if (-not $Standalone) {
            $args += "--onefile"
        }

        python @args

        if ($LASTEXITCODE -ne 0) {
            Write-Host "ERROR: Build failed for $Type!" -ForegroundColor Red
            return $false
        }
        return $true
    } finally {
        Pop-Location
    }
}

$success = $true

if ($BuildType -eq "all") {
    foreach ($type in @("cli", "gui", "viewer")) {
        if (-not (Invoke-Build -Type $type)) {
            $success = $false
        }
    }
} else {
    if (-not (Invoke-Build -Type $BuildType)) {
        $success = $false
    }
}

if (-not $success) {
    Write-Host ""
    Write-Host "ERROR: One or more builds failed!" -ForegroundColor Red
    exit 1
}

# Show results
Write-Header "Build completed successfully!"

$outputDir = Join-Path $npbackupDir "BUILDS\$Audience\windows\$arch-legacy"

if (Test-Path $outputDir) {
    Write-Host "Output location: $outputDir"
    Write-Host ""
    Get-ChildItem $outputDir | Format-Table Name, Length, LastWriteTime
} else {
    Write-Host "WARNING: Output directory not found: $outputDir" -ForegroundColor Yellow
}
