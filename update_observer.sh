#!/bin/bash
#
# FlockLab2 observer update script.

PORT=2322
USER="flocklab"
HOSTPREFIX="fl-"
OBSIDS="02 04 05 06 07 08 09"

# check arguments
if [ $# -gt 0 ]; then
  OBSIDS=$1
fi

echo "Going to update files on FlockLab observer(s) $OBSIDS."
sleep 3   # give the user time to abort, just in case

for OBS in $OBSIDS
do
    echo "Updating files on FlockLab observer ${HOSTPREFIX}${OBS}..."
    rsync -a -q --progress --exclude=".git" -e "ssh -p ${PORT}" ../observer ${USER}@${HOSTPREFIX}${OBS}: > /dev/null 2>&1
    if [ $? -ne 0 ]; then
        echo "Failed to copy repository files!"
        exit 1
    fi
done

echo "Done."

