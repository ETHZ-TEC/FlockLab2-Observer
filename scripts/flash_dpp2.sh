#!/bin/sh
#
# 2019 rdaforno

JLINK=jlink/JLinkExe

if [ "$#" -ne 1 ]; then
	echo "no filename provided"
	exit 1
fi

if [ ! -f $1 ]; then
	echo "file '$1' not found"
	exit 2
fi

printf "loadfile $1\nr\nq\n" | $JLINK -device STM32L433CC -if SWD -speed auto -autoconnect 1

exit 0
