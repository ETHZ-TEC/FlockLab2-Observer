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


HOMEDIR="/home/flocklab"
DBDIR="/home/flocklab/db"
LOGDIR="/var/log/flocklab"
CONFIGDIR="/etc/flocklab"
TESTDIR="/home/flocklab/data/curtest";
SDCARDLINK="/home/flocklab/data"

# installation directories
SCRIPTPATH="/home/flocklab/observer/testmanagement"
JLINKPATH="/opt"
BINPATH="/usr/bin"
USERSPACEMODPATH="/usr/bin"
LIBPATH="/usr/lib/flocklab/python"

# error log for this install script
ERRORLOG="/tmp/flocklab_obs_install.log"


# helper function, checks last return value and exists if not 0 (requires 2 arguments: error msg and success msg)
check_retval()
{
  if [ $? -ne 0 ]; then
    echo "[ !! ]" $1
    # display error log:
    echo "       Error log:"
    cat $ERRORLOG
    exit 1
  fi
  echo "[ OK ]" $2
}

##########################################################
# check if this is a flocklab observer
hostname | grep "fl-" > /dev/null 2>&1
if [[ $? -ne 0 ]]; then
  echo "[ !! ] Script must run on a FlockLab observer. Aborting"
  exit 1
fi

# need to run as root
if [[ $(id -u) -ne 0 ]]; then
  echo "[ !! ] Script must run as root. Aborting."
  exit 1
fi
echo "[ OK ] Checking for root permission."

# clear log file
[ -f $ERRORLOG ] && rm $ERRORLOG

##########################################################
# link to SD card and log folder
ln -sf /media/card $SDCARDLINK
ln -sf $LOGDIR $HOMEDIR/log

# create various directories
[ -d $DBDIR ]    || (mkdir -p $DBDIR && chown flocklab:flocklab $DBDIR)
[ -d $TESTDIR ]  || (mkdir -p $TESTDIR && chown flocklab:flocklab $TESTDIR)
[ -d $LOGDIR ]   || (mkdir -p $LOGDIR && chown flocklab:flocklab $LOGDIR)
[ -d $CONFIGDIR ] || (mkdir -p $CONFIGDIR && chown flocklab:flocklab $CONFIGDIR)
check_retval "Failed to create directories." "Directories created."

# add script directory to path
grep ${SCRIPTPATH} ${HOMEDIR}/.profile > /dev/null 2>&1 || echo 'export PATH=$PATH:'${SCRIPTPATH} >> ${HOMEDIR}/.profile
check_retval "Failed to set PATH variable." "PATH variable adjusted."

##########################################################
# install device tree overlay
cd ${HOMEDIR}/observer/device_tree_overlay && ./install.sh > /dev/null 2>> $ERRORLOG
check_retval "Failed to install device tree overlay." "Device tree overlay installed."

##########################################################
# install rocketlogger software
echo "       Compiling RocketLogger code..."
cd ${HOMEDIR}/observer/rocketlogger && make install > /dev/null 2>> $ERRORLOG
check_retval "Failed to install RocketLogger software." "RocketLogger software installed."

##########################################################
# install binary for GPIO tracing
cd ${HOMEDIR}/observer/pru/fl_logic && make install > /dev/null 2>> $ERRORLOG
check_retval "Failed to install fl_logic software." "fl_logic software installed."

##########################################################
# extract JLink files
JLINK=$(ls -1 ${HOMEDIR}/observer/jlink | grep JLink_Linux | sort | tail -n 1)
JLINKDIR=${JLINK::-4}
tar xzf ${HOMEDIR}/observer/jlink/${JLINK} -C ${JLINKPATH} && cp -f ${JLINKPATH}/${JLINKDIR}/99-jlink.rules /etc/udev/rules.d/ && ln -sf ${JLINKPATH}/${JLINKDIR} ${JLINKPATH}/jlink && ln -sf ${JLINKPATH}/jlink/JRunExe ${BINPATH}/JRunExe && ln -sf ${JLINKPATH}/jlink/JLinkExe ${BINPATH}/JLinkExe && ln -sf ${JLINKPATH}/jlink/JLinkGDBServer ${BINPATH}/JLinkGDBServer
check_retval "Failed to install JLink." "JLink installed."

