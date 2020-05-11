#!/bin/bash
#
# Copyright (c) 2016-2020, ETH Zurich, Computer Engineering Group
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

ERRORLOG="/tmp/debian_install.log"


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

# check argument (requires hostname)
if [[ $# -lt 1 ]]; then
  echo "[ !! ] No hostname provided."
  exit 1
fi

# need to run as root
if [[ $(id -u) -ne 0 ]]; then
  echo "[ !! ] Please run as root. Aborting."
  exit 1
fi
echo "[ OK ] Checking root permission."

# check network connectivity
ping -q -c 1 -W 2 "8.8.8.8" > /dev/null 2>&1
if [ $? -ne 0 ]; then
  echo "[ !! ] No network connectivity! Aborting."
  exit 2
fi
echo "[ OK ] Checking network connectifiy."

# clear log file
[ -f $ERRORLOG ] && rm $ERRORLOG

# set hostname
echo $1 > /etc/hostname

# create flocklab user

# add new flocklab user with home directory and bash shell
useradd --create-home --shell /bin/bash flocklab > /dev/null 2>> $ERRORLOG
# set default password
cat user/password | chpasswd

# add flocklab user to admin and sudo group for super user commands
usermod --append --groups admin flocklab
usermod --append --groups sudo flocklab
usermod --append --groups dialout flocklab
usermod --append --groups i2c flocklab
usermod --append --groups gpio flocklab
usermod --append --groups pwm flocklab
usermod --append --groups spi flocklab
usermod --append --groups adm flocklab
usermod --append --groups users flocklab
usermod --append --groups disk flocklab

echo "[ OK ] New user 'flocklab' created."  # $(id flocklab)

# security

# copy public keys for log in
mkdir -p /home/flocklab/.ssh/
chmod 700 /home/flocklab/.ssh/
cp -f user/flocklab.default_rsa.pub /home/flocklab/.ssh/
cat /home/flocklab/.ssh/flocklab.default_rsa.pub > /home/flocklab/.ssh/authorized_keys

# copy more secure ssh configuration
cp -f ssh/sshd_config /etc/ssh/

# change ssh welcome message
cp -f system/issue.net /etc/issue.net

# make user owner of its own files
chown flocklab:flocklab -R /home/flocklab/

# create flocklab system config folder
mkdir -p /etc/flocklab

echo "[ OK ] Security and permission settings updated."

# network configuration

# copy network interface configuration
cp -f network/interfaces /etc/network/
check_retval "Failed to update network configuration." "Network configuration updated."

# format the SD card if not mounted
mount | grep mmcblk0p1 > /dev/null 2>&1
if [ $? -ne 0 ]; then
  echo "       Formatting SD card..."
  mkfs.ext4 -q /dev/mmcblk0p1
  check_retval "Failed to format SD card." "SD card formatted."
  # mount the SD card
  mkdir /media/card
  mount /dev/mmcblk0p1 /media/card
  chown flocklab:flocklab /media/card
  chmod 755 /media/card
  check_retval "Failed to mount SD card." "SD card mounted."
else
  echo "[ OK ] SD card already mounted"
fi
# add to fstab
grep /dev/mmcblk0p1 /etc/fstab > /dev/null 2>&1
if [ $? -ne 0 ]; then
  echo "       Updating fstab..."
  echo '/dev/mmcblk0p1  /media/card  ext4  noatime  0  2' >> /etc/fstab
  echo "[ OK ] Entry added to fstab."
fi

# move log directory onto the SD card
mkdir /media/card/log
chmod 777 /media/card/log
ln -sf /media/card/log /var/log

# updates and software dependencies
echo "       Deactivating and uninstalling potentially conflicting services..."

# stop preinstalled web services
systemctl stop bonescript-autorun.service cloud9.service cloud9.socket nginx.service > /dev/null 2>> $ERRORLOG
systemctl disable bonescript-autorun.service cloud9.service cloud9.socket nginx.service > /dev/null 2>> $ERRORLOG
echo "[ OK ] Services stopped."

# uninstall preinstalled web services
echo "       Removing unused packages..."
apt-get --assume-yes remove --allow-change-held-packages nginx nodejs? c9-core-installer bonescript? > /dev/null 2>> $ERRORLOG
apt-get --assume-yes autoremove > /dev/null 2>> $ERRORLOG
check_retval "Failed to remove unused packages." "Unused packages removed."

# updates and software dependencies
echo "       Updating system..."

# update packages
apt-get --assume-yes update > /dev/null 2>> $ERRORLOG
apt-get -qq --assume-yes upgrade    # can't redirect to /dev/null, apt-get may ask questions during the process...
check_retval "Failed to install system updates." "System updates installed."

# install fundamental dependencies
echo "       Installing fundamental dependencies..."
apt-get --assume-yes install unzip minicom git ntp make build-essential python3 python3-dev python3-pip device-tree-compiler gcc g++ libncurses5-dev libi2c-dev linux-headers-$(uname -r) > /dev/null 2>> $ERRORLOG
check_retval "Failed to install packages." "Packages installed."

# install SNMP for monitoring
echo "       Installing snmpd..."
apt-get --assume-yes install snmpd > /dev/null 2>> $ERRORLOG && cp -f snmp/snmpd.conf /etc/snmp/
check_retval "Failed to install snmpd." "snmpd installed."

# install TI code generation tools for PRU
apt-get --assume-yes install ti-pru-cgt-installer
check_retval "Failed to install TI PRU CGT." "TI PRU CGT installed."

# install am355x PRU support package from git
echo "       Compiling and installing am335x-pru-package..."
git clone https://github.com/beagleboard/am335x_pru_package.git > /dev/null 2>> $ERRORLOG
check_retval "Failed to clone repository." "Repository cloned."
(cd am335x_pru_package && make && make install) > /dev/null 2>> $ERRORLOG
check_retval "Failed to install am335x-pru-package." "am335x-pru-package installed."
ldconfig

# add user flocklab to newly created 'remoteproc' group
usermod --append --groups remoteproc flocklab

# set expiration date in the past to disable logins
chage -E 1970-01-01 debian
echo "[ OK ] User 'debian' disabled."

# cleanup
(cd .. && rm -rf config)
echo "[ OK ] Directory 'config' removed."

# reboot
echo "       System will reboot to apply configuration changes..."
reboot && exit 0
