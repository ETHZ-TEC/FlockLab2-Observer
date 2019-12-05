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
if [ $? -ne 0 ]; then
  echo "[ !! ] Failed to create directories."
  exit 1
fi
echo "[ OK ] Directories created."

cd ${HOMEDIR}observer/device_tree_overlay && ./install.sh > /dev/null 2>&1
if [ $? -ne 0 ]; then
  echo "[ !! ] Failed to install device tree overlay."
  exit 1
fi
echo "[ OK ] Device tree overlay installed."

# install rocketlogger software
echo "       Compiling RocketLogger code..."
cd ${HOMEDIR}observer/rocketlogger && make install > /dev/null 2>&1
if [ $? -ne 0 ]; then
  echo "[ !! ] Failed to install RocketLogger software."
  exit 1
fi
echo "[ OK ] RocketLogger software installed."

# install binary for GPIO tracing
cd ${HOMEDIR}observer/pru/fl_logic && make install > /dev/null 2>&1
if [ $? -ne 0 ]; then
  echo "[ !! ] Failed to install fl_logic software."
  exit 1
fi
echo "[ OK ] fl_logic software installed."

# extract JLink files
JLINK=$(ls -1 ${HOMEDIR}observer/jlink | grep JLink_Linux | sort | tail -n 1)
JLINKDIR=${JLINK::-4}
tar xzf ${HOMEDIR}observer/jlink/${JLINK} -C /opt && cp -f /opt/${JLINKDIR}/99-jlink.rules /etc/udev/rules.d/ && ln -sf /opt/${JLINKDIR} /opt/jlink && ln -sf /opt/jlink/JRunExe /bin/JRunExe && ln -sf /opt/jlink/JLinkExe /bin/JLinkExe && ln -sf /opt/jlink/JLinkGDBServer /bin/JLinkGDBServer
if [ $? -ne 0 ]; then
  echo "[ !! ] Failed to install JLink."
  exit 1
fi
echo "[ OK ] JLink installed."

reboot
