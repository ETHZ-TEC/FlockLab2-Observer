#!/bin/bash
#
# FlockLab2 observer update script.

INSTALL=1       # whether to recompile and install programs on the observer (will ask for sudo PW)
PORT=2322
USER="flocklab"
HOSTPREFIX="fl-"
OBSIDS="02 04 05 06 07 08 09 10 11 12"
RSYNCPARAMS=" -a -z -c --timeout=5 --exclude=.git --no-perms --no-owner --no-group"

# check arguments
if [ $# -gt 0 ]; then
    if [[ ! $OBSIDS = *"$1"* ]] || [ ${#1} -ne 2 ]; then
        echo "Invalid observer $1. Valid options are: ${OBSIDS}."
        exit 1
    fi
    OBSIDS=$1
fi

echo "Going to update files on FlockLab observer(s) $OBSIDS..."
sleep 2   # give the user time to abort, just in case

for OBS in $OBSIDS
do
    # specify custom commands
    UPDATE_MSP430_BSL_TOOLS="cd observer/various/python-msp430-tools && sudo rm -r python-msp430-tools; tar -xzf python-msp430-tools-patched.tar.gz && cd python-msp430-tools && sudo python2.7 setup.py install > /dev/null 2>&1"
    LIST_DIR="ls /usr/local/lib/python2.7/dist-packages"
    REMOVE_FILES="sudo rm -r /usr/local/lib/python2.7/dist-packages/python_msp430_tools-0.6.egg-info"

    # choose the command to execute
    COMMAND=$UPDATE_REPO_FILES
    ssh -q -tt -p ${PORT} ${USER}@${HOSTPREFIX}${OBS} "${COMMAND}"
    # or update repository files:
    #rsync ${RSYNCPARAMS} -q -e "ssh -q -p ${PORT}" . ${USER}@${HOSTPREFIX}${OBS}:observer 2>&1
    if [ $? -eq 0 ]; then
        echo "successfully updated observer ${OBS}"
    else
        echo "FAILED to update observer ${OBS}"
        sleep 1
    fi
done

echo "Done."

