#!/usr/bin/env bash

# Script ver 2025062501

#TODO: blockcommit removes current snapshots, even if not done by cube
#      - it's interesting to make housekeeping, let's make this an option

# List of machines
# All active machines by default, adding --all includes inactive machines
VMS=$(virsh list --name --all)

# Optional manual machine selection
#VMS=(some.vm.local some.other.vm.local)

EXCLUDE_VMS=(some_lab_vm.local some_other_non_to_backup_vm.local)

DEFAULT_TAG=retention3y
SPECIAL_TAG=retention30d
SPECIAL_TAG_VMS=(some.vm.local some.other.vm.local)



LOG_FILE="/var/log/cube_npv2.log"
ROOT_DIR="/opt/cube"
BACKUP_IDENTIFIER="CUBE-BACKUP-NP.$(date +"%Y%m%dT%H%M%S" --utc)"
BACKUP_FILE_LIST="${ROOT_DIR}/npbackup_cube_file.lst"
NPBACKUP_EXECUTABLE="/usr/local/bin/npbackup-cli/npbackup-cli"
NPBACKUP_CONF_FILE_TEMPLATE="${ROOT_DIR}/npbackup-cube.conf.template"
NPBACKUP_CONF_FILE="${ROOT_DIR}/npbackup-cube.conf"
SNAPSHOT_FAILED_FILE="${ROOT_DIR}/SNAPSHOT_FAILED"

# Supersede tenants if this is set, else it is extracted from machine name, eg machine.tenant.something
# TENANT_OVERRIDE=netperfect
# default tenant if extraction of tenant name failed
DEFAULT_TENANT=netperfect

# Force libvirt to talk in parseable english
export LANG=C

SCRIPT_ERROR=false

function log {
        local line="${1}"
        local level="${2}"

        echo "${line}" >> "${LOG_FILE}"
        echo "${line}"

        if [ "${level}" == "ERROR" ]; then
                SCRIPT_ERROR=true
        fi
}

function ArrayContains () {
        local needle="${1}"
        local haystack="${2}"
        local e

        if [ "$needle" != "" ] && [ "$haystack" != "" ]; then
                for e in "${@:2}"; do
                        if [ "$e" == "$needle" ]; then
                                echo 1
                                return
                        fi
                done
        fi
        echo 0
        return
}

function create_snapshot {
        local vm="${1}"
        local backup_identifier="${2}"

        # Ignore SC2068 here
        # Add VM xml description from virsh
        ## At least use a umask


        # Don't redirect direct virsh output or SELinux may complain that we cannot write with virsh context
        xml=$(virsh dumpxml --security-info $vm || log "Failed to create XML file" "ERROR")
        echo "${xml}" > "${ROOT_DIR}/${vm}.xml"
        echo "${ROOT_DIR}/${vm}.xml" >> "$BACKUP_FILE_LIST"

        # Get current disk paths to include into snapshot
        for disk_path in $(virsh domblklist $vm --details | grep file | grep disk | awk '{print $4}'); do
        if [ -f "${disk_path}" ]; then
                        # Add current disk path and all necessary backing files for current disk to backup file list
                        echo "${disk_path}" >> "$BACKUP_FILE_LIST"
                        qemu-img info --backing-chain -U "$disk_path" | grep "backing file:" | awk '{print $3}' >> "$BACKUP_FILE_LIST"
                        log "Current disk path: $disk_path"
                else
                        log "$vm has a non existent disk path: $disk_path. Cannot backup this disk"
                        # Let's still include this file in the backup list so we are sure backup will be marked as failed
                        echo "${disk_path}" >> "$BACKUP_FILE_LIST"
                fi
        done

        if [ "$(virsh domstate $vm)" == "shut off" ]; then
                log "Domain is not running, no need for snapshots"
                return
        fi

        log "Creating snapshot for $vm"
        rm -f "${SNAPSHOT_FAILED_FILE}" > /dev/null 2>&1
        virsh snapshot-create-as $vm --name "${backup_identifier}" --description "${backup_identifier}" --atomic --quiesce --disk-only >> "$LOG_FILE" 2>&1
        if [ $? -ne 0 ]; then
                log "Failed to create snapshot for $vm with quiesce option. Trying without quiesce. Data will be nonconsistent"
                virsh snapshot-create-as $vm --name "${backup_identifier}" --description "${backup_identifier}.noquiesce" --atomic --disk-only >> "$LOG_FILE" 2>&1
                if [ $? -ne 0 ]; then
                        log "Failed to create snapshot for $vm without quiesce option. Backup will be done, but data will be nonconsistent and perhaps unusable." "ERROR"
                        echo "$vm" > "${SNAPSHOT_FAILED_FILE}"
                else
                        CURRENT_VM_SNAPSHOT="${vm}"
                fi
        else
                CURRENT_VM_SNAPSHOT="${vm}"
        fi
        # Get list of snapshot files to delete "make sure we only use CUBE backup files here, since they are to be deleted later
        for disk_path in $(virsh domblklist $vm --details | grep file | grep disk |grep "${backup_identifier}" | awk '{print $4}'); do
                SNAPSHOTS_PATHS+=($disk_path)
                log "Snapshotted disk path: $disk_path"
        done
}

