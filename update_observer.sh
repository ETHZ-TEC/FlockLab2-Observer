#!/bin/bash
#
# FlockLab2 observer update script.

INSTALL=1       # whether to recompile and install programs on the observer (will ask for sudo PW)
PORT=2322
USER="flocklab"
HOSTPREFIX="fl-"
OBSIDS="02 04 05 06 07 08 09 10 11 12"
SRCDIR="."
DESTDIR="observer"
RSYNCPARAMS=" -a -z -c --timeout=5 --exclude=.git"  # --delete

# check arguments
if [ $# -gt 0 ]; then
    if [[ ! $OBSIDS = *"$1"* ]] || [ ${#1} -ne 2 ]; then
        echo "Invalid observer $1"
        exit 1
    fi
    OBSIDS=$1
fi

echo "Going to update files on FlockLab observer(s) $OBSIDS..."
sleep 2   # give the user time to abort, just in case

for OBS in $OBSIDS
do
    # get a list of modified files (-c option to use checksum to determine changes)
    RES=$(rsync ${RSYNCPARAMS} -i --dry-run --exclude=".git" -e "ssh -q -p ${PORT}" ${SRCDIR} ${USER}@${HOSTPREFIX}${OBS}:${DESTDIR}  2>&1)
    if [ $? -ne 0 ]; then
        if [[ $RES = *timeout* ]] || [[ $RES = *"connection unexpectedly closed"* ]]; then
            echo "FlockLab observer ${HOSTPREFIX}${OBS} not responsive (skipped)."
        else
            echo "An error occurred when trying to access observer ${HOSTPREFIX}${OBS}: $RES"
        fi
        continue
    fi
    if [ -z "$RES" ]; then
        echo "Files on FlockLab observer ${HOSTPREFIX}${OBS} are up to date."
        continue
    fi
    # filter, keep only changed files
    RES=$(echo "${RES}" | grep '^<fc' | cut -d' ' -f2)
    #printf "changed files:\n$RES\n"
    printf "Updating files on FlockLab observer ${HOSTPREFIX}${OBS}... "
    # copy modified files (quiet mode, compress data during file transfer)
    rsync ${RSYNCPARAMS} -q -e "ssh -q -p ${PORT}" ${SRCDIR} ${USER}@${HOSTPREFIX}${OBS}:${DESTDIR}
    if [ $? -ne 0 ]; then
        printf "failed to copy repository files!\n"
        continue
    else
        printf "files updated.\n"
    fi
    # install new code
    if [ $INSTALL -gt 0 ]; then
        if [[ $RES = *fl_logic/* ]]; then
            echo "Installing new fl_logic binary and PRU firmware... "
            ssh -q -tt ${USER}@${HOSTPREFIX}${OBS} 'cd ~/observer/pru/fl_logic && sudo make install'
            if [ $? -ne 0 ]; then
                echo "Failed!"
            fi
        fi
        if [[ $RES = *rocketlogger/* ]]; then
            echo "Compiling and installing new RocketLogger software... "
            ssh -q -tt ${USER}@${HOSTPREFIX}${OBS} 'cd ~/observer/rocketlogger && sudo make install'
            if [ $? -ne 0 ]; then
                echo "Failed!"
            fi
        fi
    fi
done

echo "Done."

