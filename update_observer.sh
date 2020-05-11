#!/bin/bash
#
# Copyright (c) 2019, ETH Zurich, Computer Engineering Group
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
OBSIDS="02 04 05 06 07 08 09 10 11 12"
SRCDIR="."
DESTDIR="observer"
RSYNCPARAMS=" -a -z -c --timeout=5 --exclude=.git --no-perms --no-owner --no-group"  # --delete
JLINKPATH="/opt"

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
            echo "Installing new fl_logic binary and PRU firmware... "
            ssh -q -tt ${USER}@${HOSTPREFIX}${OBS} 'cd ~/observer/pru/fl_logic && sudo make install'
            if [ $? -ne 0 ]; then
                echo "Failed!"
            fi
        fi
        if [[ $CHANGEDFILES = *serialreader/* ]]; then
            echo "Installing new serial reader binary... "
            ssh -q -tt ${USER}@${HOSTPREFIX}${OBS} 'cd ~/observer/various/serialreader && sudo make install'
            if [ $? -ne 0 ]; then
                echo "Failed!"
            fi
        fi
        if [[ $CHANGEDFILES = *actuation* ]]; then
            echo "Installing new actuation service module... "
            ssh -q -tt ${USER}@${HOSTPREFIX}${OBS} 'cd ~/observer/various/actuation && sudo make install'
            if [ $? -ne 0 ]; then
                echo "Failed!"
            fi
        fi
        if [[ $CHANGEDFILES = *device_tree_overlay* ]]; then
            echo "Installing new device tree overlay... "
            ssh -q -tt ${USER}@${HOSTPREFIX}${OBS} 'cd ~/observer/device_tree_overlay && sudo ./install'
            if [ $? -ne 0 ]; then
                echo "Failed!"
            fi
        fi
        if [[ $CHANGEDFILES = *rocketlogger/* ]]; then
            echo "Compiling and installing new RocketLogger software... "
            ssh -q -tt ${USER}@${HOSTPREFIX}${OBS} 'cd ~/observer/rocketlogger && sudo make install'
            if [ $? -ne 0 ]; then
                echo "Failed!"
            fi
        fi
        if [[ $NEWFILES = *jlink/* ]]; then
            echo "Installing new JLink software..."
            JLINK=$(ls -1 jlink | grep JLink_Linux | sort | tail -n 1)
            JLINKDIR=${JLINK::-4}
            ssh -q -tt ${USER}@${HOSTPREFIX}${OBS} "sudo tar xzf ~/observer/jlink/${JLINK} -C ${JLINKPATH} && sudo rm ${JLINKPATH}/jlink && sudo ln -sf ${JLINKPATH}/${JLINKDIR} ${JLINKPATH}/jlink"
            if [ $? -ne 0 ]; then
                echo "Failed!"
            fi
        fi
    fi
done

echo "Done."

