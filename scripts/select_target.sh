#!/bin/bash

if [ $# -lt 1 ] ; then
	echo "usage: $0 [target_no]"
	exit 1
fi


if [ $1 -eq 4 ] ; then
	echo 0 > /sys/class/gpio/gpio47/value # select0
	echo 0 > /sys/class/gpio/gpio27/value # select1
elif [ $1 -eq 3 ] ; then
	echo 1 > /sys/class/gpio/gpio47/value # select0
	echo 0 > /sys/class/gpio/gpio27/value # select1
elif [ $1 -eq 2 ] ; then
	echo 0 > /sys/class/gpio/gpio47/value # select0
	echo 1 > /sys/class/gpio/gpio27/value # select1
elif [ $1 -eq 1 ] ; then
	echo 1 > /sys/class/gpio/gpio47/value # select0
	echo 1 > /sys/class/gpio/gpio27/value # select1
fi
