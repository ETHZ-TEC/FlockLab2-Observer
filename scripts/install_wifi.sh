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

# FlockLab2 observer: install wifi drivers and configure the interface

HOMEDIR="/home/flocklab"

# check the arguments
if [ $# -lt 2 ]; then
  echo "Not enough arguments provided. Usage:
  ${0} [wifi SSID] [wifi password]"
  exit 1
fi

WIFISSID=$2
WIFIPW=$3

# check if this is a flocklab observer
hostname | grep "fl-" > /dev/null 2>&1
if [[ $? -ne 0 ]]; then
  echo "Script must run on a FlockLab observer."
  exit 1
fi

# need to run as root
if [[ $(id -u) -ne 0 ]]; then
  echo "Script must run as root."
  exit 1
fi

# convert the wifi password to a wpa hash
WIFIPASSPHRASE=$(wpa_passphrase ${WIFISSID} ${WIFIPW} | sed -n 's/^[^#]*psk=\([0-9a-f]*\)/\1/p')
if [ $? -ne 0 ]; then
  echo "wpa_passphrase failed to execute"
  exit 2
fi

# install driver for wifi dongle
apt-get install firmware-linux-free

# configure connman
WIFICONFIGFILE="/var/lib/connman/wifi.config"
echo "[service_home]
Type = wifi
Name = ${WIFISSID}
Security = wpa2-psk
Passphrase = ${WIFIPASSPHRASE}" > ${WIFICONFIGFILE}

# add cronjob that checks wifi connectivity periodically (workaround for issue with connman)
CRONTAB="/etc/crontab"
grep "wlan0" ${CRONTAB} > /dev/null 2>&1 || echo "*/10 *  * * *   root    /bin/bash /home/flocklab/observer/scripts/ping_watchdog.sh wlan0 2>&1 | /usr/bin/logger -t flocklab" >> ${CRONTAB}

echo "done, rebooting system..."

reboot
