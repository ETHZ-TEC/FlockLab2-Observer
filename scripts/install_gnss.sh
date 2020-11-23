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

# FlockLab2 observer: switch from PTP to GNSS time synchronization
# execute this script as root user on the observer

HOMEDIR="/home/flocklab"

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

# install gmtimer
cd ${HOMEDIR}/observer/various/pps-gmtimer && make install
echo "pps-gmtimer" > /etc/modules-load.d/pps_gmtimer.conf
depmod

# make sure the pin P8.07 is excluded from the pinmux
sed -i 's/ \/\/P8_07_pinmux/ P8_07_pinmux/' ${HOMEDIR}/observer/device_tree_overlay/BB-FLOCKLAB2.dts
cd ${HOMEDIR}/observer/device_tree_overlay && ./install.sh

# configure LinuxPTP (ptp4l)
systemctl stop ptp4l
systemctl disable ptp4l

# configure Chrony
CHRONYCONF="driftfile /var/lib/chrony/chrony.drift
logdir /var/log/chrony
rtcsync
makestep 1 3
# GPSD via SHM
refclock PPS /dev/pps0 refid PPS precision 1e-7 poll 4 filter 128
#refclock SHM 0 refid PPS2 precision 1e-7 lock GPS
#refclock SHM 1 refid GPS precision 1e-1 offset 0.136 noselect
#refclock PHC /dev/ptp0 poll 3 dpoll -2 offset 0.0 noselect
# NTP servers
server 129.132.2.21 minpoll 5 maxpoll 6
server 129.132.2.22 minpoll 5 maxpoll 6
server time.ethz.ch minpoll 5 maxpoll 6
server time1.ethz.ch minpoll 5 maxpoll 6
server time2.ethz.ch minpoll 5 maxpoll 6"

echo "${CHRONYCONF}" > /etc/chrony/chrony.conf
systemctl restart chrony

echo "done, rebooting system..."

reboot
