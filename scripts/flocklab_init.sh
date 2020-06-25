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

BASEDIR=$(dirname "$0")

# check whether Ethernet is up and running
STATE=$(ethtool eth0 | grep PHYAD | awk '{print $2}')
if [ $STATE -ne 0 ]; then
    sleep 30
    echo "Ethernet interface is stuck, rebooting..." >> /var/log/syslog
    sync
    /usr/sbin/bbb-long-reset
    exit 1
else
    echo "Ethernet interface is up and running." >> /var/log/syslog
fi


# --- GPIO INIT ---

# set direction to output
echo out > /sys/class/gpio/gpio47/direction # select0
echo out > /sys/class/gpio/gpio27/direction # select1
echo out > /sys/class/gpio/gpio26/direction # power_EN
echo out > /sys/class/gpio/gpio46/direction # Target_nEN
echo out > /sys/class/gpio/gpio65/direction # act_nEN
echo out > /sys/class/gpio/gpio44/direction # JLink_nRST
echo out > /sys/class/gpio/gpio68/direction # USB_nRST
echo out > /sys/class/gpio/gpio67/direction # GNSS_nRST
echo out > /sys/class/gpio/gpio77/direction # Target_nRST
echo out > /sys/class/gpio/gpio22/direction # MUX_nEN
echo out > /sys/class/gpio/gpio89/direction # Target_SIG1
echo out > /sys/class/gpio/gpio88/direction # Target_SIG2
echo out > /sys/class/gpio/gpio81/direction # Target_PROG

# set pin state
echo 1 > /sys/class/gpio/gpio47/value # select0
echo 1 > /sys/class/gpio/gpio27/value # select1
echo 0 > /sys/class/gpio/gpio26/value # power_EN
echo 1 > /sys/class/gpio/gpio46/value # Target_nEN
echo 1 > /sys/class/gpio/gpio65/value # act_nEN
echo 1 > /sys/class/gpio/gpio44/value # JLink_nRST
echo 1 > /sys/class/gpio/gpio68/value # USB_nRST
echo 1 > /sys/class/gpio/gpio67/value # GNSS_nRST
echo 1 > /sys/class/gpio/gpio77/value # Target_nRST
echo 0 > /sys/class/gpio/gpio22/value # MUX_nEN
echo 0 > /sys/class/gpio/gpio89/value # Target_SIG1
echo 0 > /sys/class/gpio/gpio88/value # Target_SIG2
echo 0 > /sys/class/gpio/gpio81/value # Target_PROG


