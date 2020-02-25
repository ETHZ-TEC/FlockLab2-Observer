#!/bin/bash

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

${BASEDIR}/init_gpio.sh

