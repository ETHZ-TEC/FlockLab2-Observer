#!/bin/bash

# NOTE: no need to unexport and export!
# reset GPIOs export to ensure initial state is NOT EXPORTED
#echo 47 > /sys/class/gpio/unexport
# export GPIOs
#echo 47 > /sys/class/gpio/export

# set direction
echo out > /sys/class/gpio/gpio47/direction
echo out > /sys/class/gpio/gpio27/direction
echo out > /sys/class/gpio/gpio26/direction
echo out > /sys/class/gpio/gpio46/direction
echo out > /sys/class/gpio/gpio65/direction
echo out > /sys/class/gpio/gpio44/direction
echo out > /sys/class/gpio/gpio68/direction
echo out > /sys/class/gpio/gpio67/direction
echo out > /sys/class/gpio/gpio76/direction
echo out > /sys/class/gpio/gpio22/direction
# NOTE PRU1 input pins already configured via device tree overlay
#echo in  > /sys/class/gpio/gpio75/direction # Target_LED1
#echo in  > /sys/class/gpio/gpio73/direction # Target_LED2
#echo in  > /sys/class/gpio/gpio71/direction # Target_LED3
#echo in  > /sys/class/gpio/gpio72/direction # Target_INT1
#echo in  > /sys/class/gpio/gpio70/direction # Target_INT2
echo out > /sys/class/gpio/gpio88/direction
echo out > /sys/class/gpio/gpio77/direction
echo out > /sys/class/gpio/gpio81/direction

# set pin state
echo 1 > /sys/class/gpio/gpio47/value # select0
echo 1 > /sys/class/gpio/gpio27/value # select1
echo 1 > /sys/class/gpio/gpio26/value # power_EN
echo 0 > /sys/class/gpio/gpio46/value # Target_nEN
echo 0 > /sys/class/gpio/gpio65/value # act_nEN
echo 1 > /sys/class/gpio/gpio44/value # JLink_nRST
echo 1 > /sys/class/gpio/gpio68/value # USB_nRST
echo 1 > /sys/class/gpio/gpio67/value # GNSS_nRST
echo 1 > /sys/class/gpio/gpio76/value # Target_nRST
echo 0 > /sys/class/gpio/gpio22/value # MUX_nEN
echo 0 > /sys/class/gpio/gpio88/value # Target_SIG1
echo 0 > /sys/class/gpio/gpio77/value # Target_SIG2
echo 0 > /sys/class/gpio/gpio81/value # Target_PROG

# get pin state
# /sys/class/gpio/gpioXX/value
