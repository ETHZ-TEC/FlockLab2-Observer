#! /usr/bin/env python3

"""
Copyright (c) 2020, ETH Zurich, Computer Engineering Group
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

* Redistributions of source code must retain the above copyright notice, this
  list of conditions and the following disclaimer.

* Redistributions in binary form must reproduce the above copyright notice,
  this list of conditions and the following disclaimer in the documentation
  and/or other materials provided with the distribution.

* Neither the name of the copyright holder nor the names of its
  contributors may be used to endorse or promote products derived from
  this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
POSSIBILITY OF SUCH DAMAGE.

Author: Reto Da Forno
"""

import os, sys, getopt, subprocess, errno, time, serial, traceback
import lib.flocklab as flocklab
from stm32loader.main import Stm32Loader
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

    # both pins low
    flocklab.gpio_clr(flocklab.gpio_tg_nrst)
    flocklab.gpio_clr(flocklab.gpio_tg_prog)
    time.sleep(0.001)

    # toggle TEST pin to trigger BSL entry
    flocklab.gpio_set(flocklab.gpio_tg_prog)
    time.sleep(0.001)
    flocklab.gpio_clr(flocklab.gpio_tg_prog)
    time.sleep(0.001)
    flocklab.gpio_set(flocklab.gpio_tg_prog)
    time.sleep(0.001)

    # release reset
    flocklab.gpio_set(flocklab.gpio_tg_nrst)
    time.sleep(0.001)
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
    # for some reason, programming of the msp432 'randomly' fails on some observers; try multiple times as a workaround
    tries = 10

    while tries:
        # both low
        flocklab.gpio_clr(flocklab.gpio_tg_nrst)
        flocklab.gpio_clr(flocklab.gpio_tg_prog)
        time.sleep(0.001)
        # prog high
        flocklab.gpio_set(flocklab.gpio_tg_prog)
        time.sleep(0.001)
        # release reset
        flocklab.gpio_set(flocklab.gpio_tg_nrst)
        # note: do not add delays here!

        # currently only runs with python2.7
        cmd = ["python2.7", "-m", "msp430.bsl32.uart", "-p", port, "-e", "-S", "-V", "--no-start", "--speed=%d" % speed, "-i", "ihex", "-P", imagefile]
        if debug:
            cmd.append("-v")
            cmd.append("--debug")
        rs = subprocess.call(cmd)
        if rs != 0:
            if tries <= 1:
                return flocklab.FAILED
        else:
            break
        tries = tries - 1

    if tries < 10:
        flocklab.log_info("Took %d tries to flash the target via BSL." % (11 - tries))

    return flocklab.SUCCESS
### END prog_msp432()


