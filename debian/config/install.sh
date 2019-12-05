#!/bin/bash
# Basic operating system configuration of a new BeagleBone Black/Green/Green Wireless
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


# need to run as root
echo "> Checking root permission"
if [[ $(id -u) -ne 0 ]]; then
  echo "Please run as root. Aborting."
  exit 1
fi

# check network connectivity
echo "> Checking network connectifiy"
ping -q -c 1 -W 2 "8.8.8.8" > /dev/null 2>&1
if [ $? -ne 0 ]; then
  echo "No network connectivity! Aborting."
  exit 2
fi

# create flocklab user
echo "> Create new user 'flocklab'"

# add new flocklab user with home directory and bash shell
useradd --create-home --shell /bin/bash flocklab
# set default password
cat user/password | chpasswd

# add flocklab user to admin and sudo group for super user commands
usermod --append --groups admin flocklab
usermod --append --groups sudo flocklab
usermod --append --groups dialout flocklab
usermod --append --groups i2c flocklab
usermod --append --groups gpio flocklab
usermod --append --groups pwm flocklab
usermod --append --groups remoteproc flocklab
usermod --append --groups spi flocklab
usermod --append --groups adm flocklab

# display updated user configuration
id flocklab

# security
echo "> Updating some security and permission settings"

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

# network configuration
echo "> Updating network configuration"

# copy network interface configuration
cp -f network/interfaces /etc/network/

# create flocklab system config folder
mkdir -p /etc/flocklab

# format the SD card if not mounted
mount | grep mmcblk0p1
if [ $? -ne 0 ]; then
  echo "> Formatting SD card..."
  mkfs.ext4 -q /dev/mmcblk0p1
  # mount the SD card
  echo "> Mounting SD card"
  mkdir /media/card
  mount /dev/mmcblk0p1 /media/card
else
  echo "> SD card already mounted"
fi
# add to fstab
grep /dev/mmcblk0p1 /etc/fstab
if [ $? -ne 0 ]; then
  echo '/dev/mmcblk0p1  /media/card  ext4  noatime  0  2' >> /etc/fstab
  echo "> fstab updated"
fi

# updates and software dependencies
echo "> Deactivating and uninstalling potentially conflicting services"

# stop preinstalled web services
systemctl stop bonescript-autorun.service cloud9.service cloud9.socket nginx.service
systemctl disable bonescript-autorun.service cloud9.service cloud9.socket nginx.service

# uninstall preinstalled web services
apt remove --assume-yes --allow-change-held-packages nginx nodejs? c9-core-installer bonescript?
apt autoremove --assume-yes

# updates and software dependencies
echo "> Updating system and installing software dependencies"

# update packages
apt update --assume-yes
apt upgrade --assume-yes

# install fundamental dependencies
apt install --assume-yes unzip git ntp make device-tree-compiler gcc g++ libncurses5-dev libi2c-dev linux-headers-$(uname -r)

# install am355x PRU support package from git
echo "> Manually download, compile and install am335x-pru-package"
git clone https://github.com/beagleboard/am335x_pru_package.git
(cd am335x_pru_package && make && make install)
ldconfig

# set expiration date in the past to disable logins
echo "> Disable default user 'debian'"
chage -E 1970-01-01 debian

# cleanup
(cd .. && rm -rf config)
echo "> Directory 'config' removed"

# reboot
echo "Platform initialized. System will reboot to apply configuration changes."
reboot && exit 0
