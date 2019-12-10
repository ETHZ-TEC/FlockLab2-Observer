#! /usr/bin/env python

__author__	  = "Christoph Walser <walser@tik.ee.ethz.ch>"
__copyright__   = "Copyright 2011, ETH Zurich, Switzerland, Christoph Walser"
__license__	 = "GPL"
__version__	 = "$Revision$"
__date__		= "$Date$"
__id__		  = "$Id$"
__source__	  = "$URL$"

"""
This file belongs to /usr/bin/ on the observer
"""

import os, sys, getopt, errno, subprocess
from syslog import *
# Import local libraries:
sys.path.append('/usr/lib/flocklab/python/')
import flocklab
from flocklab import SUCCESS

### Global variables ###
###
version = filter(str.isdigit, __version__)
###



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
	print "Usage: %s [--voltage=<int>] [--forcepwm] [--target=<int>] [--status] [--quiet] [--help] [--version]" %sys.argv[0]
	print "Set/read target voltage."
	print "Options:"
	print "  --voltage\t\t\tOptional. Set voltage of target(s) to desired value. Possible Values are 18-33 (1.8V - 3.3V)."
	print "  --forcepwm\t\t\tOptional. Set force PWM mode for voltage of target(s)."
	print "  --target\t\t\tOptional. If set, the requested targets voltage is set/read. Otherwise all targets are set/read."
	print "  --status\t\t\tOptional. Used in combination with --target, returns currently set voltage of target."
	print "  --quiet\t\t\tOptional. Do not print on standard out."
	print "  --help\t\t\tOptional. Print this help."
	print "  --version\t\t\tOptional. Print version number of software and exit."
### END usage()


##############################################################################
#
# Main
#
##############################################################################
def main(argv):

	target   = None
	voltage  = False
	status   = False
	quiet	= False
	forcepwm = False
		
	# Open the syslog:
	openlog('tg_volt', LOG_CONS | LOG_PID | LOG_PERROR, LOG_USER)

	# Get command line parameters.
	try:								
		opts, args = getopt.getopt(argv, "hvaqfs:t:", ["help", "version", "status", "quiet", "forcepwm", "voltage=", "target="])
	except getopt.GetoptError, err:
		syslog(LOG_ERR, str(err))
		usage()
		sys.exit(errno.EINVAL)
	for opt, arg in opts:
		if opt in ("-s", "--voltage"):
			try:
				voltage = int(arg)
				if voltage not in range(18,37):
					raise ValueError
			except:
				syslog(LOG_ERR, "Wrong API usage: %s" %str(arg))
				usage()
				sys.exit(errno.EINVAL)
			
		elif opt in ("-t", "--target"):
			try:
				target = int(arg)
				if ( (target < 1) or (target > 4) ):
					raise ValueError
			except:
				syslog(LOG_ERR, "Wrong API usage: %s" %str(arg))
				usage()
				sys.exit(errno.EINVAL)
			
		elif opt in ("-h", "--help"):
			usage()
			sys.exit(SUCCESS)
		
		elif opt in ("-v", "--version"):
			print version
			sys.exit(SUCCESS)
		
		elif opt in ("-a", "--status"):
			status = True
		
		elif opt in ("-q", "--quiet"):
			quiet = True
			
		elif opt in ("-f", "--forcepwm"):
			forcepwm = True
			
		else:
			if not quiet:
				print "Wrong API usage"
				usage()
			syslog(LOG_ERR, "Wrong API usage")
			sys.exit(errno.EINVAL)
			
	if ((status==False) and (voltage==False)) or ((status==True) and (target==None)):
		if not quiet:
			print "Wrong API usage"
			usage()
		syslog(LOG_ERR, "Wrong API usage")
		sys.exit(errno.EINVAL)
		
	# Check if the right target interface is selected (or any at all):
	tg_if_old = flocklab.tg_interface_get()
	if (target and tg_if_old != target):
		# Activate a target interface first:
		flocklab.tg_interface_set(target)
	
	# If --status flag is set, return status of selected target:
	if status:
		# Check if target power is on. If not, turn it on: 
		tg_pwr_old = flocklab.tg_pwr_get(target)
		if tg_pwr_old == 0:
			flocklab.tg_pwr_set(target, 1)
		read_v = flocklab.tg_volt_get()
		# Reset target power to old state:
		if tg_pwr_old == 0:
			flocklab.tg_pwr_set(target, tg_pwr_old)
		if not quiet:
			sys.stdout.write('%d\n'%read_v)
		retval = read_v
	else:
		# Otherwise change voltage of the desired target(s):
		if target:
			# Check if target power is on. If not, turn it on: 
			tg_pwr_old = flocklab.tg_pwr_get(target)
			if tg_pwr_old == 0:
				flocklab.tg_pwr_set(target, 1)
			flocklab.tg_volt_set(voltage, forcepwm)
			# Reset target power to old state:
			if tg_pwr_old == 0:
				flocklab.tg_pwr_set(target, tg_pwr_old)
		else:
			# Cycle trough all targets and set voltage:
			for t in range(1,5):
				# Check if target power is on. If not, turn it on: 
				tg_pwr_old = flocklab.tg_pwr_get(t)
				if tg_pwr_old == 0:
					flocklab.tg_pwr_set(t, 1)
				flocklab.tg_interface_set(t)
				flocklab.tg_volt_set(voltage, forcepwm)
				# Reset target power to old state:
				flocklab.tg_pwr_set(t, tg_pwr_old)
		retval = SUCCESS
	
	# (Re-)activate the originally activated target interface:
	if target:
		if (tg_if_old != target): 
			flocklab.tg_interface_set(tg_if_old)
	else:
		if (tg_if_old > 0):
			flocklab.tg_interface_set(tg_if_old)
		else:
			flocklab.tg_interface_set(None)
	
	sys.exit(retval)
	
### END main()

if __name__ == "__main__":
	main(sys.argv[1:])
