#!/bin/bash

# RocketLogger installation script for FlockLab 2 observers

HOMEDIR="/home/flocklab"

##########################################################
# helper function, checks last return value and exists if not 0 (requires 2 arguments: error msg and success msg)
check_retval()
{
  if [ $? -ne 0 ]; then
    echo "[ !! ]" $1
    exit 1
  fi
  echo "[ OK ]" $1
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

##########################################################
# install rocketlogger software
cd ${HOMEDIR} rm -rf RocketLogger > /dev/null
git clone --single-branch --branch flocklab --depth 1 https://github.com/ETHZ-TEC/RocketLogger.git > /dev/null
check_retval "Code download"
cd ${HOMEDIR}/RocketLogger/software/rocketlogger
meson builddir > /dev/null && cd builddir && ninja > /dev/null
check_retval "Compile and install"
meson install --no-rebuild
cd ${HOMEDIR} && rm -rf RocketLogger

##########################################################
# restart RocketLogger service
systemctl daemon-reload && systemctl restart rocketlogger && sleep 1 && systemctl status rocketlogger
check_retval "Restart service"
