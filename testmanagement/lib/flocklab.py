__author__		= "Dario Leuchtmann <ldario@student.ethz.ch>"
__copyright__	= "Copyright 2019, ETH Zurich, Switzerland, Dario Leuchtmann"
__license__		= "GPL"
__version__		= "$Revision$"
__date__		= "$Date$"
__id__			= "$Id$"
__source__		= "$URL$"

"""
!!!IMPORTANT!!! This file belongs to /usr/lib/flocklab/python/ on the FlockLab server
"""

# Needed imports:
import sys, os, errno, signal
import time
import configparser
import logging
import logging.config
import subprocess
#import simpleGPIO
import traceback
import glob
from syslog import *
from os import listdir
from os.path import isfile, join
import shutil

### Global variables ###
tg_rst				= "P8_9"
tg_prog				= "P8_28"
tg_sig1				= "P8_45"
tg_sig2				= "P8_46"
tg_interf_addr0		= ""		#TBD
tg_interf_addr1		= ""		#TBD
tg_interf_enable	= ""		#TBD
tg_pwr_path			= ""		#TBD (target dependent)
tg_usbpwr_path		= ""		#TBD (target dependent)
tg_power_3_3		= ""		#TBD
LM3370PATH			= '/proc/lm3370'

# Error code to return if there was no error:
SUCCESS = 0

##############################################################################
#
# get_config - read config.ini and return it to caller.
#
##############################################################################
def get_config():
	"""Arguments: 
			none
	   Return value:
			The configuration object on success
			none otherwise
	"""
	configpath = '/home/debian/flocklab/config.ini'
	
	#try: 
	config = configparser.SafeConfigParser()
	config.read(configpath)
	#except:
	#	syslog(LOG_ERR, "Could not read %s because: %s: %s" %(configpath, str(sys.exc_info()[0]), str(sys.exc_info()[1])))
	#	config = None
	return config
### END get_config()


##############################################################################
#
# get_logger - Open a logger for the caller.
#
##############################################################################
def get_logger(loggername=""):
	"""Arguments: 
			loggername
	   Return value:
			The logger object on success
			none otherwise
	"""
	configpath = '/home/debian/flocklab/logging.conf'
	
	try:
		logging.config.fileConfig(configpath)
		logger = logging.getLogger(loggername)
		logger.setLevel(logging.DEBUG)
	except:
		syslog(LOG_ERR, "%s: Could not open logger because: %s: %s" %(str(loggername), str(sys.exc_info()[0]), str(sys.exc_info()[1])))
		logger = None

	return logger
### END get_logger()


##############################################################################
#
# led_on - Turn the desired LED on
#
##############################################################################
def led_on(ledpath=None):
	"""Arguments: 
			Path to the LED control structure (usually this is somewhere in /sys/class/leds/)
	   Return value:
			0 on success
			errno otherwise
	"""
	if (not ledpath) or (not os.path.isdir(ledpath)):
		return errno.EINVAL
	
	f = open("%s/trigger"%ledpath, 'w')
	f.write("none")
	f.close()
	f = open("%s/brightness"%ledpath, 'w')
	f.write("255")
	f.close()
	
	return 0
### END led_on()


##############################################################################
#
# led_off - Turn the desired LED off
#
##############################################################################
def led_off(ledpath=None):
	"""Arguments: 
			Path to the LED control structure (usually this is somwhere in /sys/class/leds/)
	   Return value:
			0 on success
			errno otherwise
	"""
	if (not ledpath) or (not os.path.isdir(ledpath)):
		return errno.EINVAL
	
	f = open("%s/trigger"%ledpath, 'w')
	f.write("none")
	f.close()
	f = open("%s/brightness"%ledpath, 'w')
	f.write("0")
	f.close()
	
	return 0
### END led_off()


##############################################################################
#
# led_blink - Let the desired LED blink
#
##############################################################################
def led_blink(ledpath=None, ondelay=0, offdelay=0):
	"""Arguments: 
			Path to the LED control structure (usually this is somwhere in /sys/class/leds/)
			Delay in ms before LED is turned on
			Delay in ms before LED is turned off
	   Return value:
			0 on success
			errno otherwise
	"""
	if (not ledpath) or (not os.path.isdir(ledpath)):
		return errno.EINVAL
	
	f = open("%s/trigger"%ledpath, 'w')
	f.write("timer")
	f.close()
	f = open("%s/delay_on"%ledpath, 'w')
	f.write(str(ondelay))
	f.close()
	f = open("%s/delay_off"%ledpath, 'w')
	f.write(str(offdelay))
	f.close()
	
	return 0
