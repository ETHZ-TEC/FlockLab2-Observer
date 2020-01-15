#! /usr/bin/env python3

__author__		= "Dario Leuchtmann <ldario@student.ethz.ch>"
__copyright__	= "Copyright 2019, ETH Zurich, Switzerland, Dario Leuchtmann"
__license__		= "GPL"
__version__		= "$Revision$"
__date__		= "$Date$"
__id__			= "$Id$"
__source__		= "$URL$"

"""
This file belongs to /usr/bin/ on the observer
"""

import os, signal, sys, getopt, socket, time, subprocess, multiprocessing, Queue, threading, errno, traceback, pickle, tempfile, __main__
from xml.etree.ElementTree import ElementTree
from syslog import *
# Import local libraries:
sys.path.append('/usr/lib/flocklab/python/')
import daemon
from flocklab import SUCCESS
import flocklab
import Adafruit_BBIO.GPIO as GPIO

### Global variables ###
###
debug		=	False
xml			=	None
log_file	=	None
th			=	None
value		=	""

def gpio_trigger_thread(pin, edge, mode):
	GPIO.setup(pin, GPIO.IN)
	if GPIO.input(pin):
		value = "High"
	else:
		value = "Low"

	f = open(log_file, "ab")
	f.write("%s;%s;%s\n" %(flocklab.pin_num2abbr(pin), str(time.time()), value))
	f.close()

	if os.path.exists(log_file):
		syslog(LOG_INFO, "File exists")
	else:
		f = open(log_file, "wb")
		f.write("%s;%s;%s\n" %(flocklab.pin_num2abbr(pin), str(time.time()), value))
		f.close()
		if os.path.exists(log_file):
			syslog(LOG_INFO, "File exists now")
		else:
			syslog(LOG_INFO, "File still does not exist")

	if value == "Low":
		value = "High"
	else:
		value = "Low"

	gpio_edge = None
	if edge == "both":
		gpio_edge = GPIO.BOTH
	elif edge == "rising":
		gpio_edge = GPIO.RISING
	elif edge == "falling":
		gpio_edge = GPIO.FALLING

	while True:
		GPIO.wait_for_edge(pin, gpio_edge)
		f = open(log_file, "ab")
		f.write("%s;%s;%s\n" %(flocklab.pin_num2abbr(pin), str(time.time()), value))
		f.close()
		# Switch value
		if value == "Low":
			value = "High"
		else:
			value = "Low"

### END reset_thread()

##############################################################################
#
# Main
#
##############################################################################
def main(argv):

	global debug
	global xml
	global log_file
	global th
	global value

	# Get config:
	config = flocklab.get_config()
	if not config:
		syslog(LOG_INFO, "Could not read configuration file. Exiting...")
		sys.exit(errno.EAGAIN)

	# Get command line parameters.
	try:								
		opts, args = getopt.getopt(argv, "x:f:", ["xml=", "file="])
	except (getopt.GetoptError) as err:
		syslog(LOG_INFO, str(err))
		sys.exit(errno.EINVAL)

	for opt, arg in opts:
		if opt in ("-x", "--xml"):
			xml = str(arg)
		elif opt in ("-f", "--file"):
			log_file = str(arg)

	try:
		tree = ElementTree()
		tree.parse(xml)
		if (tree.find('obsGpioSettingConf') != None):
			# Cycle through all configs and start threads:
			subtree = tree.find('obsGpioMonitorConf')
			pinconfs = list(subtree.getiterator("pinConf"))
			for pinconf in pinconfs:
				pin = flocklab.pin_abbr2num(pinconf.find('pin').text)
				edge = pinconf.find('edge').text
				mode = pinconf.find('mode').text
				# Start the thread
				th = threading.Thread(target = gpio_trigger_thread, args=(pin,edge,mode,))
				th.daemon = True
				th.start()
	except Exception as error:
		syslog(LOG_INFO, "An error occured: %s" % str(error))

	sys.exit(SUCCESS)

### END main()


if __name__ == "__main__":
	try:
		main(sys.argv[1:])
	except SystemExit:
		pass
	except:
		syslog(LOG_ERR, "Encountered error in line %d: %s: %s: %s\n\n--- traceback ---\n%s--- end traceback ---\n\nCommandline was: %s" % (traceback.tb_lineno(sys.exc_info()[2]), str(sys.exc_info()[0]), str(sys.exc_info()[1]), str(traceback.print_tb(sys.exc_info()[2])), traceback.format_exc(), str(sys.argv)))
		sys.exit(errno.EAGAIN)
