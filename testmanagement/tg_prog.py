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

import os, sys, getopt, subprocess, errno, time, serial
# Import local libraries:
sys.path.append('/usr/lib/flocklab/python/')
from flocklab import SUCCESS
import flocklab


### Global variables ###
###
version = filter(str.isdigit, __version__)
###
imagefile	= None
target	   	= None
targetlist  = ('tmote', 'dpp')
porttypelist= ('usb', 'serial')
porttype	= None
pin_rst	  	= "P8_9"
pin_prog	= "P8_28"
pin_sig1	= "P8_45"
pin_sig2	= "P8_46"
noreset		= False
debug		= False


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
	print("Usage: %s --image=<path> --target=<string> [--port=<string>] [--core=<int>] [--noreset] [--debug] [--help] [--version]" %sys.argv[0])
	print("Reprogram a target node on the FlockBoard. The target will be turned on after the reprogramming.")
	print("Options:")
	print("  --image=<path>\t\tAbsolute path to image file which is to be flashed onto target node")
	print("  --target=<string>\t\tType of target. Allowed targets: %s" %(", ".join(targetlist)))
	print("  --port=<string>\t\tOptional. Specify port which is used for reprogramming. Allowed values are: %s. Defaults: usb for tmote, serial for dpp." %(", ".join(porttypelist)))
	print("  --core=<int>\t\tOptional. Specify core to program. Defaults to 0.")
	print("  --noreset\t\t\tOptional. If set, node will not be reset after reprogramming.")
	print("  --debug\t\t\tOptional. Print debug messages to log.")
	print("  --help\t\t\tOptional. Print this help.")
	print("  --version\t\t\tOptional. Print version number of software and exit.")
### END usage()

##############################################################################
#
# Helper functions
#
##############################################################################
def reprog_msp430bsl5_common(imagefile, slotnr, port, prog_toggle_num=1, progstate=0, speed=38400):
	usleep = 0.00005

	#rst = simpleGPIO.SimpleGPIO(pin_rst)
	#prog = simpleGPIO.SimpleGPIO(pin_prog)
	flocklab.tg_press_gpio(pin_rst, 0)
	flocklab.tg_press_gpio(pin_prog, 1)
	
	#rst.write(0)
	#prog.write(1)

	time.sleep(usleep)
	
	for i in range(0, prog_toggle_num):
		#prog.write(0)
		flocklab.tg_press_gpio(pin_prog, 0)
		time.sleep(usleep)
	
		#prog.write(1)
		flocklab.tg_press_gpio(pin_prog, 1)
		time.sleep(usleep)
	
	#rst.write(1)
	flocklab.tg_press_gpio(pin_rst, 1)
	time.sleep(usleep)

	#prog.write(0)
	flocklab.tg_press_gpio(pin_prog, 0)
	
	if progstate == 1:
		time.sleep(usleep)
		#prog.write(1)
		flocklab.tg_press_gpio(pin_prog, 1)

	import msp430.bsl5.uart
	
	#cmd = ["-p", port, "-e", "-S", "-V", "--speed=%d" %speed, "-i", "ihex", "-P", imagefile]
	cmd = ["python","-m","msp430.bsl5.uart","-p", port, "-e", "-S", "-V", "--speed=%d" %speed, "-i", "ihex", "-P", imagefile, "-v", "--debug"]
	
	if debug:
		cmd.append("-vvvvvvvvv")
		cmd.append("--debug")
	#bsl =  msp430.bsl5.uart.SerialBSL5Target()
	try:
		#bsl.main(cmd)
		subprocess.call(cmd)
		print("TEST2")
	except Exception:
		flocklab.tg_reset(usleep)
		return 3
	
	# Revert back all config changes:
	subprocess.call(["stty", "-F", port, "-parenb", "iexten", "echoe", "echok", "echoctl", "echoke", "115200"])
	#set_pin(pin_prog, 0)
	#prog.write(0)
	flocklab.tg_press_gpio(pin_prog, 0)
	
	# Reset if not forbidden by caller: 
	if noreset:
		flocklab.tg_reset_keep()
	else:
		flocklab.tg_reset(usleep)

	return 0
### END reprog_cc430()


