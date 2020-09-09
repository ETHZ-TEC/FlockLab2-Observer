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

# FlockLab2 observer: switch from GPS to PTP time synchronization
# execute this script as root user on the observer
#
# notes:
# - the package linuxptp is already installed at this point
# - we do not need phc2sys on the slaves since we use chrony to sync to PTP
# - disable all unnecessary time sync services (ntp, timesyncd)

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

# remove gmtimer
rm /etc/modules-load.d/pps_gmtimer.conf
depmod

# make sure the pin P8.07 is not excluded from the pinmux
sed -i 's/ P8_07_pinmux/ \/\/P8_07_pinmux/' ${HOMEDIR}/observer/device_tree_overlay/BB-FLOCKLAB2.dts
cd ${HOMEDIR}/observer/device_tree_overlay && ./install.sh

# configure LinuxPTP (ptp4l)
PTPCONF="[global]
twoStepFlag         1
slaveOnly           1
priority1           128
priority2           128
clockClass          255
clockAccuracy       0x20
domainNumber        0
logging_level       7
verbose             0
time_stamping       hardware
step_threshold      1.0
summary_interval    0

[eth0]
logAnnounceInterval 1
logSyncInterval     0
delay_mechanism     E2E
network_transport   UDPv4
tsproc_mode         raw
delay_filter        moving_median
delay_filter_length 10"

echo "${PTPCONF}" > /etc/linuxptp/ptp4l.conf
systemctl enable ptp4l
systemctl start ptp4l

# configure Chrony
CHRONYCONF="# take PTP for timesync
refclock PHC /dev/ptp0 refid PTP poll 0
# Uncomment the following line to turn logging on.
#log tracking measurements statistics
# Log files location.
logdir /var/log/chrony
# turn on rtc synchronization
rtcsync
# Step the system clock instead of slewing it if the adjustment is larger than 1sec
makestep 1 -1"

echo "${CHRONYCONF}" > /etc/chrony/chrony.conf
systemctl restart chrony

# disable NTP and timesync daemon
systemctl stop ntp
systemctl disable ntp
systemctl stop systemd-timesyncd
systemctl disable systemd-timesyncd