### END led_blink()


##############################################################################
#
# tg_pwr_get - get power state of a target slot
#
##############################################################################
def tg_pwr_get(slotnr):
	#TODO
	if slotnr not in (1,2,3,4):
		return errno.EINVAL

	tg_interface_set(slotnr)
	rs = 1

	return rs
### END tg_pwr_get()


##############################################################################
#
# tg_pwr_set - set power state of a target slot
#
##############################################################################
def tg_pwr_set(slotnr, value):
	#TODO
	return value
	if slotnr not in (1,2,3,4):
		return errno.EINVAL
	if value not in (0,1):
		return errno.EINVAL
	
	tg_interface_set(slotnr)
	
	return value
### END tg_pwr_get()

##############################################################################
#
# tg_pwr_get - get power state of a target slot
#
##############################################################################
def tg_usbpwr_get(slotnr):
	#TODO
	return 1
	if slotnr not in (1,2,3,4):
		return errno.EINVAL

	tg_interface_set(slotnr)
	rs = 1
	
	return rs
### END tg_pwr_get()


##############################################################################
#
# tg_pwr_set - set power state of a target slot
#
##############################################################################
def tg_usbpwr_set(slotnr, value):
	#TODO
	return value
	if slotnr not in (1,2,3,4):
		return errno.EINVAL
	if value not in (0,1):
		return errno.EINVAL
	
	tg_interface_set(slotnr)

	return value
### END tg_pwr_get()

##############################################################################
#
# tg_press_gpio - set a GPIO
#
##############################################################################
def tg_press_gpio(pin, value):
	try:
		cmd = ["simpleGPIO.py", "--pin=%s" % pin, "--direction=out", "--value=%d" % value]
		subprocess.call(cmd)
	except Exception:
		return errno.EFAULT
	return SUCCESS
### END tg_press_gpio()


##############################################################################
#
# tg_interface_get - get currently active slot interface
#
##############################################################################
def tg_interface_get():
	# Currently not connected to FlockBoard:
	return 1

	# Setup relevant GPIOS:
	subprocess.call("echo %s > %s/export" % (tg_interf_addr0, gpio_pins))
	subprocess.call("echo %s > %s/export" % (tg_interf_addr1, gpio_pins))
	subprocess.call("echo in > %s/gpio%s/direction" % (gpio_pins, tg_interf_addr0))
	subprocess.call("echo in > %s/gpio%s/direction" % (gpio_pins, tg_interf_addr1))
	# Read values of relevant GPIOS:
	addr0 = subprocess.Popen("cat %s/gpio%s/value" % (gpio_pins, tg_interf_addr0), stdout=subprocess.PIPE)
	addr1 = subprocess.Popen("cat %s/gpio%s/value" % (gpio_pins, tg_interf_addr1), stdout=subprocess.PIPE)
	if (addr0 == 0) and (addr1 == 0):
		rs = 1
	elif (addr0 == 1) and (addr1 == 0):
		rs = 2
	elif (addr0 == 0) and (addr1 == 1):
		rs = 3
	elif (addr0 == 1) and (addr1 == 1):
		rs = 4
	else:
		rs = None
	
	return rs
### END tg_interface_get()


##############################################################################
#
# tg_interface_set - set specific slot interface to be active
#
##############################################################################
def tg_interface_set(slotnr):
	# Currently not connected to FlockBoard:
	return SUCCESS
	if slotnr not in (None,1,2,3,4):
		return errno.EINVAL
	
	# Setup relevant GPIOS:
	subprocess.call("echo %s > %s/export" % (tg_interf_addr0, gpio_pins))
	subprocess.call("echo %s > %s/export" % (tg_interf_addr1, gpio_pins))
	subprocess.call("cd %s/gpio%s" % (gpio_pins, tg_interf_addr0))
	subprocess.call("echo out > %s/gpio%s/direction")
	subprocess.call("cd %s/gpio%s" % (gpio_pins, tg_interf_addr1))
	subprocess.call("echo out > %s/gpio%s/direction")
	if (slotnr == 1):
		subprocess.call("echo 0 > %s/gpio%s/value" % (gpio_pins, tg_interf_addr0))
		subprocess.call("echo 0 > %s/gpio%s/value" % (gpio_pins, tg_interf_addr1))
	elif (slotnr == 2):
		subprocess.call("echo 1 > %s/gpio%s/value" % (gpio_pins, tg_interf_addr0))
		subprocess.call("echo 0 > %s/gpio%s/value" % (gpio_pins, tg_interf_addr1))
	elif (slotnr == 3):
		subprocess.call("echo 0 > %s/gpio%s/value" % (gpio_pins, tg_interf_addr0))
		subprocess.call("echo 1 > %s/gpio%s/value" % (gpio_pins, tg_interf_addr1))
	elif (slotnr == 4):
		subprocess.call("echo 1 > %s/gpio%s/value" % (gpio_pins, tg_interf_addr0))
		subprocess.call("echo 1 > %s/gpio%s/value" % (gpio_pins, tg_interf_addr1))
	
	return SUCCESS