function get_tenant {
        local vm="${1}"

        if [ -n "${TENANT_OVERRIDE}" ]; then
                echo "${TENANT_OVERRIDE}"
                return
        fi

        # $(NF-1) means last column -1
        npf_tenant=$(echo ${vm} |awk -F'.' '{print $(NF-1)}')
        if [ "${npf_tenant}" == "npf" ]; then
                npf_tenant="netperfect"
        fi

        if [ -z "${npf_tenant}" ]; then
                npf_tenant="${DEFAULT_TENANT}"
        fi

        # return this
        echo "${npf_tenant}"
}

function run_backup {
        local tenant="${1}"
        local vm="${2}"

        log "Running backup for:" >> "$LOG_FILE" 2>&1
        cat  "$BACKUP_FILE_LIST" >> "$LOG_FILE" 2>&1
        log "Running backup as ${tenant} for:"
        cat  "$BACKUP_FILE_LIST"
        # Run backups
        #/usr/local/bin/restic backup --compression=auto --files-from-verbatim "${BACKUP_FILE_LIST}" --tag "${backup_identifier}" -o rest.connections=15 -v >> "$LOG_FILE" 2>&1
        # Prepare config file
        rm -f "${NPBACKUP_CONF_FILE}"
        cp "${NPBACKUP_CONF_FILE_TEMPLATE}" "${NPBACKUP_CONF_FILE}"
        sed -i "s%___TENANT___%${tenant}%g" "${NPBACKUP_CONF_FILE}"
        sed -i "s%___SOURCE___%${BACKUP_FILE_LIST}%g" "${NPBACKUP_CONF_FILE}"
        sed -i "s%___VM___%${vm}%g" "${NPBACKUP_CONF_FILE}"

        if [ $(ArrayContains "$vm" "${SPECIAL_TAG_VMS[@]}") -eq 0 ]; then
                log "Changing tag for $vm to $SPECIAL_TAG"
                tags="${SPECIAL_TAG}"
        else
                tags="${DEFAULT_TAG}"
        fi
        sed -i "s%___TAG___%${tags}%" "${NPBACKUP_CONF_FILE}"

        "${NPBACKUP_EXECUTABLE}" --config-file "${NPBACKUP_CONF_FILE}" --backup --force >> "$LOG_FILE" 2>&1
        if [ $? -ne 0 ]; then
                log "Backup failure" "ERROR"
        else
                log "Backup success"
        fi
}

