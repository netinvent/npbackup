@echo off

setlocal

if exist "%~dp0..\python.exe" (
"%~dp0..\python" -m npbackup %*
) else if exist "%~dp0python.exe" (
"%~dp0python" -m npbackup %*
) else (
"python" -m npbackup %*
)

endlocal
