#!/bin/bash

set -e

GO_VERSION=1.25.6
RESTIC_VERSION=0.18.1

LOG_FILE=${0%.sh}.log

log() {
    __log_line="${1}"
    __log_level="${2:-INFO}"

    __log_line="${__log_level}: ${__log_line}"
    echo "${__log_line}" >> "${LOG_FILE}"
    echo "${__log_line}"

    if [ "${__log_level}" = "ERROR" ]; then
        POST_INSTALL_SCRIPT_GOOD=false
    fi
}

log_quit() {
    log "${1}" "${2}"
    log "Exiting script"
    exit 1
}

log "Starting build of restic ${RESTIC_VERSION} with Go ${GO_VERSION} for Windows 7"

[ ! -d BUILD ] && mkdir BUILD
pushd BUILD

if type curl > /dev/null 2>&1; then
	DL_PROGRAM="curl -OL"
elif type wget > /dev/null 2>&1; then
	DL_PROGRAM="wget"
else
	log_quit "Neither curl nor wget is installed. Please install at least one"
fi

if [ ! -f go${GO_VERSION}.linux-amd64.tar.gz ]; then
    ${DL_PROGRAM} https://dl.google.com/go/go${GO_VERSION}.linux-amd64.tar.gz || log_quit "Go ${GO_VERSION} archive not downloaded" "ERROR"
fi
if [ ! -f win7sup25.diff ]; then
   ${DL_PROGRAM} https://gist.github.com/DRON-666/6e29eb6a8635fae9ab822782f34d8fd6/raw/win7sup25.diff || log_quit "Windows 7 support patch not downloaded" "ERROR"
fi

if [ -d go ]; then
    log "Removing existing Go directory"
    rm -rf go || log_quit "Failed to remove existing Go directory" "ERROR"
fi

tar xvf go${GO_VERSION}.linux-amd64.tar.gz || log_quit "Failed to extract Go ${GO_VERSION} archive" "ERROR"

git apply --directory=go/src --check win7sup25.diff || log_quit "Windows 7 support patch cannot be applied cleanly" "ERROR"
git apply --directory=go/src win7sup25.diff || log_quit "Failed to apply Windows 7 support patch" "ERROR"

if [ ! -f restic-${RESTIC_VERSION}.tar.gz ]; then
    ${DL_PROGRAM} https://github.com/restic/restic/releases/download/v${RESTIC_VERSION}/restic-${RESTIC_VERSION}.tar.gz || log_quit "Restic ${RESTIC_VERSION} archive not downloaded" "ERROR"
fi

if [ -d restic-${RESTIC_VERSION} ]; then
    log "Removing existing restic source directory"
    rm -rf restic-${RESTIC_VERSION} || log_quit "Failed to remove existing restic source directory" "ERROR"
fi
tar xvf restic-${RESTIC_VERSION}.tar.gz || log_quit "Failed to extract restic ${RESTIC_VERSION} archive" "ERROR"

for goos in windows; do
    for goarch in 386 amd64; do
        pushd restic-${RESTIC_VERSION}
        log "Building Go ${GO_VERSION} for ${arch} with Windows 7 support"
        ../go/bin/go run build.go --goos ${goos} --goarch ${goarch} -o ../../restic_${RESTIC_VERSION}_${goos}_legacy_${goarch}.exe || log_quit "Failed to build Go ${GO_VERSION} for ${arch}" "ERROR"
        popd
    done
done


log "BUILD with great success!"
popd
