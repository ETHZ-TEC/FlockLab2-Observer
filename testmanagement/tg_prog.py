#! /usr/bin/env python3

import os, sys, getopt, subprocess, errno, time, serial
import lib.flocklab as flocklab
import stm32loader.stm32loader as stm32loader
from intelhex import hex2bin

# bootstrap loader scripts
#import msp430.bsl5.uart


debug = False


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
def prog_msp430(imagefile, port, prog_toggle_num=1, progstate=0, speed=38400):
    global debug
    usleep = 0.001

    flocklab.gpio_clr(flocklab.gpio_tg_nrst)
    flocklab.gpio_set(flocklab.gpio_tg_prog)

    time.sleep(usleep)
    
    for i in range(0, prog_toggle_num):
        #prog.write(0)
        flocklab.gpio_clr(flocklab.gpio_tg_prog, 0)
        time.sleep(usleep)
    
        #prog.write(1)
        flocklab.gpio_set(flocklab.gpio_tg_prog, 1)
        time.sleep(usleep)
    
    flocklab.gpio_set(flocklab.gpio_tg_nrst)  # release reset
    time.sleep(usleep)
    flocklab.gpio_clr(flocklab.gpio_tg_prog)
    
    if progstate == 1:
        time.sleep(usleep)
        flocklab.gpio_set(flocklab.gpio_tg_prog)
    
    cmd = ["python","-m","msp430.bsl5.uart","-p", port, "-e", "-S", "-V", "--speed=%d" %speed, "-i", "ihex", "-P", imagefile, "-v", "--debug"]
    
    if debug:
        cmd.append("-vvv")
        cmd.append("--debug")
    try:
        subprocess.call(cmd)
    except Exception:
        flocklab.tg_reset()
        return 3
    
    # Revert back all config changes:
    subprocess.call(["stty", "-F", port, "-parenb", "iexten", "echoe", "echok", "echoctl", "echoke", "115200"])
    flocklab.gpio_clr(flocklab.gpio_tg_prog)

    return flocklab.SUCCESS
### END reprog_cc430()


##############################################################################
#
# MSP432 via serial port / bootloader
#
##############################################################################
def prog_msp432(imagefile, port, speed):
    global debug
    usleep = 0.001

    flocklab.set_pin(flocklab.gpio_tg_nrst, 0)
    flocklab.set_pin(flocklab.gpio_tg_prog, 1)
    time.sleep(usleep)

    flocklab.set_pin(flocklab.gpio_tg_nrst, 1)
    time.sleep(5)

    cmd = ["python","-m","msp430.bsl5.uart","-p", port, "-e", "-S", "-V","--speed=%d" % speed, "-i", "ihex", "-P", imagefile, "-v", "--debug"]
    if debug:
        cmd.append("-vvv")
        cmd.append("--debug")
    try:
        subprocess.call(cmd)
    except Exception:
        flocklab.tg_reset()
        return 3
    
    flocklab.set_pin(flocklab.gpio_tg_prog, 0)
    
    # Revert back all config changes:
    #subprocess.call(["stty", "-F", port, "-parenb", "iexten", "echoe", "echok", "echoctl", "echoke", "115200"])

    return flocklab.SUCCESS
### END prog_msp432()


