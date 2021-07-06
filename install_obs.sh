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

##########################################################
#
# FlockLab2 observer install script (runs on BeagleBone).
# Do not call this script directly, use ./setup_observer.sh instead.
#
##########################################################

HOMEDIR="/home/flocklab"
RESULTSDIR="/home/flocklab/data/results"
LOGDIR="/var/log/flocklab"
CONFIGDIR="/etc/flocklab"
TESTDIR="/home/flocklab/data/curtest";
SDCARDLINK="/home/flocklab/data"                      # path to the SD card
SDCARD="/media/sdcard"

# installation directories
SCRIPTPATH="/home/flocklab/observer/testmanagement"   # will be appended to PATH
INSTALLPATH="/opt"                                    # additional SW such as JLink will be installed here
BINPATH="/usr/bin"                                    # executables will be copied into this directory
LIBPATH="/opt/jlink"                                  # will be appended to LD_LIBRARY_PATH

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
echo "" > $ERRORLOG

##########################################################
# make sure an SD card is mounted
mount | grep "$SDCARD" > /dev/null
check_retval "No SD card mounted!" "SD card is mounted."

# link to SD card and log folder
#ln -sf $SDCARD $SDCARDLINK  -> done via fstab
ln -sf $LOGDIR $HOMEDIR/log

# create various directories
[ -d $RESULTSDIR ] || (mkdir -p $RESULTSDIR && chown flocklab:flocklab $RESULTSDIR)
[ -d $TESTDIR ]    || (mkdir -p $TESTDIR && chown flocklab:flocklab $TESTDIR)
[ -d $LOGDIR ]     || (mkdir -p $LOGDIR && chown flocklab:flocklab $LOGDIR)
[ -d $CONFIGDIR ]  || (mkdir -p $CONFIGDIR && chown flocklab:flocklab $CONFIGDIR)
check_retval "Failed to create directories." "Directories created."

# add script directories to path
grep ${SCRIPTPATH} ${HOMEDIR}/.profile > /dev/null 2>&1 || echo 'export PATH=$PATH:'${SCRIPTPATH} >> ${HOMEDIR}/.profile
check_retval "Failed to set PATH variable." "PATH variable adjusted."

# add library directories to path (not required)
#grep ${LIBPATH} ${HOMEDIR}/.profile > /dev/null 2>&1 || echo 'export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:'${LIBPATH} >> ${HOMEDIR}/.profile

##########################################################
# install device tree overlay -> already done in RocketLogger system installation
#cd ${HOMEDIR}/observer/device_tree_overlay && ./install.sh > /dev/null 2>> $ERRORLOG
#check_retval "Failed to install device tree overlay." "Device tree overlay installed."
echo "[ -- ] Device tree overlay installation skipped."

##########################################################
# install am355x PRU support package from git
cd ${HOMEDIR} && rm -rf am335x_pru_package  > /dev/null 2>&1
git clone https://github.com/beagleboard/am335x_pru_package.git > /dev/null 2>> $ERRORLOG
check_retval "Failed to download am335x_pru_package code." "am335x_pru_package code downloaded."
echo "       Compiling and installing am335x-pru-package..."
(cd am335x_pru_package && make && make install) > /dev/null 2>> $ERRORLOG
check_retval "Failed to install am335x-pru-package." "am335x-pru-package installed."
cd ${HOMEDIR} && rm -rf am335x_pru_package
ldconfig
usermod --append --groups remoteproc flocklab
[ -e /etc/udev/rules.d/uio.rules ] || echo 'SUBSYSTEM=="uio", GROUP="users", MODE="0660"' > /etc/udev/rules.d/uio.rules

##########################################################
# install rocketlogger software
cd ${HOMEDIR} rm -rf RocketLogger > /dev/null 2>&1
git clone --single-branch --branch flocklab --depth 1 https://github.com/ETHZ-TEC/RocketLogger.git > /dev/null 2>> $ERRORLOG
check_retval "Failed to get RocketLogger code." "RocketLogger code downloaded."
echo "       Compiling RocketLogger code..."
cd ${HOMEDIR}/RocketLogger/software/rocketlogger  # && make install > /dev/null 2>> $ERRORLOG
meson builddir > /dev/null 2>> $ERRORLOG && cd builddir && ninja > /dev/null 2>> $ERRORLOG
check_retval "Failed to install RocketLogger software." "RocketLogger software installed."
meson install --no-rebuild > /dev/null 2>> $ERRORLOG    # don't check retval, may be 1 if executed the 2nd time
cd ${HOMEDIR} && rm -rf RocketLogger

##########################################################
# install binary for GPIO tracing
cd ${HOMEDIR}/observer/pru/fl_logic && make install > /dev/null 2>> $ERRORLOG
check_retval "Failed to install GPIO tracing software." "GPIO tracing software installed."

##########################################################
# install binary for serial logging
cd ${HOMEDIR}/observer/various/serialreader && make install > /dev/null 2>> $ERRORLOG
check_retval "Failed to install serial logging software." "Serial logging software installed."

##########################################################
# install kernel module for GPIO actuation
cd ${HOMEDIR}/observer/various/actuation && make install > /dev/null 2>> $ERRORLOG
check_retval "Failed to install GPIO actuation kernel module" "GPIO actuation kernel module installed."
echo "fl_actuation" > /etc/modules-load.d/fl_actuation.conf
depmod
# add udev rule
[ -e /etc/udev/rules.d/99-flocklab-act.rules ] || echo "KERNEL==\"flocklab_act\", OWNER=\"root\", GROUP=\"dialout\", MODE=\"0660\"" > /etc/udev/rules.d/99-flocklab-act.rules

