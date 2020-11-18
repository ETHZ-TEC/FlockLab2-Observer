#!/bin/bash

# a simple ping watchdog, reboots the host system if the target host is inaccessible

HOSTNAME=whymper.ee.ethz.ch   # target host to ping
TIMEOUT=60                    # timeout in seconds
INTERFACE=""

if [ $# -gt 0 ]; then
  INTERFACE="-I $1"
fi

#echo "[ping watchdog] trying to reach $HOSTNAME..."
while [[ $TIMEOUT -gt 0 ]]; do
  TIMEOUT=`expr $TIMEOUT - 1`
  ping -c1 -W1 ${INTERFACE} ${HOSTNAME} > /dev/null 2>&1
  RET=$?
  # break timeout loop on success
  if [ $RET -eq 0 ]; then
    #echo "[ping watchdog] $HOSTNAME is reachable"
    break
  elif [ $RET -gt 1 ]; then
    sleep 1   # this error happens e.g. when hostname is unknown -> make sure to wait 1 second
  fi
done
if [ $TIMEOUT -eq 0 ]; then
  if [ -z "$INTERFACE" ]; then
    echo "[ping watchdog] cannot reach $HOSTNAME, rebooting system..."
    reboot
  else
    # if an interface was provided: restart the connman service instead of rebooting the system
    echo "[ping watchdog] restarting connman"
    systemctl restart connman
  fi
fi