##############################################################################
#
# STM32L4 via serial port / bootloader
#
##############################################################################
def prog_stm32l4(imagefile, port, speed=115200):
    global debug
    usleep = 0.001

    # stm32loader expects a binary file
    if "hex" in os.path.splitext(imagefile)[1]:
        hex2bin(imagefile, imagefile + ".binary")
        imagefile = imagefile + ".binary"
    elif "elf" in os.path.splitext(imagefile)[1]:
        ret = os.system("objcopy -O binary " + imagefile + " " + imagefile + ".binary")
        if ret != 0:
            logger.debug("Failed to convert elf file to binary.")
        else:
            imagefile = imagefile + ".binary"
    if not "bin" in os.path.splitext(imagefile)[1]:
        logger.error("stm32loader expects a binary file")
        return errno.EINVAL

    # BSL entry sequence
    flocklab.set_pin(flocklab.gpio_tg_prog, 0)
    flocklab.set_pin(flocklab.gpio_tg_nrst, 0)
    flocklab.set_pin(flocklab.gpio_tg_prog, 1)
    time.sleep(usleep)
    flocklab.set_pin(flocklab.gpio_tg_nrst, 1)

    # call the bootloader script
    loader = stm32loader.Stm32Loader()
    loader.configuration['data_file'] = imagefile
    loader.configuration['port'] = port
    loader.configuration['baud'] = 115200
    loader.configuration['parity'] = serial.PARITY_EVEN
    loader.configuration['erase'] = True
    loader.configuration['write'] = True
    loader.configuration['verify'] = True
    if debug:
        stm32loader.VERBOSITY = 10
    else:
        stm32loader.VERBOSITY = 0
    loader.connect()
    if loader.read_device_details() != 0x435:
        flocklab.tg_reset()
        return 2
    loader.perform_commands()
    
    flocklab.tg_reset()
    
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
        ret = prog_msp430(imagefile, flocklab.tg_serial_port, progstate = 1, speed=115200)
    elif core == 1: # BOLT
        ret = prog_msp430(imagefile, flocklab.tg_serial_port, speed=115200)
    elif core == 2: # APP
        ret = prog_msp432(imagefile, flocklab.tg_serial_port, 57600)
    elif core == 3: # SENSOR
        ret = prog_msp430(imagefile, flocklab.tg_serial_port, progstate = 1, speed=115200)

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
        print("Failed to program target via SWD. Message: %s" % out)
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
    
    # Get logger:
    logger = flocklab.get_logger("tg_prog.py")
    
    # Get command line parameters.
    try:
        opts, args = getopt.getopt(argv, "dhi:t:p:c:", ["debug", "help", "image=", "target=", "port=", "core="])
    except getopt.GetoptError  as err:
        logger.error(str(err))
        usage()
        sys.exit(errno.EINVAL)
    for opt, arg in opts:
        if opt in ("-h", "--help"):
            usage()
            sys.exit(flocklab.SUCCESS)
        elif opt in ("-d", "--debug"):
            debug = True
        elif opt in ("-i", "--image"):
            imagefile = arg
            if not (os.path.exists(imagefile)):
                err = "Error: file %s does not exist" %(str(imagefile))
                logger.error(str(err))
                sys.exit(errno.EINVAL)
        elif opt in ("-t", "--target"):
            target = arg
        elif opt in ("-p", "--port"):
            porttype = arg
        elif opt in ("-c", "--core"):
            core = int(arg)
        else:
            logger.error("Unknown argument %s" % opt)
            sys.exit(errno.EINVAL)
    
    # Check mandatory parameters
    if (imagefile == None) or (target == None):
        logger.error("No image file or target specified.")
        usage()
        sys.exit(errno.EINVAL)
    
    # Check if file exists
    if not os.path.isfile(imagefile):
        logger.error("Image file '%s' not found." % imagefile)
        sys.exit(errno.EINVAL)
    
    # Set environment variable needed for programmer: 
    #os.environ["PYTHONPATH"] = os.environ.get("PYTHONPATH", "") + "/usr/local/lib/python2.7/"
    
    # Set target voltage to 3.3V and make sure power & actuation is enabled
    flocklab.tg_set_vcc(3.3)
    flocklab.tg_pwr_en()
    flocklab.set_pin(flocklab.gpio_tg_prog, 0)
    flocklab.set_pin(flocklab.gpio_tg_act_nen, 0)
    
    # Flash the target:
    print("Programming target %s with image %s..." % (target, imagefile))
    if target == 'dpp':
        rs = prog_dpp(imagefile, core)
    elif target == 'dpp2lora' or target == 'dpp2lorahg':
        if porttype in ("SWD", "swd"):
            rs = prog_swd(imagefile, "STM32L433CC")
        else:
            rs = prog_stm32l4(imagefile, flocklab.tg_serial_port)
    elif target == 'nrf5':
        rs = prog_swd(imagefile, "nRF52840_xxAA")
    else:
        print("Unknown target '%s'" % target)
    
    # Return an error if there was one while flashing:
    if (rs != 0):
        logger.error("Image could not be flashed to target. Error %d occurred." % rs)
        sys.exit(errno.EIO)
    else:
        logger.info("Target node flashed successfully.")
        sys.exit(flocklab.SUCCESS)
### END main()


if __name__ == "__main__":
    main(sys.argv[1:])
