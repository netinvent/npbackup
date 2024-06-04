#!/usr/bin/env bash

# Script to create KVM snapshots using libvirt
# Have npbackup backup the qcow2 file + the xml file of the VM
# then have the script erase the snapshot

# Script ver 2024060401 for NPBackup V3

#TODO: support modding XML file from offline domains to remove snapshot and replace by backing file after qemu-img commit

# Expects repository version 2 to already exist

# List of machines

# All active machines by default, adding --all includes inactive machines
VMS=$(virsh list --name --all)
# Optional machine selection
#VMS=(some.vm.local some.other.vm.local)

LOG_FILE="/var/log/cube_npv1.log"
ROOT_DIR="/opt/cube"
BACKUP_IDENTIFIER="CUBE-BACKUP-NP.$(date +"%Y%m%dT%H%M%S" --utc)"
BACKUP_FILE_LIST="${ROOT_DIR}/npbackup_cube_file.lst"
NPBACKUP_CONF_FILE_TEMPLATE="${ROOT_DIR}/npbackup.cube.template"
NPBACKUP_CONF_FILE="${ROOT_DIR}/npbackup-cube.conf"
NPBACKUP_EXECUTABLE="/usr/local/bin/npbackup-cli/npbackup-cli"

function log {
        local line="${1}"

        echo "${line}" >> "${LOG_FILE}"
        echo "${line}"
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
        virsh dumpxml --security-info $vm > "${ROOT_DIR}/$vm.xml"
        echo "${ROOT_DIR}/$vm.xml" >> "$BACKUP_FILE_LIST"

        # Get current disk paths
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
        log "Creating snapshot for $vm"
        virsh snapshot-create-as $vm --name "${backup_identifier}" --description "${backup_identifier}" --atomic --quiesce --disk-only >> "$LOG_FILE" 2>&1
        if [ $? -ne 0 ]; then
                log "Failed to create snapshot for $vm with quiesce option. Trying without quiesce."
                virsh snapshot-create-as $vm --name "${backup_identifier}" --description "${backup_identifier}.noquiesce" --atomic --disk-only >> "$LOG_FILE" 2>&1
                if [ $? -ne 0 ]; then
                        log "Failed to create snapshot for $vm without quiesce option. Cannot backup that file."
                        echo "$vm.SNAPSHOT_FAILED" >> "$BACKUP_FILE_LIST"
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
        # Optional extract a tenant name from a VM name. example. myvm.tenant.local returns tenant
        local vm="${1}"

        # $(NF-1) means last column -1
        tenant=$(echo "${vm}" |awk -F'.' '{print $(NF-1)}')
        # Special case for me
        if [ "${tenant}" == "npf" ]; then
                tenant="netperfect"
        fi
        # return this
        if [ "${tenant}" != "" ]; then
            echo "${tenant}"
        else
            echo "unknown_tenant"
        fi
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
        sed -i "s%### TENANT ###%${tenant}%g" "${NPBACKUP_CONF_FILE}"
        sed -i "s%### SOURCE ###%${BACKUP_FILE_LIST}%g" "${NPBACKUP_CONF_FILE}"
        sed -i "s%### VM ###%${vm}%g" "${NPBACKUP_CONF_FILE}"

        "$NPBACKUP_EXECUTABLE" --config-file "${NPBACKUP_CONF_FILE}" --backup --force >> "$LOG_FILE" 2>&1
        if [ $? -ne 0 ]; then
                log "Backup failure"
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
                        qemu-img commit -dp "$disk_path" >> "$LOG_FILE" 2>&1
                        log "Note that you will need to modify the XML manually"

                        # TODO: test2
                        virsh dumpxml --inactive --security-info "$vm" > "${ROOT_DIR}/$vm.xml.temp"
                        sed -i "s%${backup_identifier}//g" "${ROOT_DIR}/$vm.xml.temp"
                        virsh define "${ROOT_DIR}/$vm.xml.temp"
                        rm -f "${ROOT_DIR}/$vm.xml.temp"

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
                        log "Cannot delete snapshot metadata for $vm: ${backup_identifier}"
                fi
        else
                log "Will not delete metadata from snapshot ${backup_identifier} for $vm"
        fi
}


function run {
        for vm in ${VMS[@]}; do
                # Empty file
                : > "$BACKUP_FILE_LIST"

                CURRENT_VM_SNAPSHOT=""

                log "Running backup for ${vm}"
                SNAPSHOTS_PATHS=()
                create_snapshot "${vm}" "${BACKUP_IDENTIFIER}"
                tenant=$(get_tenant "${vm}")
                run_backup "${tenant}" "${vm}"
                if [ "${CURRENT_VM_SNAPSHOT}" != "" ]; then
                        remove_snapshot "${CURRENT_VM_SNAPSHOT}" "${BACKUP_IDENTIFIER}"
                fi
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

        log "#### Running backup `date`" >> "$LOG_FILE" 2>&1
        [ ! -d "${ROOT_DIR}" ] && mkdir "${ROOT_DIR}"
        run
}

# SCRIPT ENTRY POINT
main