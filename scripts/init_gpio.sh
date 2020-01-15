#!/bin/bash

# NOTE: no need to unexport and export!

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
echo out > /sys/class/gpio/gpio75/direction # Target_SIG1
echo out > /sys/class/gpio/gpio76/direction # Target_SIG2
echo out > /sys/class/gpio/gpio81/direction # Target_PROG

# set pin state
echo 1 > /sys/class/gpio/gpio47/value # select0
echo 1 > /sys/class/gpio/gpio27/value # select1
echo 1 > /sys/class/gpio/gpio26/value # power_EN
echo 0 > /sys/class/gpio/gpio46/value # Target_nEN
echo 0 > /sys/class/gpio/gpio65/value # act_nEN
echo 1 > /sys/class/gpio/gpio44/value # JLink_nRST
echo 1 > /sys/class/gpio/gpio68/value # USB_nRST
echo 1 > /sys/class/gpio/gpio67/value # GNSS_nRST
echo 1 > /sys/class/gpio/gpio77/value # Target_nRST
echo 0 > /sys/class/gpio/gpio22/value # MUX_nEN
echo 0 > /sys/class/gpio/gpio75/value # Target_SIG1
echo 0 > /sys/class/gpio/gpio76/value # Target_SIG2
echo 0 > /sys/class/gpio/gpio81/value # Target_PROG

# get pin state
# /sys/class/gpio/gpioXX/value
