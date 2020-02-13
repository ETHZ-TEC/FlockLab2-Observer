#!/usr/bin/env python3

##############################################################################
# FlockLab library, runs on the observer
##############################################################################

# needed imports:
import sys, os, errno, signal, time, configparser, logging, logging.config, subprocess, traceback, glob, shutil, smbus

# pin numbers
gpio_tg_nrst    = 77
gpio_tg_prog    = 81
gpio_tg_sig1    = 75
gpio_tg_sig2    = 76
gpio_tg_sel0    = 47
gpio_tg_sel1    = 27
gpio_tg_nen     = 46
gpio_tg_pwr_en  = 26
gpio_tg_act_nen = 65
gpio_tg_mux_nen = 22
gpio_led_status = 69
gpio_led_error  = 45
gpio_jlink_nrst = 44
gpio_usb_nrst   = 68
gpio_gnss_nrst  = 67

# list of all output GPIOs and their default state
out_pin_list    = [gpio_tg_nrst,
                   gpio_tg_prog,
                   gpio_tg_sig1,
                   gpio_tg_sig2,
                   gpio_tg_sel0,
                   gpio_tg_sel1,
                   gpio_tg_nen,
                   gpio_tg_pwr_en,
                   gpio_tg_act_nen,
                   gpio_tg_mux_nen,
                   gpio_led_status,
                   gpio_led_error,
                   gpio_jlink_nrst,
                   gpio_usb_nrst,
                   gpio_gnss_nrst]
out_pin_states  = [1,             # don't keep target in reset state
                   0,             # PROG pin low
                   0,             # SIG pins low
                   0,             # -
                   1,             # select target 1
                   1,             # -
                   1,             # disable target
                   0,             # power off
                   1,             # disable actuation
                   0,             # enable MUX
                   0,             # LED off
                   0,             # LED off
                   1,             # enable JLink debugger
                   1,             # turn on USB hub (required for SWD and target USB)
                   1 ]            # turn on GNSS receiver (required for time sync)

# allowed values
tg_vcc_min      = 1.1
tg_vcc_max      = 3.6
tg_vcc_default  = 3.3             # e.g. used for target programming
tg_platforms    = ['dpp', 'tmote', 'dpp2lora', 'nrf5']
tg_port_types   = ['usb', 'serial']
tg_serial_port  = '/dev/ttyS5'
tg_baud_rates   = [9600, 19200, 38400, 57600, 115200]
rl_max_rate     = 64000
rl_default_rate = 1000
rl_samp_rates   = [1, 10, 100, 1000, 2000, 4000, 8000, 16000, 32000, 64000]
rl_max_samples  = 100000000

# paths
configfile = '/home/flocklab/observer/testmanagement/config.ini'
loggerconf = '/home/flocklab/observer/testmanagement/logging.conf'
scriptname = os.path.basename(os.path.abspath(sys.argv[0]))   # name of caller script

# constants
SUCCESS = 0
FAILED  = -2       # note: must be negative, and -1 (= 255) is reserved for SSH error

# global variables
logger = None
config = None


##############################################################################
#
# log_fallback - a way to log errors if the regular log file is unavailable
#
##############################################################################
def log_fallback(msg):
    #syslog.syslog(syslog.LOG_ERR, msg)    # -> requires 'import syslog'
    #print(msg, file=sys.stderr)
    print(msg)
### END log_fallback()


##############################################################################
#
# get_config - read config.ini and return it to caller.
#
##############################################################################
def get_config():
    global config
    # if config already exists, return it
    if config:
        return config
    try:
        config = configparser.SafeConfigParser()
        config.read(configfile)
    except:
        logger = get_logger()
        logger.error("Failed to load config file '%s'." % configfile)
    return config
### END get_config()


##############################################################################
#
# get_logger - Open a logger for the caller.
#
##############################################################################
def get_logger(loggername=scriptname, debug=False):
    global logger
    # if it already exists, return logger
    if logger:
        return logger
    try:
        logging.config.fileConfig(loggerconf)
        logger = logging.getLogger(loggername)
        if debug:
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.INFO)
    except:
        log_fallback("[FlockLab %s] Could not open logger because: %s, %s" % (str(loggername), str(sys.exc_info()[0]), str(sys.exc_info()[1])))
        logger = None
    return logger
### END get_logger()


##############################################################################
#
# logging helpers
#
##############################################################################
def log_info(msg=""):
    global logger
    logger.info(msg)
