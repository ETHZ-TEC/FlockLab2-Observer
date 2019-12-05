#!/bin/bash

# NOTE: only works with rproc (not with the older UIO method)

PRU_CORE=1

if [ "$#" -lt 1 ]; then
	echo "usage: $0 [fw file (.out)]"
	exit 1
fi

if [ ! -f $1 ]; then
	echo "file $1 not found"
	exit 1
fi

FWFILE=$1

if [[ ! $FWFILE = *.out ]]; then
	echo "invalid file"
	exit 1
fi

cp $FWFILE /lib/firmware/am335x-pru$PRU_CORE-fw

if [ $PRU_CORE -eq 0 ]
then
    echo 'stop' > /sys/class/remoteproc/remoteproc1/state 2>/dev/null
    echo "am335x-pru0-fw" > /sys/class/remoteproc/remoteproc1/firmware
    echo 'start' > /sys/class/remoteproc/remoteproc1/state
else
    echo 'stop' > /sys/class/remoteproc/remoteproc2/state 2>/dev/null
    echo "am335x-pru1-fw" > /sys/class/remoteproc/remoteproc2/firmware
    echo 'start' > /sys/class/remoteproc/remoteproc2/state
fi

echo "firmware $FWFILE successfully deployed to PRU$PRU_CORE"