##############################################################################
#
# TelosB (Tmote Sky) via USB / bootloader
#
##############################################################################
def prog_telosb(imagefile, speed=38400):
    if os.path.splitext(imagefile)[1] in (".exe", ".sky"):
        ret = os.system("objcopy -O ihex %s %s.ihex" % (imagefile, imagefile))
        if ret != 0:
            flocklab.log_warning("Failed to convert elf file to Intel hex.")
        else:
            flocklab.log_debug("File '%s' converted to Intel hex format." % imagefile)
            imagefile = imagefile + ".ihex"
    if "hex" not in os.path.splitext(imagefile)[1]:
        flocklab.log_error("Invalid file format, Intel hex file expected.")
        return -1

    # check if the device exists
    if not os.path.exists(flocklab.tg_usb_port):
        flocklab.log_error("Device %s does not exist." % flocklab.tg_usb_port)
        return flocklab.FAILED

    # currently only runs with python2.7
    #cmd = ["msp430-bsl-telosb", "-p", flocklab.tg_usb_port, "-e", "-S", "-V", "-i", "ihex", "-P", imagefile]
    # note: verify option ("-V") removed since it takes too much time (up to 25s)
    cmd = ["python2.7", "-m", "msp430.bsl.target.telosb", "-p", flocklab.tg_usb_port, "-e", "-S", "--speed=%d" % speed, "-i", "ihex", "-P", imagefile]
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
    tries = 2
    
    # stm32loader expects a binary file
    if "hex" in os.path.splitext(imagefile)[1]:
        hex2bin(imagefile, imagefile + ".binary")
        imagefile = imagefile + ".binary"
    elif "elf" in os.path.splitext(imagefile)[1]:
        ret = os.system("objcopy -O binary " + imagefile + " " + imagefile + ".binary")
        if ret != 0:
            flocklab.log_warning("Failed to convert elf file to binary.")
        else:
            flocklab.log_debug("File '%s' converted to binary format." % imagefile)
            imagefile = imagefile + ".binary"
    if not "bin" in os.path.splitext(imagefile)[1]:
        flocklab.log_error("stm32loader expects a binary file")
        return errno.EINVAL

    while tries:
        # BSL entry sequence
        flocklab.set_pin(flocklab.gpio_tg_nrst, 1)    # reset high
        flocklab.set_pin(flocklab.gpio_tg_prog, 0)    # prog low
        flocklab.set_pin(flocklab.gpio_tg_nrst, 0)    # reset low
        time.sleep(0.001)
        flocklab.set_pin(flocklab.gpio_tg_prog, 1)    # prog high
        time.sleep(0.001)
        flocklab.set_pin(flocklab.gpio_tg_nrst, 1)    # reset high
        time.sleep(0.1)

        # call the bootloader script
        loader = Stm32Loader()
        loader.configuration['family'] = 'L4'
        loader.configuration['data_file'] = imagefile
        loader.configuration['port'] = port
        loader.configuration['baud'] = 115200
        loader.configuration['parity'] = serial.PARITY_EVEN
        loader.configuration['erase'] = True
        loader.configuration['write'] = True
        loader.configuration['verify'] = True
        loader.configuration['hide_progress_bar'] = True
        if debug:
            loader.verbosity = 10
        else:
            loader.verbosity = 0
        loader.connect()
        loader.read_device_id()
        if loader.stm32.get_id() != 0x435:
            return flocklab.FAILED
        try:
            loader.perform_commands()
            break
        except:
            if tries <= 1:
                raise
            else:
                flocklab.log_debug("Failed, trying again...")
        tries = tries - 1

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
        flocklab.logger.debug("Programming CC430...")
        ret = prog_msp430(imagefile, flocklab.tg_serial_port, 115200)
    elif core == 1: # BOLT
        flocklab.logger.debug("Programming BOLT...")
        ret = prog_msp430(imagefile, flocklab.tg_serial_port, 115200)
    elif core == 2: # APP
        flocklab.logger.debug("Programming MSP432...")
        # cannot go higher than 57600 due to a bug in the on-chip bootloader
        ret = prog_msp432(imagefile, flocklab.tg_serial_port, 57600)
    elif core == 3: # SENSOR
        flocklab.logger.debug("Programming sensor...")
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
def prog_swd(imagefile, device, speed='auto'):
    # JLinkExe expects Intel hex file format
    if "hex" not in os.path.splitext(imagefile)[1]:
        ret = os.system("objcopy -O ihex %s %s.hex" % (imagefile, imagefile))
        if ret != 0:
            flocklab.log_warning("Failed to convert file '%s' to Intel hex format." % imagefile)
        else:
            flocklab.log_debug("File '%s' converted to Intel hex format." % imagefile)
            imagefile = imagefile + ".hex"
    # note: file ending must be .hex, JLink doesn't recognize .ihex
    if "ihex" in os.path.splitext(imagefile)[1]:
        os.rename(imagefile, os.path.splitext(imagefile)[0] + ".hex")
        imagefile = os.path.splitext(imagefile)[0] + ".hex"
    # flash to target
    # note: JRunExe expects an ELF file and needs to be aborted (does not terminate automatically)
    #cmd = ['JRunExe', '-device', device, '-if', 'SWD', '-speed', str(speed), '--quit', imagefile]
    #p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    cmd = ['JLinkExe', '-device', device, '-if', 'SWD', '-speed', str(speed), '-autoconnect', '1']
    jlinkcmd = 'r\nerase\nloadfile %s\nr\nq\n' % imagefile
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    out, err = p.communicate(input=jlinkcmd)
    if "Core found" not in out:
        flocklab.log_error("Failed to connect to target via SWD. JLink output: %s" % out)
        return flocklab.FAILED
    #if out.find("Programming flash [100%] Done") < 0:
    if out.find("Verifying flash") < 0:
        dbg_pos = out.find("Cortex-M4 identified")
        if dbg_pos < 0:
             dbg_pos = 0
        flocklab.log_error("Failed to program target via SWD. JLink output:\n%s" % out[dbg_pos:])
        return flocklab.FAILED
    if debug:
        flocklab.log_debug(out)
    return flocklab.SUCCESS
