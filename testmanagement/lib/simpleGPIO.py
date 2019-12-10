#! /usr/bin/env python2

__author__		= "Dario Leuchtmann <ldario@student.ethz.ch>"
__copyright__	= "Copyright 2019, ETH Zurich, Switzerland, Dario Leuchtmann"
__license__		= "GPL"
__version__		= "$Revision$"
__date__		= "$Date$"
__id__			= "$Id$"
__source__		= "$URL$"

"""
This file belongs to /usr/lib/flocklab/python/ on the observer
"""
import sys, getopt, subprocess, errno
import Adafruit_BBIO.GPIO as GPIO

### Global variables ###
pin = None
direction = None
value = 0

##############################################################################
#
# Main
#
##############################################################################
def main(argv):
	# Get command line parameters.
	try:								
		opts, args = getopt.getopt(argv, "p:d:v:", ["pin=", "direction=", "value="])
	except(getopt.GetoptError) as err:
		print(str(err))
		usage()
		sys.exit(errno.EINVAL)

	for opt, arg in opts:	  
		if opt in ("-p", "--pin"):
			pin = str(arg)	
		elif opt in ("-d", "--direction"):
			direction = str(arg)
		elif opt in ("-v", "--value"):
			value = int(arg)
		else:
			print("Wrong API usage")
			usage()
			sys.exit(errno.EINVAL)

	if direction == "out":
		GPIO.setup(pin, GPIO.OUT)
		if value == 0:
			GPIO.output(pin, GPIO.LOW)
		else:
			GPIO.output(pin, GPIO.HIGH)
	else:
		GPIO.setup(pin, GPIO.IN)
		if GPIO.input(pin):
			value = 1
		else:
			value = 0

		return value

	return -1

if __name__ == "__main__":
	main(sys.argv[1:])