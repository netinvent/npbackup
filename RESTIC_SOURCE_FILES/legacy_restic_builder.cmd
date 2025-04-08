@echo off

:: Blatantly copied from https://github.com/restic/restic/issues/4636#issuecomment-1896455557


SET RESTIC_VERSION=0.18.0

set RESTIC_URL=https://github.com/restic/restic/releases/download/v%RESTIC_VERSION%/restic-%RESTIC_VERSION%.tar.gz
set GO_BIN_URL=https://go.dev/dl/go1.21.3.windows-amd64.zip
set GO_SRC_URL=https://go.dev/dl/go1.21.6.src.tar.gz
set BAD_COMMIT_URL=https://github.com/golang/go/commit/9e43850a3298a9b8b1162ba0033d4c53f8637571.diff
set BUSYBOX_URL=https://frippery.org/files/busybox/busybox64.exe
set BUSYBOX="%~dp0busybox64.exe"
if not exist %BUSYBOX% powershell -Command (New-Object System.Net.WebClient^).DownloadFile('"%BUSYBOX_URL%"','"%BUSYBOX%"'^)
if not exist go1.*.windows-amd64.zip (%BUSYBOX% wget %GO_BIN_URL% || GOTO ERROR)
if not exist go (%BUSYBOX% unzip -q go1.*.windows-amd64.zip || GOTO ERROR)
if not exist go1.*.src.tar.gz (%BUSYBOX% wget %GO_SRC_URL% || GOTO ERROR)
if not exist src (md src && %BUSYBOX% tar x -z --strip-components 1 -C src -f go1.*.src.tar.gz || GOTO ERROR)
pushd src
if not exist *.diff (%BUSYBOX% wget %BAD_COMMIT_URL% && %BUSYBOX% patch -p 1 -R -i *.diff || GOTO ERROR)
pushd src
if not exist ..\bin\go.exe (set GOROOT_BOOTSTRAP=%~dp0go&& call make.bat || GOTO ERROR)
popd && popd
if not exist restic-%RESTIC_VERSION%.tar.gz (%BUSYBOX% wget %RESTIC_URL% || GOTO ERROR)
if not exist restic-%RESTIC_VERSION% (md restic-%RESTIC_VERSION% && %BUSYBOX% tar x -z --strip-components 1 -C restic-%RESTIC_VERSION% -f restic-%RESTIC_VERSION%.tar.gz || GOTO ERROR)
set GOARCH=amd64
pushd restic-%RESTIC_VERSION% && set path=%~dp0\src\bin&& go.exe run build.go && move /y restic.exe ../restic_%RESTIC_VERSION%_windows_legacy_%GOARCH%.exe && popd
set GOARCH=386
pushd restic-%RESTIC_VERSION% && set path=%~dp0\src\bin&& go.exe run build.go && move /y restic.exe ../restic_%RESTIC_VERSION%_windows_legacy_%GOARCH%.exe && popd
GOTO END

:ERROR
echo Build failure
GOTO EXIT

:END
echo Build success
GOTO EXIT

:EXIT
::exit /b 1