### END log_info()

def log_error(msg=""):
    global logger
    logger.error(msg)
### END log_error()

def log_warning(msg=""):
    global logger
    logger.warn(msg)
### END log_warning()

def log_debug(msg=""):
    global logger
    logger.debug(msg)
### END log_debug()


##############################################################################
#
# error_logandexit - log error message and terminate process
#
##############################################################################
def error_logandexit(msg=None, err=FAILED):
    # clear status LED, turn on error LED
    gpio_clr(gpio_led_status)
    gpio_set(gpio_led_error)
    logger = get_logger()
    if logger:
        logger.error(msg)
        logger.debug("Exiting with error code %u." % err)
    else:
        log_fallback(msg)
        log_fallback("Exiting with error code %u." % err)
    #print(msg, file=sys.stderr)
    sys.exit(err)
### END error_logandexit()


##############################################################################
#
# log_test_error - write error message to log appended to test results
#
##############################################################################
def log_test_error(testid=None, msg=None):
    if testid and msg:
        resfolder = "%s/%d" % (config.get("observer", "testresultfolder"), testid)
        errorlogfile = "%s/%d/error_%s.log" % (config.get("observer", "testresultfolder"), testid, time.strftime("%Y%m%d%H%M%S", time.gmtime()))
        with open(errorlogfile, 'a') as f:
            f.write("%s,%s\n" % (str(time.time()), msg))
        log_debug("Error message logged to file '%s'" % errorlogfile)
### END log_test_error()


##############################################################################
#
# init_gpio - initialize all used GPIOs (output pins) to their default value
#
##############################################################################
def init_gpio():
    try:
        for pin, state in zip(out_pin_list, out_pin_states):
            os.system("echo out > /sys/class/gpio/gpio%d/direction" % (pin))
            os.system("echo %d > /sys/class/gpio/gpio%d/value" % (state, pin))
    except IOError:
        print("Failed to configure GPIO.")
        return
### END init_gpio()


##############################################################################
#
# gpio_set - set an output pin high
#
##############################################################################
def gpio_set(pin):
    try:
        os.system("echo 1 > /sys/class/gpio/gpio%s/value" % (pin))
    except IOError:
        print("Failed to set GPIO state.")
        return FAILED
    return SUCCESS
### END gpio_set()


##############################################################################
#
# gpio_clr - set an output pin low
#
##############################################################################
def gpio_clr(pin):
    try:
        os.system("echo 0 > /sys/class/gpio/gpio%s/value" % (pin))
    except IOError:
        print("Failed to set GPIO state.")
        return FAILED
    return SUCCESS
### END gpio_clr()


##############################################################################
#
# gpio_get - poll the current pin state
#
##############################################################################
def gpio_get(pin):
    try:
        p = subprocess.Popen(["cat", "/sys/class/gpio/gpio%s/value" % (pin)], stdout=subprocess.PIPE, universal_newlines=True)
        out = p.communicate()[0]
    except IOError:
        print("Failed to get GPIO state.")
        return FAILED
    return int(out)
### END gpio_get()


##############################################################################
#
# set_pin - set a pin to high or low
#
##############################################################################
def set_pin(pin, level):
    if level:
      return gpio_set(pin)
    else:
      return gpio_clr(pin)
### END set_pin()


##############################################################################
#
# tg_pwr_get - get power state of a target slot
#
##############################################################################
def tg_pwr_state():
    return gpio_get(gpio_tg_pwr_en)
### END tg_pwr_get()


##############################################################################
#
# tg_pwr_set - set power state
#
##############################################################################
def tg_pwr_en(enable=True):
    if enable:
        gpio_set(gpio_tg_pwr_en)
    else:
        gpio_clr(gpio_tg_pwr_en)
    return SUCCESS
### END tg_pwr_en()


##############################################################################
#
# tg_en - enable target
#
##############################################################################
def tg_en(enable=True):
    if enable:
        gpio_clr(gpio_tg_nen)
    else:
        gpio_set(gpio_tg_nen)
    return SUCCESS
### END tg_en()


##############################################################################
#
# tg_en_state - get the enabled state (returns True if enabled, False otherwise)
#
##############################################################################
def tg_en_state():
    return (gpio_get(gpio_tg_nen) == 0)
### END tg_en_state()