### END tg_interface_set()


##############################################################################
#
# tg_reset - Reset target on active interface
#
##############################################################################
def tg_reset(usleep):
	#rst = simpleGPIO.SimpleGPIO(tg_rst)
	if (usleep == None):
		usleep = 0.00010
	if ((type(usleep) not in (int, float)) or (usleep <= 0)):
		return errno.EINVAL
	
	time.sleep(usleep)
	tg_press_gpio(tg_rst, 0)
	#rst.write(0)
	time.sleep(usleep)
	tg_press_gpio(tg_rst, 1)
	#rst.write(1)
	time.sleep(usleep)
	
	return SUCCESS
### END tg_reset()


##############################################################################
#
# tg_reset - Pull reset pin for target on active interface without releasing it.
#
##############################################################################
def tg_reset_keep():
	#rst = simpleGPIO.SimpleGPIO(tg_rst)
	#rst.write(0)
	tg_press_gpio(tg_rst, 0)
	
	return SUCCESS
### END tg_reset_keep()


##############################################################################
#
# pin_abbr2num - Convert a pin abbreviation to its corresponding number
#
##############################################################################
def pin_abbr2num(abbr=""):
	if not abbr:
		return errno.EINVAL
	abbrdict =	{
					'RST' : "P8_9",
					'SIG1': "P8_45",
					'SIG2': "P8_46",
					'INT1': "P8_37",
					'INT2': "P8_38",
					'LED1': "P8_39",
					'LED2': "P8_40",
					'LED3': "P8_41"
				}
	try:
		pinnum = abbrdict[abbr.upper()]
	except KeyError:
		return errno.EFAULT
	
	return pinnum	
### END pin_abbr2num()

##############################################################################
#
# pin_num2abbr - Convert a pin abbreviation to its corresponding number
#
##############################################################################
def pin_num2abbr(pinnum=""):
	if not pinnum:
		return errno.EINVAL
	pindict =	{
					'P8_9' : "RST",
					'P8_45': "SIG1",
					'P8_45': "SIG2",
					'P8_37': "INT1",
					'P8_38': "INT2",
					'P8_39': "LED1",
					'P8_40': "LED2",
					'P8_41': "LED3"
				}
	try:
		abbr = pindict[pinnum.upper()]
	except KeyError:
		return errno.EFAULT
	
	return abbr	
### END pin_num2abbr()


##############################################################################
#
# level_str2abbr - Convert a pin level string to its abbreviation
#
##############################################################################
def level_str2abbr(levelstr=""):
	if not levelstr:
		return errno.EINVAL
	strdict =	{
					'LOW'   : 'L',
					'HIGH'  : 'H',
					'TOGGLE': 'T'
				}
	try:
		abbr = strdict[levelstr.upper()]
	except KeyError:
		return errno.EFAULT
	
	return abbr	
### END level_str2abbr()



##############################################################################
#
# edge_str2abbr - Convert a pin edge string to its abbreviation
#
##############################################################################
def edge_str2abbr(edgestr=""):
	if not edgestr:
		return errno.EINVAL
	strdict =	{
					'RISING' : 'R',
					'FALLING': 'F',
					'BOTH'   : 'B'
				}
	try:
		abbr = strdict[edgestr.upper()]
	except KeyError:
		return errno.EFAULT
	
	return abbr	
### END edge_str2abbr()


##############################################################################
#
# gpiomon_mode_str2abbr - Convert a GPIO monitoring mode string to its abbreviation
#
##############################################################################
def gpiomon_mode_str2abbr(modestr=""):
	if not modestr:
		return errno.EINVAL
	strdict =	{
					'CONTINUOUS' : 'C',
					'SINGLE'     : 'S'
				}
	try:
		abbr = strdict[modestr.upper()]
	except KeyError:
		return errno.EFAULT
	
	return abbr	
