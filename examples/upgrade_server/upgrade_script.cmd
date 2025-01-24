:: Example upgrade script for NPBackup that will be pushed server side

:: The following variables will be overwritten by the upgrade process
:: {CURRENT_DIR}    - The current directory of the distribution
:: {backup_dist}    - A directory where we try to move / copy the current distribution
:: {upgrade_dist}   - The directory where the new distribution is extracted to after download
:: {log_file}       - The log file where the output of this script will be written
:: {original_args}  - The arguments that were passed to the upgrade script


setlocal EnableDelayedExpansion
echo "Launching upgrade" >> "{log_file}" 2>&1
echo "Moving current dist from {CURRENT_DIR} to {backup_dist}" >> "{log_file}" 2>&1
move /Y "{CURRENT_DIR}" "{backup_dist}" >> "{log_file}" 2>&1
IF !ERRORLEVEL! NEQ 0 (
    echo "Moving current dist failed. Trying to copy it." >> "{log_file}" 2>&1
    xcopy /S /Y /I "{CURRENT_DIR}\*" "{backup_dist}" >> "{log_file}" 2>&1
    echo "Now trying to overwrite current dist with upgrade dist" >> "{log_file}" 2>&1
    xcopy /S /Y /I "{upgrade_dist}\*" "{CURRENT_DIR}" >> "{log_file}" 2>&1
    set REPLACE_METHOD=overwrite
) ELSE (
    echo "Moving upgraded dist from {upgrade_dist} to {CURRENT_DIR}" >> "{log_file}" 2>&1
    move /Y "{upgrade_dist}" "{CURRENT_DIR}" >> "{log_file}" 2>&1
    echo "Copying optional configuration files from {backup_dist} to {CURRENT_DIR}" >> "{log_file}" 2>&1
    xcopy /S /Y /I "{backup_dist}\*conf" {CURRENT_DIR} > NUL 2>&1
    set REPLACE_METHOD=move
)

echo "Loading new executable {CURRENT_EXECUTABLE} --check-config {original_args}" >> "{log_file}" 2>&1
"{CURRENT_EXECUTABLE}" --check-config {original_args} >> "{log_file}" 2>&1
IF !ERRORLEVEL! NEQ 0 (
    echo "New executable failed. Rolling back" >> "{log_file}" 2>&1
    IF "%REPLACE_METHOD%"=="overwrite" echo "Overwrite method used. Overwrite back" >> "{log_file}" 2>&1
    IF "%REPLACE_METHOD%"=="overwrite" xcopy /S /Y /I "{backup_dist}\*" "{CURRENT_DIR}" >> "{log_file}" 2>&1

    IF NOT "%REPLACE_METHOD%"=="overwrite" echo "Move method used. Move back" >> "{log_file}" 2>&1
    IF NOT "%REPLACE_METHOD%"=="overwrite" rd /S /Q "{CURRENT_DIR}" >> "{log_file}" 2>&1 &
    IF NOT "%REPLACE_METHOD%"=="overwrite" move /Y "{backup_dist}" "{CURRENT_DIR}" >> "{log_file}" 2>&1
) ELSE (
    echo "Upgrade successful" >> "{log_file}" 2>&1
    rd /S /Q "{backup_dist}" >> "{log_file}" 2>&1
    :: f'rd /S /Q "{upgrade_dist}" >> "{log_file}" 2>&1 # Since we move this, we don't need to delete it
    del /F /S /Q "{downloaded_archive}" >> "{log_file}" 2>&1
    echo "Running new version as planned:" >> "{log_file}" 2>&1
    echo "{CURRENT_EXECUTABLE} {original_args}" >> "{log_file}" 2>&1
    "{CURRENT_EXECUTABLE}" {original_args}'
)
echo "Upgrade script run finished" >> "{log_file}" 2>&1