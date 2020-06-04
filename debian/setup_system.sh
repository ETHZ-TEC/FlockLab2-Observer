#!/bin/bash
#
# Copyright (c) 2016-2018, ETH Zurich, Computer Engineering Group
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

#
# Basic operating system configuration of a new BeagleBone Black/Green/Green Wireless
#

REBOOT_TIMEOUT=120
PORT=22
USER="debian"

# check arguments
if [ $# -lt 1 ]; then
  echo "Usage: ./setup_system.sh <beaglebone-host-address> [<hostname>]"
  exit -1
fi
HOST=$1

if [ $# -gt 1 ]; then
  HOSTNAME=$2
else
  HOSTNAME=$HOST
fi

# remove IP address / host name from known_hosts file
ssh-keygen -R $HOST > /dev/null 2>&1

echo "Deploying system configuration on host '${HOST}'..."
sleep 3   # give the user time to abort, just in case

# write the password into a file
echo "Enter new password for user flocklab on host ${HOST}:"
read -s PASSWORD
echo "flocklab:${PASSWORD}" > config/user/password

# either clone the repo on the beaglebone or copy all files
echo "       Copying config files... (enter default password 'temppwd' when asked)"
scp -F /dev/null -P ${PORT} -r config ${USER}@${HOST}: > /dev/null
if [ $? -ne 0 ]; then
  echo "[ !! ] Failed to copy config files!"
  exit 1
else
  echo "[ OK ] Files copied."
fi

# perform system configuration
echo "       Initiating system configuration. You will be asked for the default user password ('temppwd') two times."
ssh -q -F /dev/null -p $PORT -t ${USER}@${HOST} "(cd config && sudo ./install.sh ${HOSTNAME})"
if [ $? -ne 255 ]; then
  echo "[ !! ] System configuration failed (code $CONFIG)."
  exit 1
else
  echo "[ OK ] System configuration was successful."
fi

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

# remove password file
rm config/user/password


