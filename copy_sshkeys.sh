#!/bin/bash

# replaces the default rocketlogger ssh key with custom flocklab keys
# the keyfile required to deploy these new public keys is available in the RocketLogger wiki:
#   https://github.com/ETHZ-TEC/RocketLogger/wiki/software

PORT=2322
USER=flocklab

# check argument
if [ $# -lt 3 ]; then
  echo "Usage: ./setup_observer.sh <beaglebone-host-address> <path_to_rocketlogger.default_rsa> <your_public_key>"
  exit 1
fi
if [ ! -e $2 ]; then
  echo "File '$2' does either not exist or cannot be accessed"
  exit 1
fi
if [ ! -e $3 ]; then
  echo "File '$3' does either not exist or cannot be accessed"
  exit 1
fi

HOST=$1
KEYFILE=$2
PUBLICKEY=$(cat $3)

# remove IP address / host name from known_hosts file
IPADDR=$(host $HOST | awk '{print $NF}')
HOSTNAME=$(host $HOST | awk '{print $1}')
ssh-keygen -R "[${HOSTNAME}]:${PORT}" > /dev/null 2>&1
ssh-keygen -R "[${IPADDR}]:${PORT}" > /dev/null 2>&1

ssh -p $PORT -i $KEYFILE -t ${USER}@$HOST "echo '${PUBLICKEY}' > pubkey.pub && sudo cat pubkey.pub >> ~/.ssh/authorized_keys && rm pubkey.pub"