### END gpiomon_mode_str2abbr()


##############################################################################
#
# tg_volt_get - get currently set voltage on the active interface
#
##############################################################################
def tg_volt_get():
	#TODO: without FlockBoard not possible to connect
	return 3.3
	try:
		f = open(LM3370PATH, 'r')
		read_v = f.read(2)
		f.close()
	except (IOError) as e:
		return -1
		
	return int(read_v)
### END tg_volt_get()


##############################################################################
#
# tg_volt_set - set voltage on the active interface
#
##############################################################################
def tg_volt_set(newvoltage, forcepwm = None):
	#TODO: without FlockBoard not possible to connect
	return SUCCESS
	try:
		f = open(LM3370PATH, 'w')
		if forcepwm is not None:
			if forcepwm:
				f.write('force')
			else:
				f.write('auto')
			f.flush()
		f.write('%d'%newvoltage)
		f.close()
	except (IOError) as e:
		return -1
	
	return SUCCESS
### END tg_volt_set()


##############################################################################
#
# is_sdcard_mounted - check if the SD card is mounted
#
##############################################################################
def is_sdcard_mounted():
	# OS on SD card, so it's allways mounted.
	return True

	try:
		cmd = ["mountpoint", "-q", "/media/card"]
		p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
		p.communicate(None)
		if (p.returncode == 0):
			return True
		else:
			return False
	except:
		return False
### END is_sdcard_mounted()


##############################################################################
#
# timeformat_xml2service -	Convert between different timeformats of 
#							XML config file and FlockLab services
#
##############################################################################
def timeformat_xml2service(config=None, timestring=""):
	if (not config) or (not timestring):
		return errno.EINVAL
	try:
		# First convert time from xml-string to time format:
		xmltime = time.strptime(timestring, config.get("xml", "timeformat_xml"))
		# Now convert to service time-string:
		servicetimestring = time.strftime(config.get("observer", "timeformat_services"), xmltime)
	except:
		return errno.EFAULT
	
	return servicetimestring	
### END timeformat_xml2service()

##############################################################################
#
# timeformat_xml2timestamp -	Convert between different timeformats of 
#							XML config file and FlockLab services
#
##############################################################################
def timeformat_xml2timestamp(config=None, timestring=""):
	if (not config) or (not timestring):
		return errno.EINVAL
	try:
		# First convert time from xml-string to time format:
		#xmltime = time.strptime(timestring, config.get("xml", "timeformat_xml"))
		xmltime = time.strptime(timestring, "%Y-%m-%dT%H:%M:%S")
	except:
		return errno.EFAULT
	
	return time.mktime(xmltime)
### END timeformat_xml2service()

##############################################################################
#
# start_services -	
#
##############################################################################
def start_services(services, logger, debug):
	errors = []
	for key in services.keys():
		# Start service:
		cmd = [key, '-start']
		if not debug:
			cmd.append('--quiet')
		p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
		(out, err) = p.communicate()
		if (p.returncode not in (SUCCESS, errno.EEXIST)):
			msg = "Error %d when trying to start %s service: %s"%(p.returncode, services[key][3], str(err))
			errors.append(msg)
			if debug:
				logger.error(msg)
				logger.error("Tried to start with: %s"%(str(cmd)))
		else:
			if debug:
				if p.returncode == SUCCESS:
					logger.debug("Started %s service."%(services[key][3]))
				elif p.returncode == errno.EEXIST:
					logger.debug("%s service was already running."%(services[key][3]))
	return errors

##############################################################################
#
# start_pwr_measurement -	
#
##############################################################################
def start_pwr_measurement():
	file = open("/home/debian/flocklab/pwr_measurement.txt","w")
	file.write("start")
	file.close()
	syslog(LOG_INFO, "Started power measurement.")

##############################################################################
#
# stop_pwr_measurement -	
#
##############################################################################
def stop_pwr_measurement():
	file = open("/home/debian/flocklab/pwr_measurement.txt","w")
	file.write("stop")
	file.close()
	syslog(LOG_INFO, "Stopped power measurement.")

