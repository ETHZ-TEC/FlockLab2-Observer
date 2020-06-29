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

import os, sys, getopt, signal, socket, time, subprocess, errno, queue, serial, select, multiprocessing, threading, traceback, struct
import lib.daemon as daemon
import lib.flocklab as flocklab
import lib.dwt as dwt


pidfile   = None
prescaler = 16     # prescaler for local timestamps
loopdelay = 10     # SWO read loop delay in ms (recommended values: 10 - 100ms)


##############################################################################
#
# Usage
#
##############################################################################
def usage():
    print("Usage: %s --output --platform [--stop] [--config] [--speed] [--help]" % sys.argv[0])
    print("Options:")
    print("  --output=<string>\t\toutput filename")
    print("  --platform=<string>\t\tplatform name (e.g. dpp2lora or nrf5)")
    print("  --config=<string>\t\tDWT configuration, up to 4 comma separated value pairs of variable address and mode.")
    print("  --stop\t\t\tOptional. Causes the program to stop a possibly running instance of the serial reader service.")
    print("  --speed\t\t\tOptional. The CPU clock frequency of the target device.")
    print("  --help\t\t\tOptional. Print this help.")
### END usage()


##############################################################################
#
# sigterm_handler
#
##############################################################################
def sigterm_handler(signum, frame):
    dwt.stop_swo_read()
### END sigterm_handler()


##############################################################################
#
# stop_on_api
#
##############################################################################
def stop_daemon():
    logger = flocklab.get_logger()
    # try to get pid from file first
    pid = None
    try:
        pid = int(open(pidfile, 'r').read())
    except:
        pass
    if not pid:
        # take the first PID that isn't our PID
        pids = flocklab.get_pids('flocklab_datatrace')
        for p in pids:
            if p != os.getpid():
                pid = p
                break
    if pid:
        logger.debug("Sending SIGTERM signal to process %d" % pid)
        try:
            os.kill(pid, signal.SIGTERM)
            os.waitpid(pid, 0)
        except OSError:
            # process probably didn't exist -> ignore error
            logger.debug("Process %d does not exist" % pid)
            # delete the PID file
            os.remove(pidfile)
    else:
        logger.info("No daemon process found.")
    return flocklab.SUCCESS
### END stop_on_api()


