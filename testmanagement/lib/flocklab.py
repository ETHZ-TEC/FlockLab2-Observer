#!/usr/bin/env python3

##############################################################################
# FlockLab library, runs on the observer
##############################################################################

# Needed imports:
import sys, os, errno, signal, time, configparser, logging, logging.config, subprocess, traceback, glob, shutil, smbus

### Global variables ###
gpio_tg_nrst    = 77
gpio_tg_prog    = 81
gpio_tg_sig1    = 75
gpio_tg_sig2    = 76
gpio_tg_sel0    = 47
gpio_tg_sel1    = 27
gpio_tg_nen     = 46
gpio_tg_pwr_en  = 26
gpio_jlink_nrst = 44
gpio_tg_act_nen = 65
gpio_led_status = 69
gpio_led_error  = 45

tg_vcc_min      = 1.1
tg_vcc_max      = 3.6
tg_platforms    = ['dpp', 'tmote', 'dpp2lora', 'nrf5']
tg_port_types   = ['usb', 'serial']
tg_serial_port  = '/dev/ttyS5'
tg_baud_rates   = [9600, 19200, 38400, 57600, 115200]
rl_max_rate     = 64000
rl_default_rate = 1000
rl_samp_rates   = [1, 10, 100, 1000, 2000, 4000, 8000, 16000, 32000, 64000]
rl_max_samples  = 100000000


configfile = '/home/flocklab/observer/testmanagement/config.ini'
loggerconf = '/home/flocklab/observer/testmanagement/logging.conf'
scriptname = os.path.basename(os.path.abspath(sys.argv[0]))   # name of caller script

SUCCESS = 0
FAILED  = -1

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
# gpio_set - set an output pin high
#
##############################################################################
def gpio_set(pin):
    try:
        os.system("echo 1 > /sys/class/gpio/gpio%s/value" % (pin))
    except IOError:
        print("Failed to set GPIO state.")
        return -1
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
        return -1
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
        return -1
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
# tg_pwr_set - set power state of a target slot
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
# tg_pwr_set - set power state of a target slot
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
# pin_abbr2num - Convert a pin abbreviation to its corresponding number
#
##############################################################################
def pin_abbr2num(abbr=""):
    if not abbr:
        return errno.EINVAL
    abbrdict =    {
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
    pindict =    {
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
    strdict =    {
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
    strdict =    {
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
    strdict =    {
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
# tg_set_vcc - set voltage on the active interface
#
##############################################################################
def tg_set_vcc(v=3.3):
    if v is None or v < 1.1 or v > 3.6:
        return -1
      
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
        return -1
    
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
        return errno.EFAULT
    
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
        return errno.EFAULT
    
    return time.mktime(xmltime)
### END timeformat_xml2service()


##############################################################################
#
# start_pwr_measurement
#
##############################################################################
def start_pwr_measurement(log_file_dir, sampling_rate=rl_default_rate, num_samples=rl_max_samples):
    if sampling_rate not in rl_samp_rates:
        syslog.syslog(syslog.LOG_ERROR, "Invalid sampling rate for power measurement.")
        return errno.EINVAL
    my_time = time.strftime("%Y%m%d%H%M%S", time.gmtime())
    log_file = "%s/power_%s.rld" % (log_file_dir, my_time)
    cmd = "rocketlogger start -o %s --rate=%s" % (log_file, str(sampling_rate))
    if num_samples:
        if num_samples > rl_max_samples:
            num_samples = rl_max_samples
        cmd.append('--samples=' + str(num_samples))
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    p.wait()
    return SUCCESS
### END start_pwr_measurement()


##############################################################################
#
# stop_pwr_measurement
#
##############################################################################
def stop_pwr_measurement():
    cmd = "rocketlogger stop"
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    p.wait()
### END stop_pwr_measurement()


##############################################################################
#
# start_gpio_tracing
#
##############################################################################
def start_gpio_tracing(out_file=None, xml=None):
    if not out_file:
        my_time = time.strftime("%Y%m%d%H%M%S", time.gmtime())
        out_file = "%s/gpiotracing_%s.dat" % (config.get("observer", "testresultfolder"), my_time)
    # for now, ignore the XML config -> trace all pins by default
    cmd = "fl_logic %s &" % (out_file)
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    p.wait()
### END start_gpio_tracing()


##############################################################################
#
# stop_gpio_tracing
#
##############################################################################
def stop_gpio_tracing():
    proc = subprocess.Popen(['pgrep', '-f', 'fl_logic'], stdout=subprocess.PIPE)
    pid, err = proc.communicate()
    if pid:
        os.kill(int(pid), signal.SIGTERM)
### END stop_gpio_tracing()


##############################################################################
#
# collect_pwr_measurement_data
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
        data_files = [f for f in os.listdir(data_file_path) if os.path.isfile(os.path.join(data_file_path, f))]
        for df in data_files:
            src = "%s%s" % (data_file_path, df)
            dst = "/home/debian/flocklab/db/%d/%s" %(int(test_id), df)
            shutil.move(src, dst)
    except (Exception) as e:
        syslog.syslog(syslog.LOG_INFO, traceback.format_exc())
### END collect_pwr_measurement_data()
