#!/bin/bash

./init_gpio.sh
./select_target.sh 2
./set_v_target.sh 3000

echo 0 > /sys/class/gpio/gpio26/value # power_EN
echo 1 > /sys/class/gpio/gpio65/value # act_nEN