##########################################################
# install required packages for serial logging and GPIO actuation
echo "       Installing required packages for serial logging..."
apt-get --assume-yes install python3-serial minicom > /dev/null 2>> $ERRORLOG && pip3 install smbus intelhex > /dev/null 2>> $ERRORLOG 
# probably not needed: Adafruit_BBIO pyserial
check_retval "Failed to install pyserial." "pyserial installed."
tar xzf ${HOMEDIR}/observer/various/python-msp430-tools/python-msp430-tools-patched.tar.gz -C ${HOMEDIR}/observer/various/python-msp430-tools/ && cd ${HOMEDIR}/observer/various/python-msp430-tools/python-msp430-tools && python2.7 setup.py install > /dev/null 2>> $ERRORLOG
check_retval "Failed to install python-msp430-tools." "python-msp430-tools installed."

##########################################################
# configure time sync
echo "       Installing required packages for time sync..."
apt-get --assume-yes install gpsd gpsd-clients linuxptp chrony pps-tools > /dev/null 2>> $ERRORLOG
check_retval "Failed to install packages." "Packages installed."

# add a udev rules for PPS device to allow access by the user 'flocklab' and 'gpsd'
[ -e /etc/udev/rules.d/99-pps-noroot.rules ] || echo "KERNEL==\"pps0\", OWNER=\"root\", GROUP=\"dialout\", MODE=\"0660\"
KERNEL==\"pps1\", OWNER=\"root\", GROUP=\"dialout\", MODE=\"0660\"
KERNEL==\"pps2\", OWNER=\"root\", GROUP=\"dialout\", MODE=\"0660\"" > /etc/udev/rules.d/99-pps-noroot.rules

# set config for gpsd
echo 'DEVICES="/dev/pps0 /dev/ttyS4"
GPSD_OPTIONS="-n -b"
START_DAEMON="true"
USBAUTO="true"' > /etc/default/gpsd
check_retval "Failed to configure gpsd." "gpsd configured."

# configure chrony
echo "driftfile /var/lib/chrony/chrony.drift
logdir /var/log/chrony
rtcsync
makestep 1 3
# GPSD via SHM
refclock PPS /dev/pps0 refid PPS precision 1e-7 poll 4 filter 128
refclock SHM 0 refid PPS2 precision 1e-7 lock GPS
refclock SHM 1 refid GPS precision 1e-1 offset 0.136 noselect
refclock PHC /dev/ptp0 poll 3 dpoll -2 offset 0.0 noselect
# NTP servers
server 129.132.2.21 minpoll 5 maxpoll 6
server 129.132.2.22 minpoll 5 maxpoll 6
server time.ethz.ch minpoll 5 maxpoll 6
server time1.ethz.ch minpoll 5 maxpoll 6
server time2.ethz.ch minpoll 5 maxpoll 6" > /etc/chrony/chrony.conf
check_retval "Failed to configure chrony." "Chrony configured."

# enable gpsd service and make sure gpsd is started after reboot
ln -sf /lib/systemd/system/gpsd.service /etc/systemd/system/multi-user.target.wants/gpsd.service

# compile and install kernel module for gmtimer pps:
cd ${HOMEDIR}/observer/various/pps-gmtimer && make install > /dev/null 2>> $ERRORLOG
echo "pps-gmtimer" > /etc/modules-load.d/pps_gmtimer.conf
depmod
# after reboot, check if module loaded: lsmod | grep pps-gmtimer
# to test the module: 
#cd /sys/devices/platform/ocp/ocp:pps_gmtimer && ~/observer/various/pps-gmtimer/watch-pps


##########################################################
# add startup script
[ -f /etc/systemd/system/flocklab.service ] || echo "[Unit]
Description=FlockLab Service
[Service]
Type=idle
ExecStart=/home/flocklab/observer/scripts/flocklab_init.sh
[Install]
WantedBy=default.target" > /etc/systemd/system/flocklab.service
chmod +x /home/flocklab/observer/scripts/flocklab_init.sh
chmod 664 /etc/systemd/system/flocklab.service
systemctl daemon-reload && systemctl enable flocklab.service
check_retval "Failed to enable FlockLab service." "FlockLab service enabled."

# cleanup
apt-get --assume-yes autoremove > /dev/null 2>> $ERRORLOG

reboot && exit 0
