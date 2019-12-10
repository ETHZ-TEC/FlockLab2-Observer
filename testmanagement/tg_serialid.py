#! /usr/bin/env python

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

import os, sys, getopt, errno, subprocess, time
from syslog import *
#TODO change path to the flocklab python script
sys.path.append('/usr/lib/flocklab/python/')
from flocklab import SUCCESS
import flocklab

### Global variables ###
###
version = filter(str.isdigit, __version__)
###

maxretries = 5		# Number of times the script retries to read when no serial ID was read.
searchtime = 0.1	# How long to wait for master search


##############################################################################
#
# Error classes
#
##############################################################################
class Error(Exception):
	"""Base class for exceptions in this module."""
	pass
### END Error classes



##############################################################################
#
# Usage
#
##############################################################################
def usage():
	print("Usage: %s [--target=<int>] [--searchtime=<float>] [--maxretries=<int>] [--help] [--version]" %sys.argv[0])
	print("Get serial ID of target adaptor(s).")
	print("Options:")
	print("  --target\t\t\tOptional. If set, the serial ID of the requested target is fetched. Otherwise ID's of all targets are fetched.")
	print("  --searchtime\t\t\tOptional. If set, standard time of %.1fs for waiting for the ID search is overwritten." %searchtime)
	print("  --maxretries\t\t\tOptional. If set, standard number of retries of %d for reading an ID is overwritten." %maxretries)
	print("  --help\t\t\tOptional. Print this help.")
	print("  --version\t\t\tOptional. Print version number of software and exit.")
### END usage()



##############################################################################
#
# Main
#
##############################################################################
def main(argv):

	target = None
	global searchtime
	global maxretries
		
	# Open the syslog:
	openlog('tg_serialid', LOG_CONS | LOG_PID | LOG_PERROR, LOG_USER)

	# Get command line parameters.
	try:								
		opts, args = getopt.getopt(argv, "hvt:s:m:", ["help", "version", "target=", "searchtime=", "maxretries="])
	except (getopt.GetoptError) as err:
		syslog(LOG_ERR, str(err))
		usage()
		sys.exit(errno.EINVAL)
	for opt, arg in opts:
		if opt in ("-t", "--target"):
			try:
				target = int(arg)
				if ( (target < 1) or (target > 4) ):
					raise ValueError
			except:
				syslog(LOG_ERR, "Wrong API usage: %s" %str(arg))
				usage()
				sys.exit(errno.EINVAL)
				
		elif opt in ("-s", "--searchtime"):
			try:
				searchtime = float(arg)
				if (searchtime <= 0.0):
					raise ValueError
			except:
				syslog(LOG_ERR, "Wrong API usage: %s" %str(arg))
				usage()
				sys.exit(errno.EINVAL)
		
		elif opt in ("-m", "--maxretries"):
			try:
				maxretries = int(arg)
				if (maxretries < 0):
					raise ValueError
			except:
				syslog(LOG_ERR, "Wrong API usage: %s" %str(arg))
				usage()
				sys.exit(errno.EINVAL)
			
		elif opt in ("-h", "--help"):
			usage()
			sys.exit(SUCCESS)
		
		elif opt in ("-v", "--version"):
			print(version)
			sys.exit(SUCCESS)
		
		else:
			print("Wrong API usage")
			syslog(LOG_ERR, "Wrong API usage")
			usage()
			sys.exit(errno.EINVAL)
			
	# Check if the necessary kernel modules are loaded:
	w1_gpio = False
	w1_smem = False
	rs1 = 0
	rs2 = 0
	FILE = open('/proc/modules', 'r')
	lines = FILE.readlines()
	FILE.close()
	for line in lines:
		if line.startswith('w1_gpio'):
			w1_gpio = True
		if line.startswith('w1_smem'):
			w1_smem = True
	if w1_gpio == False:
		rs1 = subprocess.call(["modprobe", "w1_gpio"])
	if w1_smem == False:
		rs2 = subprocess.call(["modprobe", "w1_smem"])
	if (rs1 != 0) or (rs2 != 0):
		print("Could not load needed kernel modules.")
		syslog(LOG_ERR, "Could not load needed kernel modules.")
		sys.exit(errno.EFAULT)
	
	# Get the serial ID of the requested targets:
	if (target == None):
		targets = [1,2,3,4]
	else:
		targets = [target]
	for target in targets:
		# Remove all stored serial ID's:
		FILE = open('/sys/bus/w1/devices/w1_bus_master1/w1_master_slaves', 'r')
		lines = FILE.readlines()
		FILE.close()
		if (lines[0].startswith("not found.") == False):
			for line in lines:
				FILE = open('/sys/bus/w1/devices/w1_bus_master1/w1_master_remove', 'w')
				FILE.write(line)
				FILE.close()
		
		# Turn on interface:
		try:
			flocklab.tg_interface_set(target)
		except:
			err = "Could not enable interface for target %i." %target
			print(err)
			syslog(LOG_ERR, err)
			sys.exit(errno.EFAULT)
		# Read out serial ID:
		retries = 0
		while (retries < maxretries):
			FILE = open('/sys/bus/w1/devices/w1_bus_master1/w1_master_search', 'w')
			FILE.write(str(1))
			FILE.close()
			time.sleep(searchtime)
			FILE = open('/sys/bus/w1/devices/w1_bus_master1/w1_master_slaves', 'r')
			sid = FILE.readline()
			FILE.close()
			if not sid.startswith("not found."):
				break
			retries += 1
		print("%i: %s" %(target, sid))
		
		
	
	
	sys.exit(SUCCESS)
	
### END main()

if __name__ == "__main__":
	main(sys.argv[1:])
