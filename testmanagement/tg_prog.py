#! /usr/bin/env python3

import os, sys, getopt, subprocess, errno, time, serial, traceback
import lib.flocklab as flocklab
import lib.stm32loader as stm32loader
from intelhex import hex2bin

#import msp430.bsl5.uart
#os.environ["PYTHONPATH"] = os.environ.get("PYTHONPATH", "") + "/home/flocklab/observer/testmanagement/lib"

debug = False


##############################################################################
#
# Usage
#
##############################################################################
def usage():
    print("Usage: %s --image=<path> --target=<string> [--port=<string>] [--core=<int>] [--debug] [--help]" %sys.argv[0])
    print("Program a target node. Target voltage will be changed to 3.3V.")
    print("Options:")
    print("  --image=<path>\tAbsolute path to image file which is to be flashed onto target node")
    print("  --target=<string>\tType of target")
    print("  --port=<string>\tOptional. Specify port which is used for reprogramming (serial or SWD).")
    print("  --core=<int>\t\tOptional. Specify core to program. Defaults to 0.")
    print("  --debug\t\tOptional. Print debug messages to log.")
    print("  --help\t\tOptional. Print this help.")
### END usage()


##############################################################################
#
# MSP430 via serial port / bootloader
#
##############################################################################
def prog_msp430(imagefile, port, speed=38400):
    
    # both pins high
    flocklab.gpio_set(flocklab.gpio_tg_nrst)
    flocklab.gpio_set(flocklab.gpio_tg_prog)
    time.sleep(0.2)
    
    # both pins low
    flocklab.gpio_clr(flocklab.gpio_tg_nrst)
    flocklab.gpio_clr(flocklab.gpio_tg_prog)
    time.sleep(0.01)
    
    # toggle TEST pin to trigger BSL entry
    flocklab.gpio_set(flocklab.gpio_tg_prog)
    time.sleep(0.01)
    flocklab.gpio_clr(flocklab.gpio_tg_prog)
    time.sleep(0.01)
    flocklab.gpio_set(flocklab.gpio_tg_prog)
    time.sleep(0.01)
    
    # release reset
    flocklab.gpio_set(flocklab.gpio_tg_nrst)
    time.sleep(0.01)
    flocklab.gpio_clr(flocklab.gpio_tg_prog)
    # bootloader should start now
    
    # currently only runs with python2.7
    cmd = ["python2.7", "-m", "msp430.bsl5.uart", "-p", port, "-e", "-S", "-V", "--no-start", "--speed=%d" %speed, "-i", "ihex", "-P", imagefile]
    if debug:
        cmd.append("-v")
        cmd.append("--debug")
    rs = subprocess.call(cmd)
    
    if rs != 0:
        return flocklab.FAILED
    return flocklab.SUCCESS
### END reprog_cc430()


##############################################################################
#
# MSP432 via serial port / bootloader
#
##############################################################################
def prog_msp432(imagefile, port, speed):
    
    # both pins high
    flocklab.gpio_set(flocklab.gpio_tg_nrst)
    flocklab.gpio_set(flocklab.gpio_tg_prog)
    time.sleep(0.2)
    
    # both low
    flocklab.gpio_clr(flocklab.gpio_tg_nrst)
    flocklab.gpio_clr(flocklab.gpio_tg_prog)
    
    # prog high
    flocklab.set_pin(flocklab.gpio_tg_prog, 1)
    time.sleep(0.01)
    
    # release reset
    flocklab.set_pin(flocklab.gpio_tg_nrst, 1)
    time.sleep(1)

    cmd = ["python2.7", "-m", "msp430.bsl5.uart", "-p", port, "-e", "-S", "-V", "--no-start", "--speed=%d" % speed, "-i", "ihex", "-P", imagefile]
    if debug:
        cmd.append("-v")
        cmd.append("--debug")
    rs = subprocess.call(cmd)
    
    if rs != 0:
        return flocklab.FAILED
    return flocklab.SUCCESS
### END prog_msp432()


