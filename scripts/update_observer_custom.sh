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

# FlockLab2 simple observer update script.

INSTALL=1       # whether to recompile and install programs on the observer (will ask for sudo PW)
PORT=2322
USER="flocklab"
HOSTPREFIX="fl-"
OBSIDS="01 02 03 04 05 06 07 08 09 10 11 12 17 25"
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
    REMOVE_JLINKFILES="rm -r observer/jlink/JLink*"
    MOVE_LOGS_TO_SDCARD="sudo rm -rf /var/log; sudo mkdir /media/card/log; sudo chmod 777 /media/card/log; mkdir /media/card/log/flocklab; sudo ln -sf /media/card/log /var/log; sudo reboot"

    # choose the command to execute
    #COMMAND=$LIST_DIR
    #ssh -q -tt -p ${PORT} ${USER}@${HOSTPREFIX}${OBS} "${COMMAND}"
    # or update repository files:
    rsync ${RSYNCPARAMS} -q -e "ssh -q -p ${PORT}" . ${USER}@${HOSTPREFIX}${OBS}:observer 2>&1
    if [ $? -eq 0 ]; then
        echo "successfully updated observer ${OBS}"
    else
        echo "FAILED to update observer ${OBS}"
        sleep 1
    fi
done

echo "Done."

