#! /usr/bin/env python3

"""
Copyright (c) 2020 - 2022, ETH Zurich, Computer Engineering Group
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

import os, sys, subprocess, getopt, errno, tempfile, time, shutil, serial, xml.etree.ElementTree, traceback
import lib.flocklab as flocklab


stopallservices = False          # whether to stop all services before starting a test


##############################################################################
#
# Usage
#
##############################################################################
def usage():
    print("Usage: %s --testid=<testid> --xml=<path> [--debug]" % __file__)
    print("Start a FlockLab test which is defined in the provided XMl.")
    print("Options:")
    print("  --testid=<testid>\tID of the test.")
    print("  --xml=<path>\t\tPath to the XML file with the testconfiguration.")
    print("  --serialport=<port>\tPort for the serial forwarder.")
    print("  --debug\t\tOptional. Print debug messages to log.")
    print("  --help\t\tOptional. Print this help.")
### END usage()


##############################################################################
#
# Main
#
##############################################################################
def main(argv):

    xmlfile    = None
    testid     = None
    socketport = None
    debug      = False

    # Get config:
    config = flocklab.get_config()
    if not config:
        flocklab.error_logandexit("Could not read configuration file.")

    # Get command line parameters.
    try:
        opts, args = getopt.getopt(argv, "hdt:x:p:", ["help", "debug", "testid=", "xml=", "serialport="])
    except (getopt.GetoptError) as err:
        flocklab.error_logandexit(str(err), errno.EINVAL)
    except:
        flocklab.error_logandexit("Error: %s: %s" % (str(sys.exc_info()[0]), str(sys.exc_info()[1])), errno.EINVAL)
    for opt, arg in opts:
        if opt in ("-t", "--testid"):
            testid = int(arg)
        elif opt in ("-x", "--xml"):
            xmlfile = arg
            if not (os.path.exists(xmlfile)):
                flocklab.error_logandexit("Error: file %s does not exist" % (str(xmlfile)), errno.EINVAL)
        elif opt in ("-p", "--serialport"):
            socketport = int(arg)     # socket port used for the serial output
        elif opt in ("-h", "--help"):
            usage()
            sys.exit(flocklab.SUCCESS)
        elif opt in ("-d", "--debug"):
            debug = True
        else:
            flocklab.error_logandexit("Invalid option '%s'." % (opt), errno.EINVAL)

    # Check for mandatory arguments:
    if not xmlfile or not testid:
        flocklab.error_logandexit("Test ID and/or XML config missing.", errno.EINVAL)

    # init logger
    logger = flocklab.get_logger(debug=debug)
    if not logger:
        flocklab.error_logandexit("Could not get logger.")

    # Indicate start of the script by enabling status LED
    flocklab.gpio_set(flocklab.gpio_led_status)

    logger.debug("Preparing test %d..." % testid)

    # Rename XML ---
    if os.path.basename(xmlfile) != "config.xml":
        try:
            os.rename(xmlfile, "%s/config.xml" % os.path.dirname(xmlfile))
            xmlfile = "%s/config.xml" % os.path.dirname(xmlfile)
        except (OSError) as err:
            flocklab.error_logandexit("Could not rename XML config file.")

    # Process XML ---
    # Open and parse XML:
    try:
        tree = xml.etree.ElementTree.ElementTree()
        tree.parse(xmlfile)
        logger.debug("Parsed XML.")
        #logger.debug("XML config:\n%s" % (xml.etree.ElementTree.tostring(tree.getroot(), encoding='utf8', method='xml').decode()))
    except:
        flocklab.error_logandexit("Could not find or open XML file '%s'." % str(xmlfile))

    # Get basic information from <obsTargetConf> ---
    voltage             = None
    imagefile           = None
    slotnr              = None
    platform            = None
    serialport          = None
    noimage             = False
    actuationused       = False
    resetactuationused  = True
    abortonerror        = False
    ptpsynced           = False
    tracingserviceused  = tree.find('obsGpioMonitorConf') != None
    debugserviceused    = tree.find('obsDebugConf') != None
    powerprofilingused  = tree.find('obsPowerprofConf') != None
    teststarttime       = 0

    if flocklab.get_timesync_method() == "PTP":
        ptpsynced = True

    imagefiles_to_process = tree.findall('obsTargetConf/image')
    imagefile = {}
    for img in imagefiles_to_process:
        imagefile[int(img.get('core'))] = img.text
    if len(imagefiles_to_process) == 0:
        logger.debug("Test without image")
        noimage = True

    try:
        voltage = float(tree.find('obsTargetConf/voltage').text)
        # limit the voltage to the allowed range
        if voltage < flocklab.tg_vcc_min:
            voltage = flocklab.tg_vcc_min
        elif voltage > flocklab.tg_vcc_max:
            voltage = flocklab.tg_vcc_max
        slotnr = int(tree.find('obsTargetConf/slotnr').text)
        if not noimage:
            platform = tree.find('obsTargetConf/platform').text.lower()
        if (tree.find('obsTargetConf/abortOnError') != None) and (tree.find('obsTargetConf/abortOnError').text.lower() == 'yes'):
            abortonerror = True
        # find out whether serial logging is used and if so on which port
        if tree.find('obsSerialConf') != None:
            serialport = tree.findtext('obsSerialConf/port')
            # if not specified, use the default port for this platform
            if serialport:
                serialport = serialport.lower()
            else:
                serialport = flocklab.get_default_serialport(platform)
    except:
        flocklab.error_logandexit("XML: could not find mandatory element(s) in element <obsTargetConf>")

    # Activate interface, turn power on ---
    if slotnr:
        if flocklab.tg_select(slotnr) != flocklab.SUCCESS:
            flocklab.error_logandexit("Failed to select target %d!" % (slotnr))
        logger.debug("Target %d selected." % (slotnr))
    else:
        flocklab.error_logandexit("Slot number could not be determined.")

    # Make sure all services are stopped ---
    if stopallservices:
        flocklab.stop_serial_service()
        flocklab.stop_serial_logging()
        flocklab.stop_swo_logger()
        flocklab.stop_gpio_actuation()
        flocklab.stop_gpio_tracing()
        flocklab.stop_pwr_measurement()
        flocklab.stop_gdb_server()
        flocklab.stop_data_trace()

    # Delete old logs
    if os.path.isfile(flocklab.rllog):
        os.remove(flocklab.rllog)
    if os.path.isfile(flocklab.tracinglog):
        os.remove(flocklab.tracinglog)

    # Enable MUX and power
    flocklab.tg_off()
    time.sleep(0.1)
    flocklab.tg_on()

    # Pull down GPIO setting lines ---
    if flocklab.gpio_clr(flocklab.gpio_tg_sig1) != flocklab.SUCCESS or flocklab.gpio_clr(flocklab.gpio_tg_sig2) != flocklab.SUCCESS:
        flocklab.tg_off()
        flocklab.error_logandexit("Failed to set GPIO lines")

    # Flash target (will set target voltage to 3.3V) ---
    if not noimage:
        for core, image in imagefile.items():
            if platform not in flocklab.tg_platforms:
                flocklab.tg_off()
                flocklab.error_logandexit("Unknown platform %s. Not known how to program this platform." % platform)
            logger.debug("Going to flash image to platform %s (core %d)..." % (platform, core))
            if flocklab.program_target(image, platform, core) != flocklab.SUCCESS:
                flocklab.tg_off()
                flocklab.error_logandexit("An error occurred while programming the target image.")
            logger.debug("Programmed target with image %s." % (image))

    # Hold target in reset state
    flocklab.tg_reset(release=False)

    # Set voltage ---
    if flocklab.tg_set_vcc(voltage) != flocklab.SUCCESS:
        flocklab.tg_off()
        flocklab.error_logandexit("Failed to set target voltage to %.1fV." % (voltage))
    logger.debug("Target voltage set to %.1fV." % voltage)

    # Create test results directory ---
    resfolder = "%s/%d" % (config.get("observer", "testresultfolder"), testid)
    try:
        os.makedirs(resfolder)
    except Exception as e:
        flocklab.tg_off()
        flocklab.error_logandexit("Failed to create directory: %s" % str(e))
    logger.debug("Test results folder '%s' created." % resfolder)

    # Configure needed services ---

    # GPIO actuation (do this first to determine test start and stop time) ---
    flocklab.tg_act_en()  # make sure actuation is enabled
    if (tree.find('obsGpioSettingConf') != None):
        logger.debug("Found config for GPIO actuation.")
        subtree    = tree.find('obsGpioSettingConf')
        pinconfs   = list(subtree.getiterator("pinConf"))
        resets     = []
        act_events = []
        for pinconf in pinconfs:
            pin = pinconf.find('pin').text
            if pin == 'RST':
                # reset pin comes with absolute timestamps and determine the test start / stop
                resets.append(pinconf.find('timestamp').text)
                continue
            actuationused = True
            if pin == 'nRST':   # target reset actuation during the test
                resetactuationused = True
            cmd = flocklab.level_str2abbr(pinconf.find('level').text, pin)
            microsecs = int(flocklab.parse_float(pinconf.find('offset').text) * 1000000)
            if pinconf.findtext('period'):
                count = flocklab.parse_int(pinconf.findtext('count'))
                periodic_evts = flocklab.generate_periodic_act_events(pin, flocklab.parse_float(pinconf.find('offset').text), float(pinconf.findtext('period')), 0.5, count)
                if periodic_evts:
                    act_events.extend(periodic_evts)
            else:
                act_events.append([cmd, microsecs])
        # determine test start
        try:
            teststarttime = flocklab.parse_int(resets[0])   # 1st reset actuation is the reset release = start of test
            teststoptime  = flocklab.parse_int(resets[-1])  # last reset actuation is the test stop time
            # note: in case the tracing service is used, it will override the reset actuation with more precise actuation
            if (not abortonerror) or (not tracingserviceused) or resetactuationused:
                act_events.append(['R', 0])                                                            # reset high at offset 0
                act_events.append(['r', flocklab.parse_int((teststoptime - teststarttime) * 1000000)]) # reset low at end of test
            logger.debug("Test will run from %u to %u." % (teststarttime, teststoptime))
        except:
            flocklab.tg_off()
            flocklab.error_logandexit("Could not determine test start time (%s)." % str(sys.exc_info()[1]))
        # generate PPS pulses on observers with PTP time synchronization (required for GPIO tracing only)
        if ptpsynced and tracingserviceused:
            actuationused = True
            num_pulses    = flocklab.parse_int((teststoptime - teststarttime - 60) / 60) + 1
            # 2 pulses at the beginning and 2 at the end, plus one every 60 seconds (note that less pulses reduces the probability of a high shift)
            testendmicrosecs = (teststoptime - teststarttime) * 1000000
            act_events.append(['P',       0])
            act_events.append(['p',  100000])
            act_events.append(['P', testendmicrosecs +  999950])
            act_events.append(['p', testendmicrosecs + 1100000])
            act_events.append(['P', testendmicrosecs + 1999950])
            act_events.append(['p', testendmicrosecs + 2100000])
            periodic_evts = flocklab.generate_periodic_act_events('PPS', 0.999950, 60.0, 0.001, num_pulses)   # add slack time: schedule wakeups 50us before the full second
            num_pulses = num_pulses + 3
            if periodic_evts:
                act_events.extend(periodic_evts)
                logger.debug("%d PPS pulses will be generated during the test." % num_pulses)
            else:
                msg = "Failed to schedule PPS pulse generation (required for GPIO tracing on a PTP-synced observer)."
                if abortonerror:
                    flocklab.tg_off()
                    flocklab.error_logandexit(msg)
                else:
                    logger.error(msg)
                    flocklab.log_test_error(testid, msg)
        # if there are no scheduled pin actuations and neither debugging nor the serial proxy is used, then disable actuation during the test
        if (not actuationused) and (socketport == None) and (not debugserviceused):
            act_events.append(['A', 10001000])    # 10.001s after startup -> latest point where target will be released from reset state
            act_events.append(['a', flocklab.parse_int((teststoptime - teststarttime) * 1000000) - 1000])    # reactivate actuation just before the end of the test (when the reset pin needs to be pulled low)
            actuationused = True
            logger.debug("Actuation will be disabled during the test.")
        # any actuations scheduled?
        if actuationused or len(act_events) > 0:
            if flocklab.start_gpio_actuation(teststarttime, act_events) != flocklab.SUCCESS:
                msg = "Failed to start GPIO actuation service."
                if abortonerror or not tracingserviceused:
                    flocklab.tg_off()
                    flocklab.error_logandexit(msg)
                else:
                    flocklab.log_test_error(testid, msg)
            logger.debug("GPIO actuation service configured (%u actuations scheduled)." % len(act_events))
        else:
            logger.debug("No GPIO actuations scheduled.")
    else:
        flocklab.tg_off()
        flocklab.error_logandexit("No config for GPIO setting service found. Can't determine test start or stop time.")

    # Make sure the test start time is in the future ---
    if int(time.time()) > teststarttime:
        flocklab.tg_off()
        flocklab.error_logandexit("Test start time %d is in the past." % (teststarttime))

    # Debug ---
    if debugserviceused:
        logger.debug("Found config for debug service.")
        remoteIp = "0.0.0.0"
        if tree.find('obsDebugConf/remoteIp') != None:
            remoteIp = tree.findtext('obsDebugConf/remoteIp')
        cpuSpeed = None
        if tree.find('obsDebugConf/cpuSpeed') != None:
            cpuSpeed = flocklab.parse_int(tree.findtext('obsDebugConf/cpuSpeed'))
        port = 0
        if tree.find('obsDebugConf/gdbPort') != None:
            port = int(tree.findtext('obsDebugConf/gdbPort'))
        prescaler = None
        if tree.find('obsDebugConf/prescaler') != None:
            prescaler = int(tree.findtext('obsDebugConf/prescaler'))
        loopdelay = None
        if tree.find('obsDebugConf/loopDelay') != None:
            loopdelay = int(tree.findtext('obsDebugConf/loopDelay'))
        # make sure mux is enabled
        flocklab.tg_mux_en(True)
        # data trace config
        dwtconfs = list(tree.find('obsDebugConf').getiterator('dataTraceConf'))
        if dwtconfs:
            logger.debug("Config for data trace service found.")
            dwtvalues = []
            varnames  = []
            for dwtconf in dwtconfs:
                dwtvalues.append(dwtconf.findtext('variable'))
                varnames.append(dwtconf.findtext('varName'))
                dwtvalues.append(dwtconf.findtext('mode'))
                dwtvalues.append(dwtconf.findtext('size'))
                logger.debug("Found data trace config: addr=%s, mode=%s." % (dwtconf.findtext('variable'), dwtconf.findtext('mode')))
            datatracefile = "%s/%d/datatrace_%s.log" % (config.get("observer", "testresultfolder"), testid, time.strftime("%Y%m%d%H%M%S", time.gmtime()))
            # write the variable names as the first line into the file
            with open(datatracefile, "w") as f:
                f.write("%s " % (" ".join(varnames)))
                f.flush()
            if flocklab.start_data_trace(platform, ','.join(dwtvalues), datatracefile, cpuSpeed, prescaler, loopdelay) != flocklab.SUCCESS:
                msg = "Failed to start data tracing service."
                if abortonerror:
                    flocklab.tg_off()
                    flocklab.error_logandexit(msg)
                else:
                    flocklab.log_test_error(testid, msg)
        elif port > 0:
            # start GDB server 10s after test start
            if flocklab.start_gdb_server(platform, port, int(teststarttime - time.time() + 10)) != flocklab.SUCCESS:
                msg = "Failed to start debug service."
                if abortonerror:
                    flocklab.tg_off()
                    flocklab.error_logandexit(msg)
                else:
                    flocklab.log_test_error(testid, msg)
            else:
                logger.debug("GDB server will be listening on port %d." % port)
        else:
          logger.warn("Incomplete debug service config.")
    else:
        logger.debug("No config for debug service found.")
        # disable MUX for more accurate current measurements only if serial port is not USB
        if serialport != "usb":
            flocklab.tg_mux_en(False)
            logger.debug("Disabling MUX.")

    # Serial (must be started after the debug service) ---
    if tree.find('obsSerialConf') != None:
        logger.debug("Found config for serial service.")
        baudrate = tree.findtext('obsSerialConf/baudrate')
        # note: serialport has already been extracted further up
        serialfile = "%s/%d/serial_%s.csv" % (config.get("observer", "testresultfolder"), testid, time.strftime("%Y%m%d%H%M%S", time.gmtime()))
        if "swo" in serialport:
            # logging via SWO pin
            cpuspeed = tree.findtext('obsSerialConf/cpuSpeed')
            # MUX must be enabled and target released from reset state
            flocklab.tg_mux_en(True)
            flocklab.tg_reset()
            if flocklab.start_swo_logger(platform, serialfile, cpuspeed, None, True) != flocklab.SUCCESS:
                msg = "Failed to start SWO serial logger."
                if abortonerror:
                    flocklab.tg_off()
                    flocklab.error_logandexit(msg)
                else:
                    flocklab.log_test_error(testid, msg)
            # wait some time to let the services start up, then put the target back into reset state
            time.sleep(5)
            flocklab.tg_reset(False)
        elif not socketport and serialport != "usb":    # note: serial logger seems to have issues with the tmote (USB connection)
            # serial forwarder (proxy) not used -> logging only (use the faster C implementation)
            if flocklab.start_serial_logging(serialport, baudrate, serialfile, teststarttime, teststoptime - teststarttime) != flocklab.SUCCESS:
                msg = "Failed to start serial logging service."
                if abortonerror:
                    flocklab.tg_off()
                    flocklab.error_logandexit(msg)
                else:
                    flocklab.log_test_error(testid, msg)
        else:
            outputdir = "%s/%d" % (config.get("observer", "testresultfolder"), testid)
            if flocklab.start_serial_service(serialport, baudrate, socketport, outputdir, debug) != flocklab.SUCCESS:
                msg = "Failed to start serial service."
                if abortonerror:
                    flocklab.tg_off()
                    flocklab.error_logandexit(msg)
                else:
                    flocklab.log_test_error(testid, msg)
        logger.debug("Started and configured serial service.")

    # GPIO tracing (must be started after the serial and debug service) ---
    if tracingserviceused:
        logger.debug("Found config for GPIO monitoring.")
        # move the old log file
        if os.path.isfile(flocklab.tracinglog):
            os.replace(flocklab.tracinglog, flocklab.tracinglog + ".old")
        subtree = tree.find('obsGpioMonitorConf')
        pins = 0x0
        pinlist = subtree.findtext("pins")
        if pinlist:
            for pin in pinlist.strip().split():
                pins = pins | flocklab.pin_abbr2num(pin)
        offset = subtree.findtext("offset")
        if offset:
            offset = flocklab.parse_int(offset)
        else:
            offset = 1  # default offset of 1 second to avoid tracing of the erratic toggling at MCU startup
        # if GPIO actuation service is used, then also trace the SIG pins
        if actuationused:
            pins = pins | flocklab.pin_abbr2num("SIG1") | flocklab.pin_abbr2num("SIG2")
            logger.debug("Going to trace SIG pins...")
        tracingfile = "%s/%d/gpio_monitor_%s" % (config.get("observer", "testresultfolder"), testid, time.strftime("%Y%m%d%H%M%S", time.gmtime()))
        extra_options = 0x00000000      # extra options (flags) for the gpio tracing service (see fl_logic.c for details)
        if not powerprofilingused:
            extra_options = extra_options | 0x00000040    # use PRU0 to assist with GPIO tracing
        if resetactuationused:
            extra_options = extra_options | 0x00000002    # do not control the reset pin with the PRU
            logger.debug("Target reset actuations scheduled, won't control reset pin with PRU.")
        if flocklab.start_gpio_tracing(tracingfile, teststarttime, teststoptime, pins, offset, extra_options) != flocklab.SUCCESS:
            msg = "Failed to start GPIO tracing service."
            if abortonerror:
                flocklab.tg_off()
                flocklab.error_logandexit(msg)
            else:
                flocklab.log_test_error(testid, msg)
        # touch the file
        open(tracingfile + ".csv", 'a').close()
        logger.debug("Started GPIO tracing (output file: %s, pins: 0x%x, offset: %u, options: 0x%x)." % (tracingfile, pins, offset, extra_options))

    # Power profiling ---
    if powerprofilingused:
        logger.debug("Found config for power profiling.")
        # move the old log file
        if os.path.isfile(flocklab.rllog):
            os.replace(flocklab.rllog, flocklab.rllog + ".old")
        # Cycle through all powerprof configs and insert them into file:
        duration = flocklab.parse_int(tree.findtext('obsPowerprofConf/duration'))
        # Get time and bring it into right format:
        starttime = flocklab.parse_int(tree.findtext('obsPowerprofConf/starttime'))
        samplingrate = flocklab.parse_int(tree.findtext('obsPowerprofConf/samplingRate'))
        if samplingrate == 0:
            samplingrate = flocklab.rl_default_rate
        # Start profiling
        outputfile = "%s/%d/powerprofiling_%s.rld" % (config.get("observer", "testresultfolder"), testid, time.strftime("%Y%m%d%H%M%S", time.gmtime()))
        if flocklab.start_pwr_measurement(out_file=outputfile, sampling_rate=samplingrate, start_time=starttime, num_samples=int((duration + 1) * samplingrate)) != flocklab.SUCCESS:
            msg = "Failed to start power measurement."
            if abortonerror:
                flocklab.tg_off()
                flocklab.error_logandexit(msg)
            else:
                flocklab.log_test_error(testid, msg)
        logger.debug("Power measurement will start at %s (output: %s, sampling rate: %dHz, duration: %ds)." % (str(starttime), outputfile, samplingrate, duration))

    # Timesync log ---
    try:
        flocklab.log_timesync_info(testid=testid)
        flocklab.store_pps_count(testid)
    except:
        msg = "Failed to collect timesync info (%s, %s)." % (str(sys.exc_info()[0]), str(sys.exc_info()[1]))
        if abortonerror:
            flocklab.tg_off()
            flocklab.error_logandexit(msg)
        else:
            flocklab.log_test_error(testid, msg)

    flocklab.gpio_clr(flocklab.gpio_led_error)
    logger.info("Test %d successfully started." % testid)

    sys.exit(flocklab.SUCCESS)
### END main()


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except Exception:
        flocklab.error_logandexit("Encountered error: %s\n%s\nCommandline was: %s" % (str(sys.exc_info()[1]), traceback.format_exc(), str(sys.argv)))
