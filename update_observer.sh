#!/bin/bash
#
# Copyright (c) 2020, ETH Zurich, Computer Engineering Group
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# * Redistributions of source code must retain the above copyright notice, this
#   list of conditions and the following disclaimer.
#
# * Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and/or other materials provided with the distribution.
#
# * Neither the name of the copyright holder nor the names of its
#   contributors may be used to endorse or promote products derived from
#   this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
# Author: Reto Da Forno
#

#
# FlockLab2 observer update script.
#
# Copies new files and installs new binaries on the BeagleBone.
#

INSTALL=1       # whether to recompile and install programs on the observer (will ask for sudo PW)
PORT=2322
USER="flocklab"
HOSTPREFIX="fl-"
OBSIDS="01 02 03 04 05 06 07 08 09 10 11 12 15 17 25 20"
SRCDIR="."
DESTDIR="observer"
RSYNCPARAMS=" -a -z -c --timeout=5 --exclude=.git --no-perms --no-owner --no-group"  # --delete
JLINKPATH="/opt"
PASSWORD=""     # script will query password if left blank

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


function getpw {
    if [ -z "$PASSWORD" ]; then
        echo "Enter the sudo password for user $USER:"
        read -s PASSWORD
    fi
}


for OBS in $OBSIDS
do
    # get a list of modified files (-c option to use checksum to determine changes)
    RES=$(rsync ${RSYNCPARAMS} -i --dry-run -e "ssh -q -p ${PORT}" ${SRCDIR} ${USER}@${HOSTPREFIX}${OBS}:${DESTDIR}  2>&1)
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
    #echo "${RES}"
    CHANGEDFILES=$(echo "${RES}" | grep '^<fc' | cut -d' ' -f2)
    NEWFILES=$(echo "${RES}" | grep '^<f++' | cut -d' ' -f2)
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
        if [[ $CHANGEDFILES = *fl_logic/* ]]; then
            getpw
            echo "Installing new fl_logic binary and PRU firmware... "
            echo $PASSWORD | ssh -q -tt ${USER}@${HOSTPREFIX}${OBS} 'cd ~/observer/pru/fl_logic && sudo make install'
            if [ $? -ne 0 ]; then
                echo "Failed!"
            fi
        fi
        if [[ $CHANGEDFILES = *serialreader/* ]]; then
            getpw
            echo "Installing new serial reader binary... "
            echo $PASSWORD | ssh -q -tt ${USER}@${HOSTPREFIX}${OBS} 'cd ~/observer/various/serialreader && sudo make install'
            if [ $? -ne 0 ]; then
                echo "Failed!"
            fi
        fi
        if [[ $CHANGEDFILES = *actuation* ]]; then
            getpw
            echo "Installing new actuation service module... "
            echo $PASSWORD | ssh -q -tt ${USER}@${HOSTPREFIX}${OBS} 'cd ~/observer/various/actuation && sudo make install'
            if [ $? -ne 0 ]; then
                echo "Failed!"
            fi
        fi
        # do not update device tree overlay since we have different versions for different observers
        #if [[ $CHANGEDFILES = *device_tree_overlay/* ]]; then
        #    getpw
        #    echo "Installing new device tree overlay... "
        #    echo $PASSWORD | ssh -q -tt ${USER}@${HOSTPREFIX}${OBS} 'cd ~/observer/device_tree_overlay && sudo ./install.sh'
        #    if [ $? -ne 0 ]; then
        #        echo "Failed!"
        #    fi
        #fi
        if [[ $CHANGEDFILES = *rocketlogger/* ]]; then
            getpw
            echo "Compiling and installing new RocketLogger software... "
            echo $PASSWORD | ssh -q -tt ${USER}@${HOSTPREFIX}${OBS} 'cd ~/observer/rocketlogger && sudo make install'
            if [ $? -ne 0 ]; then
                echo "Failed!"
            fi
        fi
        if [[ $NEWFILES = *jlink/* ]]; then
            getpw
            echo "Installing new JLink software..."
            JLINK=$(ls -1 jlink | grep JLink_Linux | sort | tail -n 1)
            JLINKDIR=${JLINK::-4}
            printf "$PASSWORD\n$PASSWORD\n$PASSWORD\n" | ssh -q -tt ${USER}@${HOSTPREFIX}${OBS} "sudo tar xzf ~/observer/jlink/${JLINK} -C ${JLINKPATH} && sudo rm ${JLINKPATH}/jlink && sudo ln -sf ${JLINKPATH}/${JLINKDIR} ${JLINKPATH}/jlink"
            if [ $? -ne 0 ]; then
                echo "Failed!"
            fi
        fi
    fi
done

echo "Done."