##############################################################################
#
# start_gpio_tracing -	
#
##############################################################################
def start_gpio_tracing(xml, log_file_dir):
	my_time = time.strftime("%Y%m%d%H%M%S", time.gmtime())
	log_file = "%sgpio_monitor_%s.db" % (log_file_dir, my_time)
	cmd = "flocklab_gpio_tracing.py --xml=%s --file=%s" % (xml, log_file)
	p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
	p.wait()
	syslog(LOG_INFO, "Started gpio tracing.")

##############################################################################
#
# stop_gpio_tracing -	
#
##############################################################################
def stop_gpio_tracing():
	proc = subprocess.Popen(['pgrep', '-f', '/usr/bin/flocklab_gpio_tracing'], stdout=subprocess.PIPE)
	pid, err = proc.communicate()
	print("PID %s" % pid)
	print("ERR %s" % err)
	if pid:
		print(pid)
		os.kill(int(pid), signal.SIGKILL)
	syslog(LOG_INFO, "Stopped gpio tracing.")

##############################################################################
#
# collect_pwr_measurement_data -	
#
##############################################################################
def collect_pwr_measurement_data(test_id):
	data_file_path = "/home/debian/flocklab/pwr/"

	read_files = glob.glob("%s*.rld" % data_file_path)
	while len(read_files) == 0:
		read_files = glob.glob("%s*.rld" % data_file_path)
	
	for f in read_files:
		size = os.stat(str(f)).st_size
		while size == 0:
			size = os.stat(str(f)).st_size

	my_time = time.strftime("%Y%m%d%H%M%S", time.gmtime())
	
	output_file = "%spowerprofiling_%s.db" % (data_file_path, my_time)
	with open(output_file, "a+") as outfile:
		for f in read_files:
			with open(f) as infile:
				for line in infile:
					outfile.write(line)
			os.remove(str(f))

	try:
		data_files = [f for f in listdir(data_file_path) if isfile(join(data_file_path, f))]
		for df in data_files:
			src = "%s%s" % (data_file_path, df)
			dst = "/home/debian/flocklab/db/%d/%s" %(int(test_id), df)
			shutil.move(src, dst)
	except (Exception) as e:
		syslog(LOG_INFO, traceback.format_exc())

##############################################################################
#
# stop_services -	
#
##############################################################################
def stop_services(services, logger, testid, debug):
	errors = []
	# Remove all pending jobs:
	for key in services.iterkeys():
		cmd = [key, '-removeall']
		if not debug:
			cmd.append('--quiet')
		p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
		(out, err) = p.communicate()
		rs = p.returncode
		if (rs not in (SUCCESS, errno.ENOPKG)):
			msg = "Error %d when trying to run command '-removeall' for %s service."%(rs, services[key][1])
			errors.append(msg)
			logger.error(msg)
			if debug:
				logger.error("Tried to run command '-removeall' for %s service with: %s"%(services[key][1], str(cmd)))
		else:
			if debug:
				logger.debug("Successfully ran command '-removeall' for %s service."%(services[key][1]))
	# Flush all output fifo's:
	for key in services.keys():
		cmd = [key, '-flush']
		if not debug:
			cmd.append('--quiet')
		p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
		(out, err) = p.communicate()
		rs = p.returncode
		if (rs not in (SUCCESS, errno.ENOPKG)):
			msg = "Error %d when trying to run command '-flush' for %s service."%(rs, services[key][1])
			errors.append(msg)
			logger.error(msg)
			if debug:
				logger.error("Tried to run command '-flush' for %s service with: %s"%(services[key][1], str(cmd)))
		else:
			if debug:
				logger.debug("Successfully ran command '-flush' for %s service."%(services[key][1]))
	# Stop database daemons:
	for key in services.keys():
		cmd = ['flocklab_dbd', '-stop', '--testid=%d' % testid, '--service=%s'%(services[key][0])]
		p = subprocess.Popen(cmd, stdout=open('/dev/null', 'w'), stderr=subprocess.STDOUT)
		(out, err) = p.communicate()
		rs = p.returncode
		if (rs not in (SUCCESS,)):
			msg = "Error %d when trying to stop database daemon for %s service."%(rs, services[key][1])
			errors.append(msg)
			logger.error(msg)
			if debug:
				logger.error("Tried to start with: %s"%(str(cmd)))
		else:
			if debug:
				if rs == SUCCESS:
					logger.debug("Stopped database daemon for %s service."%(services[key][1]))
	return errors

### END stop_services()

class nologger():

	def error(self, msg):
		pass
	
	def debug(self, msg):
		pass
		
	def info(self, msg):
		pass