##############################################################################
#
# tg_mux_en - enable multiplexer (activates SWD, serial ID and USB for target)
#
##############################################################################
def tg_mux_en(enable=True):
    if enable:
        gpio_clr(gpio_tg_mux_nen)
    else:
        gpio_set(gpio_tg_mux_nen)
    return SUCCESS
### END tg_mux_en()


##############################################################################
#
# tg_act_en - enable target actuation
#
##############################################################################
def tg_act_en(enable=True):
    if enable:
        gpio_clr(gpio_tg_act_nen)
    else:
        gpio_set(gpio_tg_act_nen)
    return SUCCESS
### END tg_mux_en()


##############################################################################
#
# tg_get_selected - get currently active slot interface
#
##############################################################################
def tg_get_selected():
    try:
        # Read values of relevant GPIOS:
        addr0 = gpio_get(gpio_tg_sel0)
        addr1 = gpio_get(gpio_tg_sel1)
    except:
        return None
    return (4 - (addr1 * 2 + addr0))
### END tg_get_selected()


##############################################################################
#
# tg_select - set specific slot interface to be active
#
##############################################################################
def tg_select(slotnr):
    if slotnr not in (1,2,3,4):
        return errno.EINVAL
    
    # target selection:
    # 1: sel0 = 1, sel1 = 1
    # 2: sel0 = 0, sel1 = 1
    # 3: sel0 = 1, sel1 = 0
    # 4: sel0 = 0, sel1 = 0
    
    if (slotnr == 1):
        gpio_set(gpio_tg_sel0)
        gpio_set(gpio_tg_sel1)
    elif (slotnr == 2):
        gpio_clr(gpio_tg_sel0)
        gpio_set(gpio_tg_sel1)
    elif (slotnr == 3):
        gpio_set(gpio_tg_sel0)
        gpio_clr(gpio_tg_sel1)
    elif (slotnr == 4):
        gpio_clr(gpio_tg_sel0)
        gpio_clr(gpio_tg_sel1)
    
    return SUCCESS
### END tg_select()


##############################################################################
#
# tg_reset - Reset target on active interface
#
##############################################################################
def tg_reset(release=True):
    gpio_clr(gpio_tg_prog)    # ensure prog pin is low
    gpio_clr(gpio_tg_nrst)
    if release:
        time.sleep(0.1)
        gpio_set(gpio_tg_nrst)
    return SUCCESS
### END tg_reset()


##############################################################################
#
# pin_abbr2num - Convert a pin abbreviation to its corresponding PRU pin number
#
##############################################################################
def pin_abbr2num(abbr=""):
    if not abbr:
        return 0x0
    abbrdict =    {
                    'LED1': 0x01,
                    'LED2': 0x02,
                    'LED3': 0x04,
                    'INT1': 0x08,
                    'INT2': 0x10,
                    'SIG1': 0x20,
                    'SIG2': 0x40,
                    'RST' : 0x80
                }
    try:
        pinnum = abbrdict[abbr.upper()]
    except KeyError:
        return 0x0
    return pinnum
### END pin_abbr2num()


##############################################################################
#
# level_str2abbr - Convert a pin level string to its abbreviation
#
##############################################################################
def level_str2abbr(levelstr=""):
    if not levelstr:
        return errno.EINVAL
    strdict =    {
                    'LOW'   : 'L',
                    'HIGH'  : 'H',
                    'TOGGLE': 'T'
                }
    try:
        abbr = strdict[levelstr.upper()]
    except KeyError:
        return ""
    
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
    strdict =    {
                    'RISING' : 'R',
                    'FALLING': 'F',
                    'BOTH'   : 'B'
                }
    try:
        abbr = strdict[edgestr.upper()]
    except KeyError:
        return ""
    
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
    strdict =    {
                    'CONTINUOUS' : 'C',
                    'SINGLE'     : 'S'
                }
    try:
        abbr = strdict[modestr.upper()]
    except KeyError:
        return ""
    
    return abbr
### END gpiomon_mode_str2abbr()