##############################################################################
#
# reprog_dpp
#
##############################################################################
def reprog_dpp(imagefile, slotnr, core):
	port   = '/dev/ttyO2'
	core2sig = ((0,0),(1,0),(0,1),(1,1)) # (sig1,sig2)

	# select core
	#sig1 = simpleGPIO.SimpleGPIO(pin_sig1)
	#sig2 = simpleGPIO.SimpleGPIO(pin_sig2)

	#sig1.write(core2sig[core][0])
	#sig2.write(core2sig[core][1])
	flocklab.tg_press_gpio(pin_sig1, core2sig[core][0])
	flocklab.tg_press_gpio(pin_sig2, core2sig[core][1])
	
	# program
	ret = 1
	if core == 0: # COMM
		ret = reprog_msp430bsl5_common(imagefile, slotnr, port, progstate = 1, speed=115200)
	elif core == 1: # BOLT
		ret = reprog_msp430bsl5_common(imagefile, slotnr, port, speed=115200)
	elif core == 2: # APP
		ret = reprog_msp432(imagefile, slotnr, port, 57600)
	elif core == 3: # SENSOR
		ret = reprog_msp430bsl5_common(imagefile, slotnr, port, progstate = 1, speed=115200)
		
	#sig1.write(0)
	#sig2.write(0)
	flocklab.tg_press_gpio(pin_sig1, 0)
	flocklab.tg_press_gpio(pin_sig2, 0)

	return ret
### END reprog_dpp()

def reprog_msp432(imagefile, slotnr, port, speed):
	usleep = 0.0005
	import msp430.bsl5.uart
	
	#TODO: For FlockBoard the reset has to be inverted.
	#rst = simpleGPIO.SimpleGPIO(pin_rst)
	#prog = simpleGPIO.SimpleGPIO(pin_prog)

	#rst.write(0)
	flocklab.tg_press_gpio(pin_rst, 0)
	#prog.write(1)
	flocklab.tg_press_gpio(pin_prog, 1)
	time.sleep(usleep)

	#rst.write(1)
	flocklab.tg_press_gpio(pin_rst, 1)
	time.sleep(5)

	#cmd = ["-p", port, "-e", "-S", "-V","--speed=%d" % speed, "-i", "ihex", "-P", imagefile]
	cmd = ["python","-m","msp430.bsl5.uart","-p", port, "-e", "-S", "-V","--speed=%d" % speed, "-i", "ihex", "-P", imagefile, "-v", "--debug"]
	if debug:
		cmd.append("-vvvvvvvvv")
		cmd.append("--debug")
	#bsl = msp430.bsl5.uart.SerialBSL5Target()
	try:
	#	bsl.main(cmd)
		subprocess.call(cmd)
	except Exception:
		flocklab.tg_reset(usleep)
		return 3
	
	#prog.write(0)
	flocklab.tg_press_gpio(pin_prog, 0)
	
	# Revert back all config changes:
	subprocess.call(["stty", "-F", port, "-parenb", "iexten", "echoe", "echok", "echoctl", "echoke", "115200"])
	
	# Reset if not forbidden by caller: 
	if noreset:
		flocklab.tg_reset_keep()
	else:
		flocklab.tg_reset(usleep)

	return 0
### END reprog_msp432()

