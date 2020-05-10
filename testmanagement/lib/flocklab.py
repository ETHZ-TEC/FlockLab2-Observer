#!/usr/bin/env python3

##############################################################################
# FlockLab library, runs on the observer
##############################################################################

# needed imports:
import sys, os, errno, signal, time, configparser, logging, logging.config, subprocess, traceback, glob, shutil, smbus, re

# pin numbers
gpio_tg_nrst    = 77
gpio_tg_prog    = 81
gpio_tg_sig1    = 89
gpio_tg_sig2    = 88
gpio_tg_sig1_old= 75  # TODO remove
gpio_tg_sig2_old= 76  # TODO remove
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
tg_usb_port     = '/dev/ttyUSB0'
tg_baud_rates   = [9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600, 1000000, 2000000, 3000000]
rl_max_rate     = 64000
rl_default_rate = 1000
rl_samp_rates   = [1, 10, 100, 1000, 2000, 4000, 8000, 16000, 32000, 64000]
rl_max_samples  = 100000000
rl_time_offset  = -0.0037          # rocketlogger is about ~3.7ms behind the actual time

# paths
configfile   = '/home/flocklab/observer/testmanagement/config.ini'
loggerconf   = '/home/flocklab/observer/testmanagement/logging.conf'
actuationdev = '/dev/flocklab_act'
gmtimerstats = '/sys/devices/platform/ocp/ocp:pps_gmtimer/stats'
tracinglog   = '/home/flocklab/log/fl_logic.log'
rllog        = '/home/flocklab/log/rocketlogger.log'
gdblog       = '/home/flocklab/log/jlinkgdb.log'
scriptname   = os.path.basename(os.path.abspath(sys.argv[0]))   # name of caller script

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
        errorlogfile = "%s/%d/error_%s.log" % (config.get("observer", "testresultfolder"), testid, time.strftime("%Y%m%d%H%M%S", time.gmtime()))
        with open(errorlogfile, 'a') as f:
            f.write("%s,%s\n" % (str(time.time()), msg))
        log_debug("Error message logged to file '%s'" % errorlogfile)
### END log_test_error()


