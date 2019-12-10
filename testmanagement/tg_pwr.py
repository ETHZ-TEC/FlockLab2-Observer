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

import os, sys, getopt, errno
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
	print "Usage: %s --state={on,off} [--target=<int>] [--status] [--quiet] [--help] [--version]" %sys.argv[0]
	print "Turn target power on or off."
	print "Options:"
	print "  --state\t\t\tSet to on if target(s) should be turned on, set to off to turn off."
	print "  --target\t\t\tOptional. If set, the requested target is turned on. Otherwise all targets are turned on."
	print "  --status\t\t\tOptional. Used in combination with --target, returns 1 if target is on, 0 if target is off."
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

	target = None
	state  = False
	status = False
	quiet  = False
		
	# Open the syslog:
	openlog('tg_pwr', LOG_CONS | LOG_PID | LOG_PERROR, LOG_USER)

	# Get command line parameters.
	try:								
		opts, args = getopt.getopt(argv, "hvaqs:t:", ["help", "version", "status", "quiet", "state=", "target="])
	except getopt.GetoptError, err:
		syslog(LOG_ERR, str(err))
		usage()
		sys.exit(errno.EINVAL)
	for opt, arg in opts:
		if opt in ("-s", "--state"):
			state = arg
			if arg not in ("on", "off"):
				syslog(LOG_ERR, "Wrong API usage: %s" %str(arg))
				print arg
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
		
		else:
			if not quiet:
				print "Wrong API usage"
				usage()
			syslog(LOG_ERR, "Wrong API usage")
			sys.exit(errno.EINVAL)
			
	if ((status==False) and (state==False)) or ((status==True) and (target==None)):
		if not quiet:
			print "Wrong API usage"
			usage()
		syslog(LOG_ERR, "Wrong API usage")
		sys.exit(errno.EINVAL)
	
	# If --status flag is set, return status of selected target:
	if status:
		rs = flocklab.tg_pwr_get(target)
		if not quiet:
			sys.stdout.write('%d\n'%rs)
		sys.exit(rs)
		
		
	# Change state of the desired target(s):
	if (state == "on"):
		value = 1
	else:
		value = 0
	if target:
		flocklab.tg_pwr_set(target, value)
	else:
		for i in range(1,5):
			flocklab.tg_pwr_set(i, value)
	
	sys.exit(SUCCESS)
	
### END main()

if __name__ == "__main__":
	main(sys.argv[1:])
