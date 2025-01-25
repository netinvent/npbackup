:: Example upgrade script for NPBackup that will be pushed server side

:: The following variables will be overwritten by the upgrade process
:: {CURRENT_DIR}    - The current directory of the distribution
:: {backup_dist}    - A directory where we try to move / copy the current distribution
:: {upgrade_dist}   - The directory where the new distribution is extracted to after download
:: {log_file}       - The log file where the output of this script will be written
:: {original_args}  - The arguments that were passed to the upgrade script

:: Also, I really HATE batch files, from the bottom of my programmer heart
:: Every try to write a one-liner batch with some variables and perhaps if statements ?
:: With or without setlocal enabledelayedexpansion, you won't get what you want, it's a nightmare
:: eg command & IF %ERRORLEVEL% EQU 0 (echo "Success") ELSE (echo "Failure")
:: Run this a couple of times with good and bad exit code commands and you'll see the "memory" of previous runs
:: Also, using !ERRORLEVEL! produces another type of "memory"
:: So here we are, in GOTO land, like in the good old Commodore 64 days

echo "Launching upgrade" >> "{log_file}" 2>&1
echo "Moving current dist from {CURRENT_DIR} to {backup_dist}" >> "{log_file}" 2>&1
move /Y "{CURRENT_DIR}" "{backup_dist}" >> "{log_file}" 2>&1 || GOTO MOVE_FAILED
GOTO MOVE_OK
:: MOVE_FAILED
echo "Moving current dist failed. Trying to copy it." >> "{log_file}" 2>&1
xcopy /S /Y /I "{CURRENT_DIR}\*" "{backup_dist}" >> "{log_file}" 2>&1
echo "Now trying to overwrite current dist with upgrade dist" >> "{log_file}" 2>&1
xcopy /S /Y /I "{upgrade_dist}\*" "{CURRENT_DIR}" >> "{log_file}" 2>&1
GOTO TESTRUN
:: MOVE_OK
echo "Moving upgraded dist from {upgrade_dist} to {CURRENT_DIR}" >> "{log_file}" 2>&1
move /Y "{upgrade_dist}" "{CURRENT_DIR}" >> "{log_file}" 2>&1
echo "Copying optional configuration files from {backup_dist} to {CURRENT_DIR}" >> "{log_file}" 2>&1
xcopy /S /Y /I "{backup_dist}\*conf" {CURRENT_DIR} > NUL 2>&1
GOTO TESTRUN
:: TESTRUN
echo "Loading new executable {CURRENT_EXECUTABLE} --run-as-cli --check-config {original_args}" >> "{log_file}" 2>&1
"{CURRENT_EXECUTABLE}" --run-as-cli --check-config {original_args} >> "{log_file}" 2>&1 || GOTO FAILED_TEST_RUN
GOTO RUN_AS_PLANNED
:: FAILED_TEST_RUN
echo "New executable failed. Rolling back" >> "{log_file}" 2>&1
echo "Trying to move back" >> "{log_file}" 2>&1
move /Y "{CURRENT_DIR}" "{backup_dist}.original" >> "{log_file}" 2>&1 || GOTO MOVE_BACK_FAILED
move /Y "{backup_dist}" "{CURRENT_DIR}" >> "{log_file}" 2>&1
GOTO RUN_AS_PLANNED
:: MOVE_BACK_FAILED
echo "Moving files back failed. Trying to overwrite" >> "{log_file}" 2>&1
xcopy /S /Y /I "{backup_dist}\*" "{CURRENT_DIR}" >> "{log_file}" 2>&1
GOTO RUN_AS_PLANNED
:: RUN_AS_PLANNED
echo "Upgrade successful" >> "{log_file}" 2>&1
rd /S /Q "{backup_dist}" >> "{log_file}" 2>&1
rd /S /Q "{upgrade_dist}" > NUL 2>&1
del /F /S /Q "{downloaded_archive}" >> "{log_file}" 2>&1
echo "Running as initially planned:" >> "{log_file}" 2>&1
echo "{CURRENT_EXECUTABLE} {original_args}" >> "{log_file}" 2>&1
"{CURRENT_EXECUTABLE}" {original_args}
echo "Upgrade script run finished" >> "{log_file}" 2>&1