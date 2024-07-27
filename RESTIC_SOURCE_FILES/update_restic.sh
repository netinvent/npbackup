#!/usr/bin/env bash

# Quick script to update restic binaries

export ORG=restic
export REPO=restic
LATEST_VERSION=$(curl -s https://api.github.com/repos/${ORG}/${REPO}/releases/latest | grep "tag_name" | cut -d'"' -f4)
echo Latest restic version ${LATEST_VERSION}

errors=false
for platform in "windows_386" "windows_amd64" "linux_arm" "linux_arm64" "linux_amd64" "darwin_amd64" "freebsd_amd64"; do
    	restic_filename="restic_${LATEST_VERSION//v}_${platform}"
	    if [ ! -f "${restic_filename}" ]; then
        	echo "Moving earlier version to archive"
        	[ -d ARCHIVES ] || mkdir ARCHIVES
        	mv -f restic_*_${platform} ARCHIVES/ > /dev/null 2>&1
			mv -f restic_*_${platform}.exe ARCHIVES/ > /dev/null 2>&1
        	echo "Downloading ${restic_filename}"
		if [ "${platform:0:7}" == "windows" ]; then
			ext=zip
		else
			ext=bz2
		fi
        	curl -OL https://github.com/restic/restic/releases/download/${LATEST_VERSION}/restic_${LATEST_VERSION//v}_{$platform}.${ext}
	        if [ $? -ne 0 ]; then
        	    echo "Failed to download ${restic_filename}"
	            	errors=true
        	else
                	if [ -f "${restic_filename}.bz2" ]; then
            			bzip2 -d "${restic_filename}.bz2" && chmod +x "${restic_filename}"
			elif [ -f "${restic_filename}.zip" ]; then
				unzip "${restic_filename}.zip"
			else
				echo "Archive ${restic_filename} not found"
				errors=true
			fi
            	if [ $? -ne 0 ]; then
                		echo "Failed to decompress ${restic_filename}.bz2"
                		errors=true
        		fi
			[ -f "${restic_filename}.zip" ] && rm -f "${restic_filename}.zip"
    		fi
	fi
done

if [ "${errors}" = true ]; then
	echo "Errors occurred during update"
	exit 1
else
	echo "Finished updating restic binaries"
fi