##############################################################################
#
# TelosB (Tmote Sky) via USB / bootloader
#
##############################################################################
def prog_telosb(imagefile, speed=38400):
    
    # both pins high
    flocklab.gpio_set(flocklab.gpio_tg_nrst)
    flocklab.gpio_set(flocklab.gpio_tg_prog)
    time.sleep(0.2)
    
    # currently only runs with python2.7
    cmd = ["python2.7", "-m", "msp430.bsl.target.telosb", "-p", flocklab.tg_usb_port, "-e", "-S", "-V", "--speed=%d" % speed, "-i", "ihex", "-P", imagefile]
    if debug:
        cmd.append("-v")
        cmd.append("--debug")
    rs = subprocess.call(cmd)
    
    if rs != 0:
        return flocklab.FAILED
    return flocklab.SUCCESS
### END reprog_cc430()


##############################################################################
#
# STM32L4 via serial port / bootloader
#
##############################################################################
def prog_stm32l4(imagefile, port, speed=115200):
    global debug

    # stm32loader expects a binary file
    if "hex" in os.path.splitext(imagefile)[1]:
        hex2bin(imagefile, imagefile + ".binary")
        imagefile = imagefile + ".binary"
    elif "elf" in os.path.splitext(imagefile)[1]:
        ret = os.system("objcopy -O binary " + imagefile + " " + imagefile + ".binary")
        if ret != 0:
            flocklab.log_warning("Failed to convert elf file to binary.")
        else:
            imagefile = imagefile + ".binary"
    if not "bin" in os.path.splitext(imagefile)[1]:
        flocklab.log_error("stm32loader expects a binary file")
        return errno.EINVAL

    # BSL entry sequence
    flocklab.set_pin(flocklab.gpio_tg_nrst, 1)    # reset high
    flocklab.set_pin(flocklab.gpio_tg_prog, 0)    # prog low
    flocklab.set_pin(flocklab.gpio_tg_nrst, 0)    # reset low
    time.sleep(0.01)
    flocklab.set_pin(flocklab.gpio_tg_prog, 1)    # prog high
    time.sleep(0.01)
    flocklab.set_pin(flocklab.gpio_tg_nrst, 1)    # reset high
    time.sleep(0.1)

    # call the bootloader script
    loader = stm32loader.Stm32Loader()
    loader.configuration['data_file'] = imagefile
    loader.configuration['port'] = port
    loader.configuration['baud'] = 115200
    loader.configuration['parity'] = serial.PARITY_EVEN
    loader.configuration['erase'] = True
    loader.configuration['write'] = True
    loader.configuration['verify'] = True
    stm32loader.ENTRY_SEQUENCE = False
    if debug:
        stm32loader.VERBOSITY = 10
    else:
        stm32loader.VERBOSITY = 0
    loader.connect()
    if loader.read_device_details() != 0x435:
        return 2
    loader.perform_commands()
    
    # Revert back all config changes:
    #subprocess.call(["stty", "-F", port, "-parenb", "iexten", "echoe", "echok", "echoctl", "echoke", "115200"])

    return flocklab.SUCCESS
### END prog_stm32l4()


##############################################################################
#
# Dual Processor Platform v1
#
##############################################################################
def prog_dpp(imagefile, core):
    core2sig = ((0,0),(1,0),(0,1),(1,1)) # (sig1,sig2)

    # select core
    flocklab.set_pin(flocklab.gpio_tg_sig1, core2sig[core][0])
    flocklab.set_pin(flocklab.gpio_tg_sig2, core2sig[core][1])
    
    # program
    ret = 1
    if core == 0: # COMM
        ret = prog_msp430(imagefile, flocklab.tg_serial_port, 115200)
    elif core == 1: # BOLT
        ret = prog_msp430(imagefile, flocklab.tg_serial_port, 115200)
    elif core == 2: # APP
        ret = prog_msp432(imagefile, flocklab.tg_serial_port, 57600)
    elif core == 3: # SENSOR
        ret = prog_msp430(imagefile, flocklab.tg_serial_port, 115200)

    flocklab.set_pin(flocklab.gpio_tg_sig1, 0)
    flocklab.set_pin(flocklab.gpio_tg_sig2, 0)

    return ret
