@echo off

:: Blatantly copied from https://gist.github.com/DRON-666/6e29eb6a8635fae9ab822782f34d8fd6
:: with some mods to specify restic versions and produce both 32 and 64 bit executables
:: Runs on Win10+ and provides restic binaries for Win7 without the need to rampup all intermediate go compilers

SET RESTIC_VERSION=0.18.1
SET GO_BINARIES_VERSION=1.25.6

SET LOG_FILE=%~n0.log
SET BUILD_DIR=%~dp0BUILD
IF NOT EXIST "%BUILD_DIR%" MKDIR "%BUILD_DIR%" || GOTO ERROR
PUSHD BUILD

set RESTIC_URL=https://github.com/restic/restic/releases/download/v%RESTIC_VERSION%/restic-%RESTIC_VERSION%.tar.gz
set GO_BINARIES_VERSION=https://go.dev/dl/go%GO_BINARIES_VERSION%.windows-amd64.zip
set PATCH_URL=https://gist.github.com/DRON-666/6e29eb6a8635fae9ab822782f34d8fd6/raw/win7sup25.diff
set BUSYBOX_URL=https://frippery.org/files/busybox/busybox64.exe
set BUSYBOX="%BUILD_DIR%\busybox64.exe"
set GOTOOLCHAIN=local

call:Log "Running legacy restic builder"

call:Log "Fetching busybox"
if not exist %BUSYBOX% (powershell -Command (New-Object System.Net.WebClient^).DownloadFile('"%BUSYBOX_URL%"','%BUSYBOX%'^) || GOTO ERROR)
call:Log "Fetching GO %GO_BINARIES_VERSION% compiler"
call:process %GO_BINARIES_VERSION% %BUILD_DIR%\go %PATCH_URL%
call:Log "Fetching restic %RESTIC_VERSION% sources"
call:process %RESTIC_URL% restic-%RESTIC_VERSION%

call:build_restic 386
call:build_restic amd64
goto END

:GetTime
:: US Date /T returns Day MM/DD/YYYY whereas other languages may DD/MM/YYYY, Try to catch both
FOR /F "tokens=1,2,3,4 delims=/" %%a IN ('Date /T') DO (
IF "%%d"=="" set now_date=%%a-%%b-%%c
IF NOT "%%d"=="" set now_date=%%a-%%b-%%c-%%d
)
set now_time=%TIME:~0,2%:%TIME:~3,2%:%TIME:~6,2%
set start_date=%now_date%-%TIME:~0,2%_%TIME:~3,2%_%TIME:~6,2%
GOTO:EOF

:Log
call:GetTime
echo %now_date% - %now_time% %~1 >> "%LOG_FILE%"
IF "%DEBUG%"=="yes" echo %~1
GOTO:EOF

:process
:: Download and extract archives
if not exist %~nx1 (%BUSYBOX% wget %~1 || GOTO ERROR)
if not exist %~2 if /I "%~x1"==".zip" (%BUSYBOX% unzip -q %~nx1 || GOTO ERROR) else (md %~2 && %BUSYBOX% tar x -z --strip-components 1 -C %~2 -f %~nx1 || GOTO ERROR)
if "%~3"=="" goto :EOF
:: Patch go sources
if not exist %~nx3 (%BUSYBOX% wget %~3 || GOTO ERROR)
if not exist %~2\patched (pushd %~2 && %BUSYBOX% patch -p 0 -i "%BUILD_DIR%\%~nx3" && %BUSYBOX% sed -E -i "s/^go1.+[0-9]$/\0-win7sup/" VERSION && md patched && popd || GOTO ERROR)
:: Build go from sources - Don't put a space between '%4' and '&&' or else it will be interpreted as fullpath
if not exist %~2\bin\go.exe (pushd %~2\src && set GOROOT_BOOTSTRAP=%4&& call make.bat &&  popd || GOTO ERROR)
GOTO:EOF

:build_restic
set GOOS=windows
if NOT "%~1"=="" SET GOARCH=%~1
call:Log "Building restic %RESTIC_VERSION% %GOARCH% with Windows 7 Support"
:: Setting path without previous paths prevents further runs and calling binaries like powershell
set PATH=%BUILD_DIR%\go\bin;%PATH%
if not exist restic_%RESTIC_VERSION%_windows_legacy_%GOARCH%.exe (PUSHD %BUILD_DIR%\restic-%RESTIC_VERSION% && go.exe run build.go && move /y restic.exe ../restic_%RESTIC_VERSION%_windows_legacy_%GOARCH%.exe && popd || GOTO ERROR)
restic_%RESTIC_VERSION%_windows_legacy_%GOARCH%.exe version
GOTO:EOF

:ERROR
call:Log "Build failure"
GOTO EXIT

:END
call:Log "Build success"
GOTO EXIT

:EXIT
POPD
::exit /b 1