##########################################################
# extract JLink files
JLINK=$(ls -1 ${HOMEDIR}/observer/jlink | grep JLink_Linux | sort | tail -n 1)
JLINKDIR=${JLINK::-4}
tar xzf ${HOMEDIR}/observer/jlink/${JLINK} -C ${INSTALLPATH} && cp -f ${INSTALLPATH}/${JLINKDIR}/99-jlink.rules /etc/udev/rules.d/ && ln -sf ${INSTALLPATH}/${JLINKDIR} ${INSTALLPATH}/jlink && ln -sf ${INSTALLPATH}/jlink/JRunExe ${BINPATH}/JRunExe && ln -sf ${INSTALLPATH}/jlink/JLinkExe ${BINPATH}/JLinkExe && ln -sf ${INSTALLPATH}/jlink/JLinkGDBServer ${BINPATH}/JLinkGDBServer
check_retval "Failed to install JLink." "JLink installed."

##########################################################
# install required packages for rocketlogger calibration
echo "       Installing required packages for Rocketlogger calibration..."
apt-get --assume-yes install libfreetype6 libatlas3-base > /dev/null 2>> $ERRORLOG && pip3 install pyvisa pyvisa-py rocketlogger==1.99a6 >> /dev/null 2>> $ERRORLOG
check_retval "Failed to install packages." "Packages installed."

##########################################################
# install required packages for serial logging and BSL programming
echo "       Installing required packages for serial logging..."
apt-get --assume-yes install python3-serial python2.7 python-serial python-setuptools > /dev/null 2>> $ERRORLOG
check_retval "Failed to install pyserial." "pyserial installed."
tar xzf ${HOMEDIR}/observer/various/python-msp430-tools/python-msp430-tools-patched.tar.gz -C /tmp && cd /tmp/python-msp430-tools && python2.7 setup.py install > /dev/null 2>> $ERRORLOG
check_retval "Failed to install python-msp430-tools." "python-msp430-tools installed."

##########################################################
# misc python modules
pip3 install smbus intelhex stm32loader pylink-square > /dev/null 2>> $ERRORLOG
check_retval "Failed to install additional python modules." "Additional python modules installed."

##########################################################
# configure time sync
echo "       Installing required packages for time sync..."
apt-get --assume-yes install linuxptp chrony pps-tools > /dev/null 2>> $ERRORLOG    # gpsd gpsd-clients (GPSD doesn't seem to be required)
check_retval "Failed to install packages." "Packages installed."

# add a udev rules for PPS device to allow access by the user 'flocklab' and 'gpsd'
[ -e /etc/udev/rules.d/99-pps-noroot.rules ] || echo "KERNEL==\"pps0\", OWNER=\"root\", GROUP=\"dialout\", MODE=\"0660\"" > /etc/udev/rules.d/99-pps-noroot.rules

# set config for gpsd -> GPSD doesn't seem to be required!
#echo 'DEVICES="/dev/pps0 /dev/ttyS4"
#GPSD_OPTIONS="-n -b"
#START_DAEMON="true"
#USBAUTO="true"' > /etc/default/gpsd
#check_retval "Failed to configure gpsd." "gpsd configured."

# enable gpsd service and make sure gpsd is started after reboot
#ln -sf /lib/systemd/system/gpsd.service /etc/systemd/system/multi-user.target.wants/gpsd.service

# configure chrony
echo "driftfile /var/lib/chrony/chrony.drift
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
server time2.ethz.ch minpoll 5 maxpoll 6" > /etc/chrony/chrony.conf
check_retval "Failed to configure chrony." "Chrony configured."

# compile and install kernel module for gmtimer pps:
cd ${HOMEDIR}/observer/various/pps-gmtimer && make install > /dev/null 2>> $ERRORLOG
check_retval "Failed to install PPS gmtimer kernel module." "PPS gmtimer kernel module installed."
echo "pps-gmtimer" > /etc/modules-load.d/pps_gmtimer.conf
depmod
# after reboot, check if module loaded: lsmod | grep pps-gmtimer
# to test the module:
#cd /sys/devices/platform/ocp/ocp:pps_gmtimer && ~/observer/various/pps-gmtimer/watch-pps

##########################################################
# install Ethernet PHY / SYS_RESETn fix for BeagleBone
apt-get --assume-yes install ethtool > /dev/null 2>> $ERRORLOG && cd ${HOMEDIR}/observer/various/bbbrtc && make > /dev/null 2>> $ERRORLOG
check_retval "Failed to install bbbrtc." "bbbrtc installed."

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
systemctl daemon-reload && systemctl enable flocklab.service > /dev/null 2>> $ERRORLOG
check_retval "Failed to enable FlockLab service." "FlockLab service enabled."

##########################################################
# install cronjobs
CRONTAB="/etc/crontab"
# run ping watchdog every hour
grep "ping_watchdog" ${CRONTAB} > /dev/null 2>&1 || echo "0  *    * * *   root    /bin/bash /home/flocklab/observer/scripts/ping_watchdog.sh 2>&1 | /usr/bin/logger -t flocklab" >> ${CRONTAB}

##########################################################

# make sure user flocklab owns all files within the home and log directory
chown --recursive flocklab:flocklab /home/flocklab/
chown --recursive flocklab:flocklab /var/log/flocklab

# cleanup
apt-get --assume-yes autoremove > /dev/null 2>> $ERRORLOG

reboot && exit 0