function remove_snapshot {
        local vm="${1}"
        local backup_identifier="${2}"

        can_delete_metadata=true
        for disk_name in $(virsh domblklist $vm --details | grep file | grep disk | grep "${backup_identifier}" | awk '{print $3}'); do
                disk_path=$(virsh domblklist $vm --details | grep file | grep disk | grep "${backup_identifier}" | grep "${disk_name}" | awk '{print $4}')
                if [ $(ArrayContains "$disk_path" "${SNAPSHOTS_PATHS[@]}") -eq 0 ]; then
                        log "No snapshot found for $vm"
                fi

                # virsh blockcommit only works if machine is running, else we need to use qemu-img
                if [ "$(virsh domstate $vm)" == "running" ]; then
                        log "Trying to online blockcommit for $disk_name: $disk_path"
                        virsh blockcommit $vm "$disk_name" --active --pivot --verbose --delete >> "$LOG_FILE" 2>&1
                else
                        log "Trying to offline blockcommit for $disk_name: $disk_path"
                        # -p = progress, we actually don't need that hee
                        qemu-img commit -dp "$disk_path" >> "$LOG_FILE" 2>&1
                        log "Note that you will need to modify the XML manually"

                        # virsh snapshot delete will erase committed file if exist so we don't need to manually tamper with xml file
                        virsh snapshot-delete --current $vm
                        # TODO: test2
                        #virsh dumpxml --inactive --security-info "$vm" > "${ROOT_DIR}/$vm.xml.temp"
                        #sed -i "s%${backup_identifier}//g" "${ROOT_DIR}/$vm.xml.temp"
                        #virsh define "${ROOT_DIR}/$vm.xml.temp"
                        #rm -f "${ROOT_DIR}/$vm.xml.temp"

                        ##TODO WE NEED TO UPDATE DISK PATH IN XML OF OFFLINE FILE
                fi
                if [ $? -ne 0 ]; then
                        log "Failed to flatten snapshot $vm: $disk_name: $disk_path"
                        can_delete_metadata=false
                else
                        # Delete if disk is not in use
                        if [ -f "$disk_path" ]; then
                                log "Trying to delete $disk_path"
                                if ! lsof "$disk_path" > /dev/null 2>&1; then
                                        log "Deleting file ${disk_path}"
                                        rm -f "$disk_path"
                                else
                                        log "File $disk_path is in use"
                                fi
                        fi
                        CURRENT_VM_SNAPSHOT=""
                fi
        done

        # delete snapshot metadata
        if [ $can_delete_metadata == true ]; then
                log "Deleting metadata from snapshot ${backup_identifier} for $vm"
                virsh snapshot-delete $vm --snapshotname "${backup_identifier}" --metadata >> "$LOG_FILE" 2>&1
                if [ $? -ne 0 ]; then
                        log "Cannot delete snapshot metadata for $vm: ${backup_identifier}" "ERROR"
                fi
        else
                log "Will not delete metadata from snapshot ${backup_identifier} for $vm"
        fi
}


function run {
        for vm in ${VMS[@]}; do
                # Empty file
                : > "$BACKUP_FILE_LIST"

                if [ $(ArrayContains "$vm" "${EXCLUDE_VMS[@]}") -eq 0 ]; then
                        log "Not backing up $vm due to being in exclusion list"
                fi

                CURRENT_VM_SNAPSHOT=""

                log "Running backup for ${vm}"
                SNAPSHOTS_PATHS=()
                create_snapshot "${vm}" "${BACKUP_IDENTIFIER}"
                npf_tenant=$(get_tenant "${vm}")
                run_backup "${npf_tenant}" "${vm}"
                if [ "${CURRENT_VM_SNAPSHOT}" != "" ]; then
                        remove_snapshot "${CURRENT_VM_SNAPSHOT}" "${BACKUP_IDENTIFIER}"
                fi
                log "Delete former XML file"
                rm -f "${ROOT_DIR}/${vm}.xml" > /dev/null 2>&1
                rm -f "${SNAPSHOT_FAILED_FILE}" > /dev/null 2>&1
        done
}

function cleanup {
        if [ "${CURRENT_VM_SNAPSHOT}" != "" ]; then
                remove_snapshot "${CURRENT_VM_SNAPSHOT}" "${BACKUP_IDENTIFIER}"
        fi
        exit
}



function main {
        # Make sure we remove snapshots no matter what
        trap 'cleanup' INT HUP TERM QUIT ERR EXIT

        log "#### Make sure all template variables are encrypted"
        "${NPBACKUP_EXECUTABLE}" -c "${NPBACKUP_CONF_FILE_TEMPLATE}" --check-config-file

        log "#### Running backup `date`"

        [ ! -d "${ROOT_DIR}" ] && mkdir "${ROOT_DIR}"
        run

        if [ "${SCRIPT_ERROR}" == true ]; then
                log "Backup operation failed."
        else
                log "Backup finished."
        fi
        # Prune old backups ?
        # No, done remotely since we use --append-only
}

# SCRIPT ENTRY POINT
main
