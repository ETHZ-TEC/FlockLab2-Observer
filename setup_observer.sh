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
# FlockLab2 observer setup script
#
# Make sure to first execute ./debian/setup_system.sh before running this script.
#

REBOOT_TIMEOUT=120
PORT=2322
USER="flocklab"

# check arguments
if [ $# -lt 1 ]; then
  echo "Usage: ./setup_observer.sh <beaglebone-host-address>"
  exit -1
fi

HOST=$1
echo "Setting up FlockLab observer '${HOST}'..."
sleep 3   # give the user time to abort, just in case

# remove IP address / host name from known_hosts file
IPADDR=$(host $HOST | awk '{print $NF}')
HOSTNAME=$(host $HOST | awk '{print $1}')
ssh-keygen -R "[${HOSTNAME}]:${PORT}" > /dev/null 2>&1
ssh-keygen -R "[${IPADDR}]:${PORT}" > /dev/null 2>&1

# verify that SSH login works
ssh -q -p ${PORT} ${USER}@${HOST} "exit" > /dev/null 2>&1
if [ $? -ne 0 ]; then
  echo "[ !! ] SSH login failed."
  exit 1
fi
echo "[ OK ] SSH login successful."

# either clone the repo on the beaglebone or copy all files
#ssh -p $PORT ${HOST} "git clone git@gitlab.ethz.ch:tec/research/flocklab/observer.git observer"
echo "       Copying repository files..."
rsync -a -q --progress --exclude=".git" -e "ssh -p ${PORT}" ../observer ${USER}@${HOST}: > /dev/null 2>&1
if [ $? -ne 0 ]; then
  echo "[ !! ] Failed to copy repository files!"
  exit 1
fi
echo "[ OK ] Files copied."


# run install script
ssh -q -p ${PORT} -t ${USER}@${HOST} "sudo ~/observer/install_obs.sh"
if [ $? -ne 255 ]; then
  echo "[ !! ] Failed to execute install script."
  exit 1
fi
echo "[ OK ] Install script terminated."

# wait for system to reboot
echo -n "       Waiting for the system to reboot..."
sleep 5
while [[ $REBOOT_TIMEOUT -gt 0 ]]; do
  REBOOT_TIMEOUT=`expr $REBOOT_TIMEOUT - 1`
  echo -n "."
  ping -c1 -W2 ${HOST} > /dev/null
  # break timeout loop on success
  if [ $? -eq 0 ]; then
    sleep 2
    echo ""
    echo "[ OK ] Done."
    break
  fi
done
# check for connectivity loss
if [ $REBOOT_TIMEOUT -eq 0 ]; then
  echo ""
  echo "[ !! ] System reboot timed out."
  exit 1
fi


