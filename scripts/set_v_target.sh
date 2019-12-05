#!/bin/bash

I2CIF=2
SLAVEADDR=0x60
REG=0x0

if [ $# -lt 1 ]; then
	echo "usage: $0 [voltage in mV]"
	exit 1
fi

if [ $1 -gt 3600 ] || [ $1 -lt 1000 ]; then
	echo "invalid voltage (allowed range: 1000 - 3600mV)"
	exit 1
fi

# map mV to the DAC value range (0..255)

VREF=800  # mV
VDD=3375  # mV
R11R12=1.04
R11R13=3.55
VOUT=$1
VDAC=$(echo "$VREF - ($R11R12*($VOUT - $VREF*$R11R13))" | bc)
VAL=$(echo "obase=16; $VDAC*255 / $VDD" | bc)
#echo "$VDAC and $VAL"
i2cset -y $I2CIF $SLAVEADDR $REG "0x${VAL}00" w
