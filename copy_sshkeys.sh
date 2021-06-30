#!/bin/bash

# replaces the default rocketlogger ssh key with custom flocklab keys
# the keyfile required to deploy these new public keys is available in the RocketLogger wiki:
#   https://github.com/ETHZ-TEC/RocketLogger/wiki/software

PUBLICKEYS="ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCv7FL3sInVOfyhD4VHqxhOoMslxyH+gkoF7qXRtpdAVJDKbR4D8d5GI5Teqh630uVm30ZjFr00NXl/qURyQL/1p2ARgIJv5fdMm4kJNWIIC2KAlsQNa/ebKkdv8cN+Hov1f4/aADbpsild+AmnNGBD5vRcUpLMvdISf8/8hd6FfF8SaF8at7J39rufLCsBHqnI/LZ4fOeBFHnyfGJP8VCYeItVKrPqyw6h/HuStywMv8s9LEsR0wgD5WUwkbOlIBEleycHAZVSiEM6TlkvG1GYGPnuxR5ndFjYvOXSkiWvVoGAd8UHB+lUIjQJyZeT8IVxHH9UI0j/HtNOrbPuatzF flocklab-observer
ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQDBcoTMTdWOyMcpX1IZlnz0e6eohoaxu/GNiHNAbTPg1TO+Lkgskf2UWfCLcoTS/CqY1KXU91wvcYz6pLPGNwDNsoEPbDvCyWz8jDJaEvrtRZhw0Ay8DA7/3ul3Gf431xXCl7kbRcPMtTAoBTvemk+bGrzVXCr0awwuBjC62rSEjiYac06OwOGxnLIkbkfgiBtyPOCrC8grBUBRTemNGNwrkTEM1t7m/2qC43F2XvjKHwDPAa+JZRhYi0PKaZdkHFSJln2nR0v8aumBN4eofUVVoDQW0uO1mlsWutKGX4DHK9ZI02KhfqaaNnmGNf7uMtztsxpf0a7QrE+mHkTaHbDS+XTD/ZLg49hyfxmxdK9fgrrOibbS0c9UYGIHl7tCePJqq7DSGrM0Spp0lQXGj3sXrwza/YnQlmEMwbNqV0k2FLT252eGrrihucZ6iADGTaMVhh43qmKfpj9Giatr7dj4SzZC47KwJNqypp3p83RUBfCWkUD9lKmranC+RN15Phh3y1u1HA0EvOTduQBJuvFhSb4NeHpbHEiX5M8rpZ7iFKoi2DAvGVG3r6KutMbBB8DFmOdBhWpz9dN4AE9SB9J3w2HFzoxa0JmZlQFYeKJjQ/SIKWp1k8saeXFxzyTNCBdbWYo6NmITetjIg1vAsGyE+xu3YRxQc8TeVX62LkxDDw== flocklab@whymper"

PORT=2322
USER=flocklab

# check argument
if [ $# -lt 2 ]; then
  echo "Usage: ./setup_observer.sh <beaglebone-host-address> <ssh keyfile>"
  exit 1
fi
if [ ! -e $2 ]; then
  echo "File '$2' does either not exist or cannot be accessed"
  exit 1
fi

HOST=$1
KEYFILE=$2

# remove IP address / host name from known_hosts file
IPADDR=$(host $HOST | awk '{print $NF}')
HOSTNAME=$(host $HOST | awk '{print $1}')
ssh-keygen -R "[${HOSTNAME}]:${PORT}" > /dev/null 2>&1
ssh-keygen -R "[${IPADDR}]:${PORT}" > /dev/null 2>&1

ssh -p $PORT -i $KEYFILE -t ${USER}@$HOST "echo '$PUBLICKEYS' > flkeys.pub && sudo cat flkeys.pub > ~/.ssh/authorized_keys && rm flkeys.pub"
