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
	print "Usage: %s [--target=<int>] [--active] [--quiet] [--help] [--version]" %sys.argv[0]
	print "Enable interface to a specific target or disable all interfaces."
	print "Options:"
	print "  --target\t\t\tOptional. If set, the requested target's interface is enabled. If no target is given, all target's interfaces are turned off."
	print "  --active\t\t\tOptional. If set, the slot number of the currently enabled interface is returned."
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

	target = False
	active = False
	quiet  = False
		
	# Open the syslog:
	openlog('tg_interf', LOG_CONS | LOG_PID | LOG_PERROR, LOG_USER)

	# Get command line parameters.
	try:								
		opts, args = getopt.getopt(argv, "hvaqt:", ["help", "version", "active", "quiet", "target="])
	except getopt.GetoptError, err:
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
		
		elif opt in ("-a", "--active"):
			active = True
		
		elif opt in ("-q", "--quiet"):
			quiet = True
			
		elif opt in ("-h", "--help"):
			usage()
			sys.exit(SUCCESS)
		
		elif opt in ("-v", "--version"):
			print version
			sys.exit(SUCCESS)
		
		else:
			if not quiet:
				syslog(LOG_ERR, "Wrong API usage")
				usage()
			print "Wrong API usage"
			sys.exit(errno.EINVAL)
			
	# If --active flag is set, return currently active interface:
	if active:
		rs = flocklab.tg_interface_get()
		if not rs:
			rs = -1
		if not quiet:
			sys.stdout.write('%d\n'%rs)
		sys.exit(rs)
	
	"""	If --active flag is not set, there are 2 possibilities: 
			1) No target is given. Thus disable all interfaces
			2) Target was given. Thus enable selected interface
	"""
	if target:
		flocklab.tg_interface_set(target)
	else:
		flocklab.tg_interface_set(None)
		
	sys.exit(SUCCESS)
		
	
### END main()

if __name__ == "__main__":
	main(sys.argv[1:])