### END prog_dpp()


##############################################################################
#
# Program via SWD / J-Link
#
##############################################################################
def prog_swd(imagefile, device):
    cmd = 'loadfile %s\nr\nq\n' % imagefile
    # JRunExe -device STM32L433CC -if SWD -speed 4000 imagefile
    p = subprocess.Popen(['JLinkExe', '-device', device, '-if', 'SWD', '-speed', 'auto', '-autoconnect', '1'], stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    out, err = p.communicate(input=cmd)
    if "Core found" not in out:
        flocklab.log_error("Failed to program target via SWD. Message: %s" % out)
        return -1
    return flocklab.SUCCESS


##############################################################################
#
# Main
#
##############################################################################
def main(argv):
    global debug
    
    porttype  = "serial"
    imagefile = None
    target    = None
    core      = 0
    
    # Get command line parameters.
    try:
        opts, args = getopt.getopt(argv, "dhi:t:p:c:", ["debug", "help", "image=", "target=", "port=", "core="])
    except getopt.GetoptError  as err:
        flocklab.error_logandexit(str(err), errno.EINVAL)
    for opt, arg in opts:
        if opt in ("-h", "--help"):
            usage()
            sys.exit(flocklab.SUCCESS)
        elif opt in ("-d", "--debug"):
            debug = True
        elif opt in ("-i", "--image"):
            imagefile = arg
        elif opt in ("-t", "--target"):
            target = arg.lower()
        elif opt in ("-p", "--port"):
            porttype = arg
        elif opt in ("-c", "--core"):
            core = int(arg)
        else:
            flocklab.error_logandexit("Unknown argument %s" % opt, errno.EINVAL)
    
    # Check mandatory parameters
    if (imagefile == None) or (target == None):
        flocklab.error_logandexit("No image file or target specified.", errno.EINVAL)
    
    # Get logger
    logger = flocklab.get_logger(debug=debug)
    
    # Check if file exists
    if not os.path.isfile(imagefile):
        flocklab.error_logandexit("Image file '%s' not found." % imagefile, errno.ENOENT)
    
    # Set target voltage to default value and make sure power, MUX and actuation are enabled
    flocklab.tg_set_vcc()
    flocklab.tg_pwr_en()
    flocklab.tg_mux_en()
    flocklab.tg_act_en()
    
    # Enable and reset the target (also ensures the PROG pin is low)
    flocklab.tg_en()
    flocklab.tg_reset()
    
    # Flash the target:
    logger.info("Programming target %s with image %s..." % (target, imagefile))
    rs = 0
    if target == 'dpp':
        rs = prog_dpp(imagefile, core)
    elif target in ('dpp2lora', 'dpp2lorahg'):
        if porttype in ("SWD", "swd"):
            rs = prog_swd(imagefile, "STM32L433CC")
        else:
            try:
                rs = prog_stm32l4(imagefile, flocklab.tg_serial_port)
            except:     # use except here to also catch sys.exit()
                rs = 1
    elif target == 'nrf5':
        rs = prog_swd(imagefile, "nRF52840_xxAA")
    elif target in ('tmote', 'telosb', 'sky'):
        rs = prog_telosb(imagefile)
    else:
        logger.error("Unknown target '%s'" % target)
    
    # Revert back all config changes:
    #subprocess.call(["stty", "-F", port, "-parenb", "iexten", "echoe", "echok", "echoctl", "echoke", "115200"])
    
    # Reset
    flocklab.tg_reset()
    #flocklab.gpio_clr(flocklab.gpio_tg_prog)  -> already done in tg_reset()
    
    # Return an error if there was one while flashing:
    if (rs != 0):
        flocklab.error_logandexit("Image could not be flashed to target. Error %d occurred." % rs, errno.EIO)
    
    logger.info("Target node flashed successfully.")
    sys.exit(flocklab.SUCCESS)
### END main()


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except Exception:
        flocklab.error_logandexit("Encountered error: %s\n%s\nCommandline was: %s" % (str(sys.exc_info()[1]), traceback.format_exc(), str(sys.argv)))
