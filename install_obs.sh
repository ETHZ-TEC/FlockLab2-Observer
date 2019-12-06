#!/bin/bash
# FlockLab2 observer install script (runs on BeagleBone).
#
# Copyright (c) 2016-2019, ETH Zurich, Computer Engineering Group
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


HOMEDIR=/home/flocklab/


# helper function, checks last return value and exists if not 0 (requires 2 arguments: error msg and success msg)
check_retval()
{
  if [ $? -ne 0 ]; then
    echo "[ !! ]" $1
    exit 1
  fi
  echo "[ OK ]" $2
}


# need to run as root
if [[ $(id -u) -ne 0 ]]; then
  echo "Please run as root. Aborting."
  exit 1
fi
echo "[ OK ] Checking for root permission."

# create various directories
[ -d /var/www/rocketlogger ]      || (mkdir /var/www/rocketlogger && chown flocklab:flocklab /var/www/rocketlogger)
[ -d /var/www/rocketlogger/log ]  || mkdir /var/www/rocketlogger/log
[ -d /var/www/rocketlogger/data ] || mkdir /var/www/rocketlogger/data
check_retval "Failed to create directories." "Directories created."

cd ${HOMEDIR}observer/device_tree_overlay && ./install.sh > /dev/null 2>&1
check_retval "Failed to install device tree overlay." "Device tree overlay installed."

# install rocketlogger software
echo "       Compiling RocketLogger code..."
cd ${HOMEDIR}observer/rocketlogger && make install > /dev/null 2>&1
check_retval "Failed to install RocketLogger software." "RocketLogger software installed."

# install binary for GPIO tracing
cd ${HOMEDIR}observer/pru/fl_logic && make install > /dev/null 2>&1
check_retval "Failed to install fl_logic software." "fl_logic software installed."

# extract JLink files
JLINK=$(ls -1 ${HOMEDIR}observer/jlink | grep JLink_Linux | sort | tail -n 1)
JLINKDIR=${JLINK::-4}
tar xzf ${HOMEDIR}observer/jlink/${JLINK} -C /opt && cp -f /opt/${JLINKDIR}/99-jlink.rules /etc/udev/rules.d/ && ln -sf /opt/${JLINKDIR} /opt/jlink && ln -sf /opt/jlink/JRunExe /bin/JRunExe && ln -sf /opt/jlink/JLinkExe /bin/JLinkExe && ln -sf /opt/jlink/JLinkGDBServer /bin/JLinkGDBServer
check_retval "Failed to install JLink." "JLink installed."

# configure time sync
echo "       Installing required packages for time sync..."
apt -y install gpsd gpsd-clients linuxptp chrony pps-tools
check_retval "Failed to install packages." "Packages installed."

# change permission of pps device
chmod 660 /dev/pps0 && chown root:gpio /dev/pps0

# test GNSS receiver availability: gpsmon /dev/ttyO4
# test gpsd: gpsd -D 5 -N -n /dev/ttyO4 /dev/pps0
# in another terminal, check for NTP2: ntpshmmon

# set config for gpsd
echo "DEVICES=/dev/ttyO4
GPSD_OPTIONS='-n /dev/pps0'" > /etc/default/gpsd
check_retval "Failed to configure gpsd." "gpsd configured."

# configure chrony
grep "refclock PPS /dev/pps0" /etc/chrony/chrony.conf || echo "
# GPSD via SHM
refclock PPS /dev/pps0 refid PPS offset 0.5 poll 4 prefer
refclock SHM 0 refid GPS precision 1e-1 poll 4 filter 1000 offset 0.130 noselect
# refclock SOCK /var/run/chrony.ttyUSB0.sock refid GPS noselect

# from chrony.conf manpage
refclock PHC /dev/ptp0 poll 3 dpoll -2 offset 0.0 noselect

server 129.132.177.101 minpoll 4 maxpoll 5
server 129.132.2.21 minpoll 5 maxpoll 6
server 129.132.2.22 minpoll 5 maxpoll 6
server time.ethz.ch minpoll 5 maxpoll 6
server time1.ethz.ch minpoll 5 maxpoll 6
server time2.ethz.ch minpoll 5 maxpoll 6
" >> /etc/chrony/chrony.conf
check_retval "Failed to configure chrony." "Chrony configured."

# restart chrony
systemctl restart gpsd chrony
check_retval "Failed to restart services." "Restart chrony and gpsd service."

# check if chrony is working: chronyc sources -v

reboot