##############################################################################
#
# log_timesync_info
#
##############################################################################
def log_timesync_info(testid=None, includepps=False):
    if testid and os.path.isdir("%s/%d" % (config.get("observer", "testresultfolder"), testid)):
        timesynclogfile = "%s/%d/timesync_%s.log" % (config.get("observer", "testresultfolder"), testid, time.strftime("%Y%m%d%H%M%S", time.gmtime()))
        p = subprocess.Popen(['chronyc', 'sources'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        out, err = p.communicate(None)
        if (p.returncode == 0):
            lines = out.split('\n')
            for line in lines:
                res = re.match("^[#^]{1}\*\s+([a-zA-Z0-9.-_]+)[0-9\s]+([+-]{1}[0-9a-z]+)\[\s*([+-]{1}[0-9a-z]+)\]\s+(\+/\-[0-9a-z\s]*)$", line)
                if res:
                    with open(timesynclogfile, "a") as tslog:
                        tslog.write("%s,time source: %s | adjusted offset: %s | measured offset: %s | estimated error: %s\n" % (str(time.time()), res.group(1), res.group(2), res.group(3), res.group(4)))
                    break;
        else:
            log_test_error(testid=testid, msg="Failed to query time source.")
        
        if includepps:
            with open(timesynclogfile, "a") as tslog:
                tslog.write("%s,GNSS PPS reception: %.2f%%\n" % (str(time.time()), get_pps_delta(testid)))
### END log_timesync_info()


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
# usb_reset - reset USB hub
#
##############################################################################
def usb_reset():
    if gpio_clr(gpio_usb_nrst) != SUCCESS or gpio_set(gpio_usb_nrst) != SUCCESS:
        return FAILED
    time.sleep(1)     # give some time for initialization
    return SUCCESS
### END usb_reset()


##############################################################################
#
# gpio_set - set an output pin high
#
##############################################################################
def gpio_set(pin):
    try:
        #os.system("echo 1 > /sys/class/gpio/gpio%s/value" % (pin))
        f = open("/sys/class/gpio/gpio%s/value" % (pin), 'w')
        f.write('1')
        f.close()
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
        #os.system("echo 0 > /sys/class/gpio/gpio%s/value" % (pin))
        f = open("/sys/class/gpio/gpio%s/value" % (pin), 'w')
        f.write('0')
        f.close()
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
        #p = subprocess.Popen(["cat", "/sys/class/gpio/gpio%s/value" % (pin)], stdout=subprocess.PIPE, universal_newlines=True)
        #out = p.communicate()[0]
        f = open("/sys/class/gpio/gpio%s/value" % (pin), 'r')
        out = f.read()
        f.close()
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
# tg_en - enable target (note: this also enables 3.3V and 5V supply!)
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
# tg_off - turns off all power rails and cuts all lines to the selected target
#
##############################################################################
def tg_off():
    tg_pwr_en(False)
    tg_en(False)
    tg_act_en(False)
    tg_mux_en(False)
### END tg_off()


##############################################################################
#
# tg_on - turns on all power rails and connects all lines to the selected target
#
##############################################################################
def tg_on():
    tg_mux_en(True)
    tg_act_en(True)
    tg_en(True)
    tg_pwr_en(True)
### END tg_on()


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
        time.sleep(0.001)
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
    abbrdict = {
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
def level_str2abbr(levelstr="", pin="SIG1"):
    if not levelstr:
        return FAILED
    strdict = {
                'LOW'   : 'L',
                'HIGH'  : 'H',
                'TOGGLE': 'T',    # toggle is only supported for SIG1 and SIG2
              }
    try:
        abbr = strdict[levelstr.upper()]
    except KeyError:
        return ""
    pin = pin.upper()
    if pin == "SIG2":
        abbr = abbr.lower()
    elif pin == "RST":
        if abbr == 'H':
            abbr = 'R'
        else:
            abbr = 'r'
    elif pin == "PPS":
        if abbr == 'H':
            abbr = 'P'
        else:
            abbr = 'p'
    return abbr
### END level_str2abbr()


##############################################################################
#
# generate_periodic_act_events - generates an array with periodic actuation
#                                events, starting with the rising edge
#
# offset is in seconds from the test start (float)
# period is in seconds (float)
# duty cycle is the fraction of the period where the signal is high (float)
# count defines how many periods there are, i.e. # rising edges (int)
#
##############################################################################
def generate_periodic_act_events(pin="SIG1", offset=0.0, period=1.0, duty_cycle=0.5, count=1):
    if count < 1 or duty_cycle == 0 or duty_cycle > 1.0 or offset < 0.0:
        return FAILED
    result = []
    offset = 1000000 * offset     # convert to us
    # get command for high and low for the requested pin
    cmd_high = level_str2abbr('high', pin)
    cmd_low  = level_str2abbr('low', pin)
    for c in range(count):
        result.append([cmd_high, int(offset)])
        offset = offset + period * 1000000 * duty_cycle
        result.append([cmd_low, int(offset)])
        offset = offset + period * 1000000 * (1.0 - duty_cycle)
    return result
### END generate_periodic_act_events()


##############################################################################
#
# jlink_mcu_str - Get the MCU name from the platform
#
##############################################################################
def jlink_mcu_str(platform=""):
    if not platform:
        return None
    strdict = {
                'dpp2lora' : 'STM32L433CC',
                'nrf5'     : 'nRF52840_xxAA',
              }
    try:
        mcu = strdict[platform.lower()]
    except KeyError:
        return None
    return mcu
### END jlink_mcu_str()


##############################################################################
#
# tg_set_vcc - set voltage on the active interface
#
##############################################################################
def tg_set_vcc(v=tg_vcc_default):
    if v is None or v < 1.1 or v > 3.6:
        return FAILED
      
    bus = smbus.SMBus(2)  # I2C2
    
    DEVICE_ADDR = 0x60    # device part number: MCP47CVB01-E/MF
    DEVICE_REG  = 0x0
    VREF        = 800     # mV
    VDD         = 3300    # mV
    R11         = 12      # kOhm
    R12         = 11.5    # kOhm
    R13         = 4.7     # kOhm
    R12R11      = R12 / R11
    R11R13      = (R11 + R13) / R13
    
    v_dac  = VREF - (R12R11 * (v * 1000 - VREF * R11R13))
    cfgval = int(v_dac * 255 / VDD)
    try:
        bus.write_word_data(DEVICE_ADDR, DEVICE_REG, (cfgval * 256) & 0xffff)
    except (IOError) as e:
        return FAILED
    
    return SUCCESS
### END tg_set_vcc()


##############################################################################
#
# tg_get_vcc - read the configured target voltage value
#
##############################################################################
def tg_get_vcc():
    bus = smbus.SMBus(2)  # I2C2
    DEVICE_ADDR = 0x60    # device part number: MCP47CVB01-E/MF
    DEVICE_REG  = 0x0
    VREF        = 800     # mV
    VDD         = 3300    # mV
    R11         = 12      # kOhm
    R12         = 11.5    # kOhm
    R13         = 4.7     # kOhm
    R12R11      = R12 / R11
    R11R13      = (R11 + R13) / R13
    try:
        res = bus.read_word_data(DEVICE_ADDR, DEVICE_REG)
    except (IOError) as e:
        return FAILED
    v_dac = ((float(res) / 256) * VDD) / 255
    vcc = int((VREF - v_dac) / R12R11 + (VREF * R11R13)) / 1000
    return vcc
### END tg_get_vcc()


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
# get_pid - returns the PID of the first matching process
#
##############################################################################
def get_pid(process_name=None):
    if not process_name:
        return FAILED
    cmd = ['pgrep', '-f', process_name]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, universal_newlines=True)
    pid, err = p.communicate()
    if p.returncode != 0:
        return FAILED
    if pid:
        pids = pid.split('\n')
        return int(pids[0])
    return FAILED
### END get_pid()


##############################################################################
#
# get_pids - returns a list of PIDs of which the command matches a certain string
#
##############################################################################
def get_pids(process_name=None):
    if not process_name:
        return None
    cmd = ['pgrep', '-f', process_name]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, universal_newlines=True)
    pids, err = p.communicate()
    if p.returncode != 0:
        return FAILED
    if pids:
        pid_list = []
        for p in pids.strip().split('\n'):
            pid_list.append(int(p))
        return pid_list
    return None
### END get_pids()


##############################################################################
#
# start_pwr_measurement
#
##############################################################################
def start_pwr_measurement(out_file=None, sampling_rate=rl_default_rate, num_samples=0, start_time=0):
    if sampling_rate not in rl_samp_rates:
        if logger:
            logger.warn("Invalid sampling rate '%s'" % str(sampling_rate))
        return errno.EINVAL
    if not out_file:
        out_file = "%s/powerprofiling_%s.rld" % (config.get("observer", "testresultfolder"), time.strftime("%Y%m%d%H%M%S", time.gmtime()))
    cmd = ["rocketlogger", "start", "-b", "--channel=V1,V2,I1L,I1H", "--output=%s" % out_file, "--rate=%d" % int(sampling_rate), "--offset=%f" % rl_time_offset]
    if num_samples:
        if num_samples > rl_max_samples:
            num_samples = rl_max_samples
        cmd.append(("--samples=%d" % int(num_samples)))
    if start_time > 0:
        cmd.append(("--tstart=%d" % int(start_time)))
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
    # check if process exists
    p = subprocess.Popen(['pgrep', '-f', 'rocketlogger start'], stdout=subprocess.PIPE)
    rs = p.wait()
    if rs != 0:
        return SUCCESS      # process does not exist
    cmd = ["rocketlogger", "stop"]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    return SUCCESS
### END stop_pwr_measurement()


##############################################################################
#
# start_serial_logging
#
##############################################################################
def start_serial_logging(port=tg_serial_port, baudrate=115200, out_file=None):
    if not out_file:
        return FAILED
    if port.lower() == "serial" or port == tg_serial_port:
        port = tg_serial_port
    elif port.lower() == "usb" or port == tg_usb_port:
        port = tg_usb_port
    else:
        return FAILED
    cmd = ["serialreader", port, str(baudrate), out_file]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    # do not call communicate(), it will block
    logger.debug("Serial logger started with command '%s'." % (" ".join(cmd)))
    return SUCCESS
### END start_serial_logging()


##############################################################################
#
# stop_serial_logging
#
##############################################################################
def stop_serial_logging(timeout=5):
    pid = get_pid('serialreader')
    if pid <= 0:
        return SUCCESS      # process does not exist
    try:
        os.kill(pid, signal.SIGINT)   # note: send SIGINT to tell the process to stop
        rs = 0
        while rs == 0 and timeout:
            time.sleep(1)
            timeout = timeout - 1
            p = subprocess.Popen(['pgrep', '-f', 'serialreader'], stdout=subprocess.PIPE)
            rs = p.wait()
        if rs != 0:
            return SUCCESS
    except:
        if logger:
            logger.error("An error occurred in stop_serial_logging(): %s, %s", str(sys.exc_info()[0]), str(sys.exc_info()[1]))
        pass
    return FAILED
### END stop_serial_logging()


##############################################################################
#
# start_gpio_tracing
#
##############################################################################
def start_gpio_tracing(out_file=None, start_time=0, stop_time=0, pins=0x0, offset=0, extra_opts=0):
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
                if offset != 0:
                    cmd.append(str(offset))
                    # append extra commands
                    if extra_opts != 0:
                        cmd.append(str(extra_opts))
    #if logger:
    #    logger.debug("Starting GPIO tracing service with command: %s" % " ".join(cmd))
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    # do not call communicate(), it will block
    return SUCCESS
### END start_gpio_tracing()


##############################################################################
#
# stop_gpio_tracing
#
##############################################################################
def stop_gpio_tracing(timeout=30):
    pid = get_pid('fl_logic')
    if pid <= 0:
        return SUCCESS      # process does not exist
    try:
        os.kill(pid, signal.SIGINT)   # note: send SIGINT to tell the process to stop, SIGTERM will force termination
        if logger:
            logger.debug("Waiting for gpio tracing service to stop (PID %u)..." % pid)
        rs = 0
        while rs == 0 and timeout:
            time.sleep(1)
            timeout = timeout - 1
            p = subprocess.Popen(['pgrep', '-f', 'fl_logic'], stdout=subprocess.PIPE)
            rs = p.wait()
        if rs != 0:
            return SUCCESS
        else:
            # force process to stop
            os.kill(pid, signal.SIGTERM)
            logger.debug("Forced termination of process with ID %u." % pid)
    except:
        if logger:
            logger.error("An error occurred in stop_gpio_tracing(): %s, %s", str(sys.exc_info()[0]), str(sys.exc_info()[1]))
        pass
    return FAILED
### END stop_gpio_tracing()


##############################################################################
#
# start_gpio_actuation
#
##############################################################################
def start_gpio_actuation(start_time=None, act_events=[]):
    if not start_time or not isinstance(act_events, list) or len(act_events) == 0 or not isinstance(act_events[0], list):
        return FAILED
    # check whether the kernel module is loaded
    if not os.path.exists(actuationdev):
        if logger:
            logger.warning("GPIO actuation kernel module is not running.")
        return FAILED
    # Sort the events
    act_events.sort(key=lambda pair: pair[1])
    act_cmd = ""
    last_event = 0
    for evt in act_events:
        if len(evt) != 2:
            if logger:
                logger.warning("Invalid argument in act_events.")
            return FAILED
        act_cmd += "%c%u " % (evt[0], (evt[1] - last_event))    # only send the time difference to the previous event
        last_event = evt[1]
    # Append the start command
    act_cmd += "S%u" % (start_time)
    if logger:
        logger.debug("Configuring GPIO actuation service with command: '%s'" % act_cmd);
    # write the command string into the actuation device
    with open(actuationdev, 'w') as f:
        f.write(act_cmd)
    time.sleep(0.1)
    # check return code
    ret = ""
    with open(actuationdev, 'r') as f:
        ret = f.read()
    if "OK" not in ret:
        if logger:
            logger.error("Configuration of GPIO actuation service failed.")
        return FAILED
    return SUCCESS
### END start_gpio_actuation()


##############################################################################
#
# stop_gpio_actuation
#
##############################################################################
def stop_gpio_actuation():
    if not os.path.exists(actuationdev):
        return SUCCESS    # treat as success since service is not running anymore
    with open(actuationdev, 'w') as f:
        f.write("C")
    time.sleep(0.1)
    # check return code
    ret = ""
    with open(actuationdev, 'r') as f:
        ret = f.read()
    if "OK" not in ret:
        if logger:
            logger.error("Failed to stop GPIO actuation service.")
        return FAILED
    return SUCCESS
### END stop_gpio_actuation()


##############################################################################
#
# start_gdb_server
#
##############################################################################
def start_gdb_server(platform=None, port=2331, delay=0):
    if not platform or platform not in tg_platforms:
        return FAILED
    platform = jlink_mcu_str(platform)
    if not platform:
        return FAILED
    if get_pid("JLinkGDBServer") >= 0:
        return FAILED     # already running!
    if logger:
        logger.debug("Will start GDBServer in %ds..." % delay)
    #os.system("sleep %d > /dev/null 2>&1 && JLinkGDBServer -device %s -if SWD -speed 4000 -port %d > %s 2>&1 &" % (delay, platform, port, gdblog))
    args = "sleep %d; JLinkGDBServer -device %s -if SWD -speed 4000 -port %d -nohalt > %s 2>&1 &" % (delay, platform, port, gdblog)
    p = subprocess.Popen(["/bin/bash", "-c", args], stdout=subprocess.PIPE)
    return SUCCESS
    #time.sleep(5)
    # check if process is still running
    #if get_pid("JLinkGDBServer") >= 0:
    #    return SUCCESS
    #return FAILED
### END start_gdb_server()


##############################################################################
#
# stop_gdb_server
#
##############################################################################
def stop_gdb_server():
    gdbpid = get_pid("JLinkGDBServer")
    if gdbpid > 0:
        os.kill(gdbpid, signal.SIGTERM)
    return SUCCESS
### END stop_gdb_server()


##############################################################################
#
# start_data_trace
#
##############################################################################
def start_data_trace(platform=None, dwtconfig=None, outputfile=None):
    if not platform or not outputfile or not dwtconfig:
        return FAILED
    cmd = [config.get("observer", "datatraceservice"), '--output=%s' % outputfile, '--platform=%s' % platform, '--config=%s' % dwtconfig]
    p = subprocess.Popen(cmd)
    rs = p.wait()
    if rs != SUCCESS:
        return FAILED
    return SUCCESS
### END start_data_trace()


##############################################################################
#
# stop_data_trace
#
##############################################################################
def stop_data_trace():
    cmd = [config.get("observer", "datatraceservice"), '--stop']
    p = subprocess.Popen(cmd)
    rs = p.wait()
    if rs not in (SUCCESS, errno.ENOPKG):
        return FAILED
    return SUCCESS


##############################################################################
#
# get_pps_count from the kernel module stats
#
##############################################################################
def get_pps_count():
    if os.path.exists(gmtimerstats):
        try:
            with open(gmtimerstats) as ppsstats:
                return ppsstats.read().split()[1]
        except:
            return FAILED
### END get_pps_count()


##############################################################################
#
# store_pps_count in a temporary file in the test results directory
#
##############################################################################
def store_pps_count(testid=None):
    if testid:
        ppsfile = "%s/%d/ppscount" % (config.get("observer", "testresultfolder"), testid)
        with open(ppsfile, "w") as ppsfile:
            ppsfile.write("%s %s" % (str(time.time()), get_pps_count()))
### END get_pps_count()


##############################################################################
#
# get_pps_delta calculates the percentage of received PPS pulses since on the previously stored value with store_pps_count()
#
##############################################################################
def get_pps_delta(testid=None):
    if testid:
        ppscount = get_pps_count()
        if ppscount == FAILED:
            return FAILED
        ppsfile = "%s/%d/ppscount" % (config.get("observer", "testresultfolder"), testid)
        if os.path.isfile(ppsfile):
            try:
                with open(ppsfile) as f:
                    ppsstatsstart = f.read().split()
                    deltacount = int(ppscount) - int(ppsstatsstart[1])
                    deltaT = int(time.time() - float(ppsstatsstart[0]))
                    return min(100.0, (deltacount * 100.0 / deltaT))
            except:
                return FAILED
        else:
            return FAILED
### END get_pps_count()


##############################################################################
#
# parse_int()   parses a string to int
#
##############################################################################
def parse_int(s):
    res = 0
    if s:
        try:
            res = int(float(str(s).strip())) # higher success rate if first parsed to float
        except ValueError:
            if logger:
                logger.warn("Could not parse %s to int." % (str(s)))
    return res
### END parse_int()


##############################################################################
#
# parse_float()   parses a string to float
#
##############################################################################
def parse_float(s):
    res = 0.0
    if s:
        try:
            res = float(str(s).strip())
        except ValueError:
            if logger:
                logger.warn("Could not parse %s to float." % (str(s)))
    return res
### END parse_float()
