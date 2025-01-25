:: Example upgrade script for NPBackup that will be pushed server side

:: The following variables will be overwritten by the upgrade process
:: {CURRENT_DIR}    - The current directory of the distribution
:: {backup_dist}    - A directory where we try to move / copy the current distribution
:: {upgrade_dist}   - The directory where the new distribution is extracted to after download
:: {log_file}       - The log file where the output of this script will be written
:: {original_args}  - The arguments that were passed to the upgrade script


echo "Launching upgrade" >> "{log_file}" 2>&1
echo "Moving current dist from {CURRENT_DIR} to {backup_dist}" >> "{log_file}" 2>&1
mv -f "{CURRENT_DIR}" "{backup_dist}" >> "{log_file}" 2>&1
echo "Moving upgraded dist from {upgrade_dist} to {CURRENT_DIR}" >> "{log_file}" 2>&1
mv -f "{upgrade_dist}" "{CURRENT_DIR}" >> "{log_file}" 2>&1
echo "Copying optional configuration files from {backup_dist} to {CURRENT_DIR}" >> "{log_file}" 2>&1
find "{backup_dist}" -name "*.conf" -exec cp --parents "{}" "{CURRENT_DIR}" \;
echo "Adding executable bit to new executable" >> "{log_file}" 2>&1
chmod +x "{CURRENT_EXECUTABLE}" >> "{log_file}" 2>&1
echo "Loading new executable {CURRENT_EXECUTABLE} --run-as-cli --check-config {original_args}" >> "{log_file}" 2>&1
"{CURRENT_EXECUTABLE}" --run-as-cli --check-config {orignal_orgs} >> "{log_file}" 2>&1
if [ $? -ne 0 ]; then
    echo "New executable failed. Rolling back" >> "{log_file}" 2>&1
    mv -f "{CURRENT_DIR}" "{backup_dist}.original">> "{log_file}" 2>&1
    mv -f "{backup_dist}" "{CURRENT_DIR}" >> "{log_file}" 2>&1
else 
    echo "Upgrade successful" >> "{log_file}" 2>&1
    rm -rf "{backup_dist}" >> "{log_file}" 2>&1
    rm -rf "{upgrade_dist}" >> "{log_file}" 2>&1
    rm -rf "{downloaded_archive}" >> "{log_file}" 2>&1
fi
echo "Running as initially planned:" >> "{log_file}" 2>&1
echo "{CURRENT_EXECUTABLE} {original_args}" >> "{log_file}" 2>&1
"{CURRENT_EXECUTABLE}" {original_args}
echo "Upgrade script run finished" >> "{log_file}" 2>&1