##############################################################################
#
# Main
#
##############################################################################
def main(argv):
	
	### Get global variables ###
	global imagefile
	global porttype
	global noreset
	global debug
	
	# Get logger:
	logger = flocklab.get_logger("tg_reprog.py")
	
	core = 0
	
	# Get command line parameters.
	try:								
		opts, args = getopt.getopt(argv, "dhvni:t:p:c:", ["debug", "help", "version", "noreset", "image=", "target=", "port=", "core="])
	except(getopt.GetoptError) as err:
		logger.error(str(err))
		usage()
		sys.exit(errno.EINVAL)
	for opt, arg in opts:	  
		if opt in ("-h", "--help"):
			usage()
			sys.exit(SUCCESS)
			
		elif opt in ("-d", "--debug"):
			debug = True
			
		elif opt in ("-v", "--version"):
			print(version)
			sys.exit(SUCCESS)
			
		elif opt in ("-n", "--noreset"):
			noreset = True
			
		elif opt in ("-i", "--image"):
			imagefile = arg
			if not (os.path.exists(imagefile)):
				err = "Error: file %s does not exist" %(str(imagefile))
				logger.error(str(err))
				sys.exit(errno.EINVAL)
				
		elif opt in ("-t", "--target"):
			target = arg
			if not (target in targetlist):
				err = "Error: illegal target %s" %(str(target))
				logger.error(str(err))
				sys.exit(errno.EINVAL)
				
		elif opt in ("-p", "--port"):
			porttype = arg
			if not (porttype in porttypelist):
				err = "Error: illegal port %s" %(str(porttype))
				logger.error(str(err))
				sys.exit(errno.EINVAL)
		
		elif opt in ("-c", "--core"):
			core = int(arg)
				
		else:
			logger.error("Wrong API usage")
			usage()
			sys.exit(errno.EINVAL)
			
	if (imagefile == None) or (target == None):
		logger.error("Wrong API usage")
		usage()
		sys.exit(errno.EINVAL)
	
	# Set default porttypes:
	if not porttype:
		if (target in ('tmote')):
			porttype = 'usb'
		elif (target in ('dpp')):
			porttype = 'serial' 
	
	# Check port type restrictions for targets:
	if (target in ('tmote')) and (porttype != 'usb'):
		err = "Error: port type for target %s has to be usb." %target
		logger.error(str(err))
		sys.exit(errno.EINVAL)
	elif (target in ('dpp')) and (porttype != 'serial'):
		err = "Error: port type for target %s has to be serial." %target
		logger.error(str(err))
		sys.exit(errno.EINVAL)
		
	# Set environment variable needed for programmer: 
	os.environ["PYTHONPATH"] = os.environ.get("PYTHONPATH", "") + "/usr/local/lib/python2.7/"
	
	# Prepare the target for reprogramming:
	slotnr = flocklab.tg_interface_get()
	if not slotnr:
		err = "No interface active. Please activate one first."
		logger.error(err)
		sys.exit(errno.EINVAL)
	logger.debug("Active interface is target %d"%slotnr)
	# Turn on power
	flocklab.tg_pwr_set(slotnr, 1)
	# Find out voltage setting of target:
	tg_volt_state_old = flocklab.tg_volt_get()
	if (tg_volt_state_old < 0):
		tg_volt_state_old = 33
		logger.info("Currently set voltage could not be determined. Defaulting to %1.1f V"%(tg_volt_state_old/10.0))
	else:
		logger.info("Voltage is currently set to: %1.1f V"%(tg_volt_state_old/10.0))
	# set voltage to maximum:
	try:
		flocklab.tg_volt_set(33)
	except IOError:
		logger.error("Could not set voltage to 3.3V")
	# Turn on USB power if needed, otherwise turn it off.
	if porttype == 'usb':
		#TODO
		#flocklab.tg_usbpwr_set(slotnr, 1)
		logger.info("Turned on USB power")
		time.sleep(2)
	else:
		#TODO
		#flocklab.tg_usbpwr_set(slotnr, 0)
		time.sleep(2)
	
	# Flash the target:
	print("Reprogramming %s..."%target)
	if target == 'tmote':
		rs = reprog_tmote_usb(imagefile, slotnr)
	elif target == 'dpp':
		logger.info("reprog dpp with image %s, slot %d, core %d." % (imagefile, slotnr, core))
		rs = reprog_dpp(imagefile, slotnr, core)
	
	# Turn off USB power if needed:
	if porttype == 'usb':
		flocklab.tg_usbpwr_set(slotnr, 0)
		
	# Restore old status of target voltage:
	if tg_volt_state_old != 33:
		try:
			flocklab.tg_volt_set(tg_volt_state_old)
		except IOError:
			logger.error("Could not set voltage to %1.1f V"%(tg_volt_state_old/10.0))

	# Return an error if there was one while flashing:
	if (rs != 0):
		logger.error("Image could not be flashed to target. Error %d occurred."%rs)
		sys.exit(errno.EIO)
	else:
		logger.info("Target node flashed successfully.")
		sys.exit(SUCCESS)
### END main()

if __name__ == "__main__":
	main(sys.argv[1:])