##############################################################################
#
# tg_set_vcc - set voltage on the active interface
#
##############################################################################
def tg_set_vcc(v=tg_vcc_default):
    if v is None or v < 1.1 or v > 3.6:
        return FAILED
      
    bus = smbus.SMBus(2)  # I2C2
    
    DEVICE_ADDR = 0x60
    DEVICE_REG  = 0x0
    VREF        = 800     # mV
    VDD         = 3375    # mV
    R11         = 12      # kOhm
    R12         = 11.5    # kOhm
    R13         = 4.7     # kOhm
    
    R11R12      = R11 / R12
    R11R13      = (R11 + R13) / R13
    
    v_dac  = VREF - (R11R12 * (v * 1000 - VREF * R11R13))
    cfgval = int(v_dac * 255 / VDD)
    try:
        bus.write_word_data(DEVICE_ADDR, DEVICE_REG, (cfgval * 256) & 0xffff)
    except (IOError) as e:
        return FAILED
    
    return SUCCESS
### END tg_set_vcc()


##############################################################################
#
# is_sdcard_mounted - check if the SD card is mounted
#
##############################################################################
def is_sdcard_mounted():
    try:
        p = subprocess.Popen(["mount"], stdout=subprocess.PIPE, universal_newlines=True)
        out, err = p.communicate()
        if "/dev/mmcblk1p1" in out:
            return True
        else:
            return False
    except:
        return False
### END is_sdcard_mounted()


##############################################################################
#
# timeformat_xml2service -   Convert between different timeformats of 
#                            XML config file and FlockLab services
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
        return ""
    
    return servicetimestring
### END timeformat_xml2service()


##############################################################################
#
# timeformat_xml2timestamp - Convert between different timeformats of 
#                            XML config file and FlockLab services
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
        return ""
    
    return time.mktime(xmltime)
### END timeformat_xml2service()


##############################################################################
#
# start_pwr_measurement
#
##############################################################################
def start_pwr_measurement(out_file=None, sampling_rate=rl_default_rate, num_samples=0, start_time=0):
    if sampling_rate not in rl_samp_rates:
        return errno.EINVAL
    if not out_file:
        out_file = "%s/powerprofiling_%s.rld" % (config.get("observer", "testresultfolder"), time.strftime("%Y%m%d%H%M%S", time.gmtime()))
    cmd = ["rocketlogger", "start", "-b", "--channel=V1,V2,I1L,I1H", "--output=%s" % out_file, "--rate=%d" % int(sampling_rate)]
    if num_samples:
        if num_samples > rl_max_samples:
            num_samples = rl_max_samples
        cmd.append(("--samples=%s" % str(num_samples)))
    if start_time > 0:
        cmd.append(("--tstart=%s" % str(start_time)))
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    rs = p.wait()
    if rs != 0:
        logger = get_logger()
        logger.warn("Tried to start power measurement with command '%s'" % cmd)
        return FAILED
    return SUCCESS
### END start_pwr_measurement()


##############################################################################
#
# stop_pwr_measurement
#
##############################################################################
def stop_pwr_measurement():
    cmd = ["rocketlogger", "stop"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    return SUCCESS
### END stop_pwr_measurement()


##############################################################################
#
# start_gpio_tracing
#
##############################################################################
def start_gpio_tracing(out_file=None, start_time=0, stop_time=0, pins=0x0):
    if not out_file:
        out_file = "%s/gpiotracing_%s.dat" % (config.get("observer", "testresultfolder"), time.strftime("%Y%m%d%H%M%S", time.gmtime()))
    cmd = ["fl_logic", out_file]
    if start_time > 0:
        cmd.append("%d" % start_time)
        # test start time must be given in order to specify a stop time
        if stop_time > 0:
            cmd.append("%d" % stop_time)
            if pins != 0x0:
                cmd.append("0x%x" % pins)
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    # do not call communicate(), it will block
    return SUCCESS
### END start_gpio_tracing()


##############################################################################
#
# stop_gpio_tracing
#
##############################################################################
def stop_gpio_tracing():
    p = subprocess.Popen(['pgrep', '-f', 'fl_logic'], stdout=subprocess.PIPE)
    pid, err = p.communicate()
    try:
        if p.returncode != 0:
            return SUCCESS      # process does probably not exist
        if pid:
            os.kill(int(pid), signal.SIGTERM)
            logger.debug("Waiting for gpio tracing service to stop...")
            timeout = 30
            rs = 0
            while rs == 0 and timeout:
                time.sleep(1)
                timeout = timeout - 1
                p = subprocess.Popen(['pgrep', '-f', 'fl_logic'], stdout=subprocess.PIPE)
                rs = p.wait()
            if rs != 0:         # process does not exist anymore
                return SUCCESS
    except:
        pass
    return FAILED
### END stop_gpio_tracing()
