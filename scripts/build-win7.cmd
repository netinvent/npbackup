@echo off
REM npbackup Windows 7 Legacy Build Script
REM Requirements: Python 3.8.x (x86 or x64) - last version with Win7 support

setlocal enabledelayedexpansion

echo ========================================
echo  npbackup Windows 7 Legacy Builder
echo ========================================
echo.

REM Check Python version
python --version 2>nul
if errorlevel 1 (
    echo ERROR: Python not found in PATH
    echo Please install Python 3.8.x from https://www.python.org/downloads/release/python-3810/
    exit /b 1
)

REM Get Python version and architecture
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VER=%%i
for /f %%i in ('python -c "import struct; print(struct.calcsize('P') * 8)"') do set PYTHON_ARCH=%%i

echo Python version: %PYTHON_VER%
echo Python architecture: %PYTHON_ARCH%-bit
echo.

REM Determine build architecture
if "%PYTHON_ARCH%"=="32" (
    set ARCH=x86
    set RESTIC_PATTERN=restic_*_windows_legacy_386.exe
) else (
    set ARCH=x64
    set RESTIC_PATTERN=restic_*_windows_legacy_amd64.exe
)

echo Build architecture: %ARCH%-legacy
echo.

REM Set paths
set SCRIPT_DIR=%~dp0
set PROJECT_DIR=%SCRIPT_DIR%..
set NPBACKUP_DIR=%PROJECT_DIR%\npbackup

REM Check if npbackup source exists
if not exist "%NPBACKUP_DIR%" (
    echo ERROR: npbackup source not found at %NPBACKUP_DIR%
    echo Please clone the repository first:
    echo   git clone https://github.com/netinvent/npbackup.git "%NPBACKUP_DIR%"
    exit /b 1
)

REM Check for legacy restic binary
dir /b "%NPBACKUP_DIR%\RESTIC_SOURCE_FILES\%RESTIC_PATTERN%" >nul 2>&1
if errorlevel 1 (
    echo ERROR: Legacy restic binary not found!
    echo Expected: %NPBACKUP_DIR%\RESTIC_SOURCE_FILES\%RESTIC_PATTERN%
    exit /b 1
)
echo Legacy restic binary found.
echo.

REM Parse arguments
set BUILD_TYPE=gui
set ONEFILE=--onefile
set AUDIENCE=public

:parse_args
if "%1"=="" goto :args_done
if /i "%1"=="--cli" set BUILD_TYPE=cli
if /i "%1"=="--gui" set BUILD_TYPE=gui
if /i "%1"=="--viewer" set BUILD_TYPE=viewer
if /i "%1"=="--all" set BUILD_TYPE=all
if /i "%1"=="--standalone" set ONEFILE=
if /i "%1"=="--help" goto :show_help
shift
goto :parse_args

:show_help
echo Usage: %~nx0 [options]
echo.
echo Options:
echo   --cli        Build CLI version only
echo   --gui        Build GUI version only (default)
echo   --viewer     Build Viewer version only
echo   --all        Build all versions
echo   --standalone Build standalone (directory) instead of onefile
echo   --help       Show this help
echo.
exit /b 0

:args_done

REM Install/upgrade dependencies
echo Installing dependencies...
python -m pip install --upgrade pip
python -m pip install nuitka ordered-set zstandard
python -m pip install -r "%NPBACKUP_DIR%\npbackup\requirements.txt"

REM Install Windows-specific dependencies
if exist "%NPBACKUP_DIR%\npbackup\requirements-win32.txt" (
    python -m pip install -r "%NPBACKUP_DIR%\npbackup\requirements-win32.txt"
)

echo.
echo ========================================
echo  Starting build: %BUILD_TYPE% (%ARCH%-legacy)
echo ========================================
echo.

cd /d "%NPBACKUP_DIR%"

if /i "%BUILD_TYPE%"=="all" (
    echo Building CLI...
    python bin/compile.py --audience %AUDIENCE% --build-type cli %ONEFILE%
    echo.
    echo Building GUI...
    python bin/compile.py --audience %AUDIENCE% --build-type gui %ONEFILE%
    echo.
    echo Building Viewer...
    python bin/compile.py --audience %AUDIENCE% --build-type viewer %ONEFILE%
) else (
    python bin/compile.py --audience %AUDIENCE% --build-type %BUILD_TYPE% %ONEFILE%
)

if errorlevel 1 (
    echo.
    echo ERROR: Build failed!
    exit /b 1
)

echo.
echo ========================================
echo  Build completed successfully!
echo ========================================
echo.
echo Output location: %NPBACKUP_DIR%\BUILDS\%AUDIENCE%\windows\%ARCH%-legacy\
echo.
dir "%NPBACKUP_DIR%\BUILDS\%AUDIENCE%\windows\%ARCH%-legacy\" 2>nul

endlocal