##############################################################################
#
# Main
#
##############################################################################
def main(argv):
    global pidfile

    stop     = False
    filename = None
    platform = None
    dwtconf  = None
    reset    = False
    cpuspeed = 48000000 #None
    swospeed = 4000000

    # Get config:
    config = flocklab.get_config()
    if not config:
        flocklab.error_logandexit("Could not read configuration file.")

    # Get command line parameters.
    try:
        opts, args = getopt.getopt(argv, "sho:p:c:s:", ["stop", "help", "output=", "platform=", "config=", "speed="])
    except(getopt.GetoptError) as err:
        flocklab.error_logandexit(str(err), errno.EINVAL)
    for opt, arg in opts:
        if opt in ("-h", "--help"):
            usage()
            sys.exit(flocklab.SUCCESS)
        elif opt in ("-e", "--stop"):
            stop = True
        elif opt in ("-o", "--output"):
            filename = arg
        elif opt in ("-p", "--platform"):
            platform = arg
        elif opt in ("-c", "--config"):
            dwtconf = arg
        elif opt in ("-s", "--speed"):
            try:
                cpuspeed = int(arg)
                if cpuspeed < 1000000:    # must be at least 1 MHz
                    cpuspeed = None
            except:
                pass
        else:
            flocklab.error_logandexit("Unknown option '%s'." % (opt), errno.EINVAL)

    # Check mandatory parameters:
    if not stop:
        if not filename or not platform:
            flocklab.error_logandexit("No output file or platform specified.", errno.EINVAL)

    pidfile = "%s/flocklab_datatrace.pid" % (config.get("observer", "pidfolder"))

    if stop:
        sys.exit(stop_daemon())

    if len(flocklab.get_pids('flocklab_datatrace')) > 1:
        flocklab.error_logandexit("There is already an instance of %s running." % sys.argv[0])

    # init logger AFTER daemonizing the process
    logger = flocklab.get_logger()
    if not logger:
        flocklab.error_logandexit("Could not get logger.")

    # make sure the mux is enabled
    flocklab.tg_mux_en(True)

    if swospeed > cpuspeed:
        swospeed = cpuspeed

    # DWT config provided?
    # Note: configure service before daemonizing the process
    if dwtconf:
        try:
            # make sure target is released from reset state before configuring data trace
            if flocklab.gpio_get(flocklab.gpio_tg_nrst) == 0:
                flocklab.tg_reset()
                reset = True
            # parse
            dwtvalues = []
            values = dwtconf.split(',')
            prevval = None
            for val in values:
                if "0x" in val:
                    # variable address
                    if prevval:
                        dwtvalues.append([int(prevval, 0), 'w', False])    # use default mode
                    prevval = val
                elif prevval:
                    # mode definition (a variable address must precede it)
                    mode    = val.lower()
                    trackpc = False
                    if 'pc' in mode:
                        trackpc = True
                    if 'rw' in mode:
                        mode = 'rw'
                    elif 'r' in mode:
                        mode = 'r'
                    else:
                        mode = 'w'    # default mode
                    dwtvalues.append([int(prevval, 0), mode, trackpc])
                    prevval = None
            # config valid?
            if len(dwtvalues) > 0:
                for elem in dwtvalues:
                    logger.info("Config found: addr=0x%x, mode=%s, pc=%s" % (elem[0], elem[1], str(elem[2])))
                # fill up the unused variables with zeros
                while len(dwtvalues) < 4:
                    dwtvalues.append([None, None, None])
                # apply config
                logger.info("Configuring data trace service for MCU %s with prescaler %d..." % (flocklab.jlink_mcu_str(platform), prescaler))
                dwt.config_dwt_for_data_trace(device_name=flocklab.jlink_mcu_str(platform), ts_prescaler=prescaler,
                                              trace_address0=dwtvalues[0][0], access_mode0=dwtvalues[0][1], trace_pc0=dwtvalues[0][2],
                                              trace_address1=dwtvalues[1][0], access_mode1=dwtvalues[1][1], trace_pc1=dwtvalues[1][2],
                                              trace_address2=dwtvalues[2][0], access_mode2=dwtvalues[2][1], trace_pc2=dwtvalues[2][2],
                                              trace_address3=dwtvalues[3][0], access_mode3=dwtvalues[3][1], trace_pc3=dwtvalues[3][2],
                                              swo_speed=swospeed, cpu_speed=cpuspeed)
        except:
            flocklab.error_logandexit("Failed to configure data trace service (%s).\n%s" % (str(sys.exc_info()[1]), traceback.format_exc()))

    if reset:
        flocklab.tg_reset(False)

    logger.info("Starting SWO read... (output file: %s, CPU speed: %s, SWO speed: %s)." % (filename, str(cpuspeed), str(swospeed)))

    # run process in background
    daemon.daemonize(pidfile=pidfile, closedesc=True)

    # note: 'logger' is not valid anymore at this point

    # register signal handlers
    signal.signal(signal.SIGTERM, sigterm_handler)
    signal.signal(signal.SIGINT, sigterm_handler)

    # Start SWO read
    dwt.read_swo_buffer(device_name=flocklab.jlink_mcu_str(platform), loop_delay_in_ms=loopdelay, filename=filename, swo_speed=swospeed, cpu_speed=cpuspeed)

    # Remove PID file
    if os.path.isfile(pidfile):
        os.remove(pidfile)

    sys.exit(flocklab.SUCCESS)
### END main()


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except Exception:
        flocklab.error_logandexit("Encountered error: %s\n%s\nCommand line was: %s" % (str(sys.exc_info()[1]), traceback.format_exc(), " ".join(sys.argv)))
        sys.exit(flocklab.FAILED)
