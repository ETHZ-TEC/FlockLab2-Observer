#!/bin/bash

# RocketLogger installation script for FlockLab 2 observers

HOMEDIR="/home/flocklab"

PWMUDEVRULE=$(cat <<- END
# /etc/udev/rules.d/81-pwm-noroot.rules
#
# ReWritten by: Matthijs van Duin
# Corrects sys PWM permissions on the BB so non-root users in the pwm group can
# manipulate pwm along with creating a symlink under /dev/pwm/
#
SUBSYSTEM=="pwm", ACTION=="add", \
        RUN+="/bin/chgrp -R pwm '/sys%p'", \
        RUN+="/bin/chmod -R g=u '/sys%p'"

# automatically export pwm channels
SUBSYSTEM=="pwm", KERNEL=="pwmchip*", ACTION=="add",  ATTR{export}="0"
SUBSYSTEM=="pwm", KERNEL=="pwmchip*", ACTION=="add", ATTR{npwm}!="1",  ATTR{export}="1"

# identify pwm peripherals on am335x
SUBSYSTEM=="pwm", KERNELS=="48300100.*",  ENV{PWMCHIP_NAME}="ecap0"
SUBSYSTEM=="pwm", KERNELS=="48300200.*",  ENV{PWMCHIP_NAME}="ehrpwm0"
SUBSYSTEM=="pwm", KERNELS=="48302100.*",  ENV{PWMCHIP_NAME}="ecap1"
SUBSYSTEM=="pwm", KERNELS=="48302200.*",  ENV{PWMCHIP_NAME}="ehrpwm1"
SUBSYSTEM=="pwm", KERNELS=="48304100.*",  ENV{PWMCHIP_NAME}="ecap2"
SUBSYSTEM=="pwm", KERNELS=="48304200.*",  ENV{PWMCHIP_NAME}="ehrpwm2"

# identify pwm peripherals on am57xx/dra7xx
SUBSYSTEM=="pwm", KERNELS=="4843e100.*",  ENV{PWMCHIP_NAME}="ecap0"
SUBSYSTEM=="pwm", KERNELS=="4843e200.*",  ENV{PWMCHIP_NAME}="ehrpwm0"
SUBSYSTEM=="pwm", KERNELS=="48440100.*",  ENV{PWMCHIP_NAME}="ecap1"
SUBSYSTEM=="pwm", KERNELS=="48440200.*",  ENV{PWMCHIP_NAME}="ehrpwm1"
SUBSYSTEM=="pwm", KERNELS=="48442100.*",  ENV{PWMCHIP_NAME}="ecap2"
SUBSYSTEM=="pwm", KERNELS=="48442200.*",  ENV{PWMCHIP_NAME}="ehrpwm2"

# identify pwm channels
SUBSYSTEM=="pwm", ENV{DEVTYPE}=="pwm_channel", ENV{PWMCHIP_NAME}!="", ATTR{../npwm}=="1",  ENV{PWM_NAME}="%E{PWMCHIP_NAME}"
SUBSYSTEM=="pwm", ENV{DEVTYPE}=="pwm_channel", ENV{PWMCHIP_NAME}!="", DRIVERS=="ehrpwm", KERNEL=="*:0",  ENV{PWM_NAME}="%E{PWMCHIP_NAME}a"
SUBSYSTEM=="pwm", ENV{DEVTYPE}=="pwm_channel", ENV{PWMCHIP_NAME}!="", DRIVERS=="ehrpwm", KERNEL=="*:1",  ENV{PWM_NAME}="%E{PWMCHIP_NAME}b"

# create symlinks in /dev/pwm
SUBSYSTEM=="pwm", ENV{DEVTYPE}=="pwm_channel", ACTION=="add", ENV{PWM_NAME}!="", \
        RUN+="/bin/mkdir -p /dev/pwm", \
        RUN+="/bin/ln -sT '/sys/class/pwm/%k' /dev/pwm/%E{PWM_NAME}"
END
)

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
# install dependencies
echo "       Updating system..."
echo "deb http://deb.debian.org/debian stretch-backports main" > /etc/apt/sources.list.d/stretch-backports.list
apt-get update > /dev/null && apt-get install --assume-yes ninja-build meson/stretch-backports pkg-config libzmq3-dev libncurses5-dev > /dev/null
check_retval "Install dependencies"

##########################################################
# install udev rule
echo "$PWMUDEVRULE" > /etc/udev/rules.d/81-pwm-noroot.rules
check_retval "Add udev rule for PWM device"

##########################################################
# install rocketlogger software
cd ${HOMEDIR}
[ -e RocketLogger ] && rm -rf RocketLogger
git clone --quiet --single-branch --branch flocklab --depth 1 https://github.com/ETHZ-TEC/RocketLogger.git
check_retval "Code download"
cd ${HOMEDIR}/RocketLogger/software/rocketlogger
meson builddir > /dev/null && cd builddir && ninja > /dev/null
check_retval "Compile and install"
meson install --no-rebuild > /dev/null
cd ${HOMEDIR} && rm -rf RocketLogger

##########################################################
# restart RocketLogger service
systemctl daemon-reload && systemctl restart rocketlogger && sleep 2 && systemctl is-active --quiet rocketlogger
check_retval "Restart service"
