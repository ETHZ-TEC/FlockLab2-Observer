#! /usr/bin/env python3

import os, sys, getopt, signal, socket, time, subprocess, errno, queue, serial, select, multiprocessing, threading, traceback, struct
import lib.daemon as daemon
import lib.flocklab as flocklab
import lib.dwt as dwt


pidfile  = None


##############################################################################
#
# Usage
#
##############################################################################
def usage():
    print("Usage: %s --output --platform [--stop] [--config] [--help]" % sys.argv[0])
    print("Options:")
    print("  --output=<string>\t\toutput filename")
    print("  --platform=<string>\t\tplatform name (e.g. dpp2lora or nrf5)")
    print("  --config=<string>\t\tDWT configuration, up to 4 comma separated value pairs of variable address and mode.")
    print("  --stop\t\t\tOptional. Causes the program to stop a possibly running instance of the serial reader service.")
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
        logger.info("Sending SIGTERM signal to process %d" % pid)
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            return flocklab.FAILED
        try:
            os.waitpid(pid, 0)
        except OSError:
            pass
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

    # Get config:
    config = flocklab.get_config()
    if not config:
        flocklab.error_logandexit("Could not read configuration file.")

    # Get command line parameters.
    try:
        opts, args = getopt.getopt(argv, "sho:p:c:", ["stop", "help", "output=", "platform=", "config="])
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

    daemon.daemonize(pidfile=pidfile, closedesc=True)

    # init logger AFTER daemonizing the process
    logger = flocklab.get_logger()
    if not logger:
        flocklab.error_logandexit("Could not get logger.")

    # register signal handlers
    signal.signal(signal.SIGTERM, sigterm_handler)
    signal.signal(signal.SIGINT, sigterm_handler)

    # DWT config provided?
    if dwtconf:
        # parse
        dwtvalues = []
        values = dwtconf.split(',')
        prevval = None
        for val in values:
            if "0x" in val:
                # variable address
                if prevval:
                    dwtvalues.append([prevval, 'w', False])    # use default mode
                prevval = val
            elif prevval:
                # mode definition (a variable address must precede it)
                mode    = val.lower()
                trackpc = False
                if mode in 'pc':
                    trackpc = True
                    mode = 'rw'
                elif mode not in ('r', 'w', 'rw'):
                    mode = 'w'    # default value
                dwtvalues.append([int(prevval, 0), mode, trackpc])
        # config valid?
        if len(dwtvalues) > 0:
            for elem in dwtvalues:
                logger.info("Config found: addr=0x%x, mode=%s" % (elem[0], elem[1]))
            # fill up the unused variables with zeros
            while len(dwtvalues) < 4:
                dwtvalues.append([None, None, None])
            # apply config
            logger.info("Configuring data trace service for MCU %s..." % (flocklab.jlink_mcu_str(platform)))
            dwt.config_dwt_for_data_trace(device_name=flocklab.jlink_mcu_str(platform), ts_prescaler=64,
                                          trace_address0=dwtvalues[0][0], access_mode0=dwtvalues[0][1], trace_pc0=dwtvalues[0][2],
                                          trace_address1=dwtvalues[1][0], access_mode1=dwtvalues[1][1], trace_pc1=dwtvalues[1][2],
                                          trace_address2=dwtvalues[2][0], access_mode2=dwtvalues[2][1], trace_pc2=dwtvalues[2][2],
                                          trace_address3=dwtvalues[3][0], access_mode3=dwtvalues[3][1], trace_pc3=dwtvalues[3][2])

    logger.info("Starting SWO read... (output file: %s)." % filename)

    # Start SWO read
    dwt.read_swo_buffer(device_name=flocklab.jlink_mcu_str(platform), loop_delay_in_ms=2, filename=filename)

    sys.exit(flocklab.SUCCESS)
### END main()


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except Exception:
        flocklab.error_logandexit("Encountered error: %s\n%s\nCommandline was: %s" % (str(sys.exc_info()[1]), traceback.format_exc(), str(sys.argv)))