### END prog_swd()


##############################################################################
#
# Main
#
##############################################################################
def main(argv):
    global debug

    porttype  = None
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
    imagefile = os.path.abspath(imagefile)
    if not os.path.isfile(imagefile):
        flocklab.error_logandexit("Image file '%s' not found." % imagefile, errno.ENOENT)

    # Set target voltage to default value and make sure power, MUX and actuation are enabled
    flocklab.tg_set_vcc(3.3)
    flocklab.log_debug("Target voltage set to 3.3V.")

    flocklab.tg_on()
    flocklab.tg_reset()
    time.sleep(1)

    # Flash the target:
    logger.info("Programming target %s with image %s..." % (target, imagefile))
    rs = flocklab.FAILED
    if target == 'dpp':
        rs = prog_dpp(imagefile, core)
    elif target in ('dpp2lora', 'dpp2lorahg'):
        if porttype in ("BSL", "bsl", "serial"):
            try:
                rs = prog_stm32l4(imagefile, flocklab.tg_serial_port)
            except:     # use except here to also catch sys.exit()
                rs = 1
        else:
            rs = prog_swd(imagefile, "STM32L433CC")
            # power cycle to make sure the debug circuit is disabled
            flocklab.tg_pwr_en(False)
            time.sleep(1)
            flocklab.tg_pwr_en(True)
    elif target == 'nrf5':
        rs = prog_swd(imagefile, "nRF52840_xxAA")
    elif target in ('tmote', 'telosb', 'sky'):
        rs = prog_telosb(imagefile)
        if rs == flocklab.FAILED:
            logger.info("Resetting USB hub and power cycling target...")
            flocklab.tg_off()
            time.sleep(0.1)
            flocklab.tg_on()
            time.sleep(0.1)
            # try to reset the USB hub and try again
            if flocklab.usb_reset() != flocklab.SUCCESS:
                logger.error("Failed to reset USB hub.");
            time.sleep(1)
            rs = prog_telosb(imagefile)
    else:
        logger.error("Unknown target '%s'" % target)

    # Revert back all config changes:
    #subprocess.call(["stty", "-F", port, "-parenb", "iexten", "echoe", "echok", "echoctl", "echoke", "115200"])

    # Reset
    flocklab.tg_reset()

    # Return an error if there was one while flashing:
    if (rs != flocklab.SUCCESS):
        flocklab.error_logandexit("Image could not be flashed to target. Error %d occurred." % rs, errno.EIO)

    logger.info("Target node flashed successfully.")
    sys.exit(flocklab.SUCCESS)
### END main()


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except Exception:
        flocklab.error_logandexit("Encountered error: %s\n%s\nCommandline was: %s" % (str(sys.exc_info()[1]), traceback.format_exc(), str(sys.argv)))
