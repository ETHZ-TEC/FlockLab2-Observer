#!/bin/bash

if [ $# -lt 1 ]; then
  EN=1
else
  EN=$1
fi

echo $EN > /sys/class/gpio/gpio26/value # power_EN
echo $EN > /sys/class/gpio/gpio76/value # Target_nRST
