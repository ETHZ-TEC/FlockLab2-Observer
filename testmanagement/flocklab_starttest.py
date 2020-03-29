#! /usr/bin/env python3

import os, sys, subprocess, getopt, errno, tempfile, time, shutil, serial, xml.etree.ElementTree, traceback
import lib.flocklab as flocklab


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
    serialport = None
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
            serialport = int(arg)
        elif opt in ("-h", "--help"):
            usage()
            sys.exit(flocklab.SUCCESS)
        elif opt in ("-d", "--debug"):
            debug = True
        else:
            flocklab.error_logandexit("Invalid option '%s'." % (opt), errno.EINVAL)

    # Check for mandatory arguments:
    if not xmlfile or not testid or not serialport:
        flocklab.error_logandexit("Test ID, XML or serial port missing.", errno.EINVAL)

    # init logger
    logger = flocklab.get_logger(debug=debug)
    if not logger:
        flocklab.error_logandexit("Could not get logger.")

    # Indicate start of the script by enabling status LED
    flocklab.gpio_set(flocklab.gpio_led_status)

    # Rename XML ---
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
    voltage         = None
    imagefile       = None
    slotnr          = None
    platform        = None
    ssport          = None
    operatingsystem = None
    noimage         = False
    teststarttime   = 0

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
    p = subprocess.Popen([config.get("observer", "serialservice"), '--stop'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    (out, err) = p.communicate()
    if (p.returncode not in (flocklab.SUCCESS, errno.ENOPKG)):
        flocklab.error_logandexit("Error %d when trying to stop a potentially running serial service script: %s" % (p.returncode, str(err).strip()))
    flocklab.stop_gpio_tracing()
    flocklab.stop_gpio_actuation()
    flocklab.stop_pwr_measurement()
    flocklab.stop_gdb_server()

    # Enable MUX and power
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
            cmd = [config.get("observer", "progscript"), '--image=%s' % image, '--target=%s' % (platform), '--core=%d' % core]
            logger.debug("Going to flash image to platform %s (core %d)..." % (platform, core))
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            (out, err) = p.communicate()
            if (p.returncode != flocklab.SUCCESS):
                flocklab.tg_off()
                #shutil.move(image, '/tmp/failed_image_%s' % os.path.basename(image))
                #logger.debug("Moved file to /tmp. Command was: %s." % cmd)
                logger.debug("Programming failed. Output of script:\n%s" % (out.strip()))
                flocklab.error_logandexit("Error %d when programming target image:\n%s" % (p.returncode, err.strip()))
            logger.debug("Programmed target with image %s" % (image))

    # Hold target in reset state
    flocklab.tg_reset(False)

    # Set voltage ---
    msg = None
    if flocklab.tg_set_vcc(voltage) != flocklab.SUCCESS:
        flocklab.tg_off()
        flocklab.error_logandexit("Failed to set target voltage to %.1fV" % (voltage))
    logger.debug("Target voltage set to %.1fV" % voltage)

    # Create test results directory ---
    resfolder = "%s/%d" % (config.get("observer", "testresultfolder"), testid)
    try:
        os.makedirs(resfolder)
    except Exception as e:
        flocklab.tg_off()
        flocklab.error_logandexit("Failed to create directory: %s" % str(e))
    logger.debug("Test results folder '%s' created" % resfolder)

    # Configure needed services ---
    # Serial ---
    if tree.find('obsSerialConf') != None:
        logger.debug("Found config for serial service.")
        cmd = [config.get("observer", "serialservice"), '--testid=%d' % testid]
        if slotnr:
            logger.debug("Serial socket port: %d" % serialport)
            cmd.append('--socketport=%d' % (serialport))
        br = tree.findtext('obsSerialConf/baudrate')
        if br != None:
            logger.debug("Baudrate: %s" % (br))
            cmd.append('--baudrate=%s' % (br))
        ssport = tree.findtext('obsSerialConf/port')
        if ssport != None:
            logger.debug("Port: %s" % (ssport))
            cmd.append('--port=%s' % (ssport))
        # note: force serial port 'usb' for target tmote
        if platform == 'tmote':
            ssport = 'usb'
        cmd.append('--daemon')
        if debug:
            cmd.append('--debug')
        p = subprocess.Popen(cmd)
        rs = p.wait()
        if (rs != flocklab.SUCCESS):
            flocklab.tg_off()
            flocklab.error_logandexit("Error %d when trying to start serial service." % (rs))
        else:
            # Wait some time to let all threads start
            time.sleep(3)
            logger.debug("Started and configured serial service.")
    else:
        logger.debug("No config for serial service found.")

    # GPIO actuation ---
    flocklab.tg_act_en()  # make sure actuation is enabled
    if (tree.find('obsGpioSettingConf') != None):
        logger.debug("Found config for GPIO setting.")
        # Cycle trough all configurations and write them to a file which is then fed to the service.
        # Create temporary file:
        (fd, batchfile) = tempfile.mkstemp()
        f = os.fdopen(fd, 'w')
        # Cycle through all configs and insert them into file:
        subtree = tree.find('obsGpioSettingConf')
        pinconfs = list(subtree.getiterator("pinConf"))
        settingcount = 0
        resets = []
        for pinconf in pinconfs:
            pin = flocklab.pin_abbr2num(pinconf.find('pin').text)
            tstart = flocklab.timeformat_xml2timestamp(pinconf.find('absoluteTime/absoluteDateTime').text)
            if pinconf.find('pin').text == 'RST':
                resets.append(tstart)
            settingcount = settingcount + 1
            level = flocklab.level_str2abbr(pinconf.find('level').text)
            interval = pinconf.find('intervalMicrosecs').text
            count = pinconf.find('count').text
            # Get time and bring it into right format:
            microsecs = pinconf.find('absoluteTime/absoluteMicrosecs').text
            f.write("%s;%s;%s;%s;%s;%s;\n" %(pin, level, tstart, microsecs, interval, count))
        f.close()
        # Feed service with batchfile:
        #cmd = ['flocklab_gpiosetting', '-addbatch', '--file=%s'%batchfile]
        #if not debug:
        #    cmd.append('--quiet')
        #p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        #(out, err) = p.communicate()
        #if (p.returncode != flocklab.SUCCESS):
        if False:   # TODO
            flocklab.tg_off()
            flocklab.error_logandexit("Error %d when trying to configure GPIO setting service: %s" % (p.returncode, str(err).strip()))
        else:
            # Remove batch file:
            os.remove(batchfile)
            logger.debug("Configured GPIO setting service.")
        # determine test start
        try:
            teststarttime = int(resets[0])   # 1st reset actuation is the reset release = start of test
            teststoptime  = int(resets[-1])  # last reset actuation is the test stop time
            logger.debug("Test will run from %s to %s." % (teststarttime, teststoptime))
        except:
            logger.error("Could not determine test start time.")
    else:
        logger.debug("No config for GPIO setting service found.")

    # Make sure the test start time is in the future ---
    if int(time.time()) > teststarttime:
        flocklab.tg_off()
        flocklab.error_logandexit("Test start time %d is in the past." % (teststarttime))

    # Debug ---
    if tree.find('obsDebugConf') != None:
        logger.debug("Found config for debug service.")
        remoteIp = "0.0.0.0"
        if tree.find('obsDebugConf/remoteIp') != None:
            remoteIp = tree.findtext('obsDebugConf/remoteIp')
        port = 2331
        if tree.find('obsDebugConf/gdbPort') != None:
            port = int(tree.findtext('obsDebugConf/gdbPort'))
        # make sure mux is enabled and target is released from reset state!
        flocklab.tg_mux_en(True)
        flocklab.tg_reset()
        # start GDB server 10s after test start
        if flocklab.start_gdb_server(platform, port, int(teststarttime - time.time() + 10)) != flocklab.SUCCESS:
            flocklab.tg_off()
            flocklab.error_logandexit("Failed to start debug service.")
        else:
            logger.debug("GDB server will be listening on port %d." % port)
        logger.debug("Started and configured debug service.")
    else:
        logger.debug("No config for debug service found.")
        # disable MUX for more accurate current measurements only if serial port is not USB
        if ssport != "usb":
            flocklab.tg_mux_en(False)
            logger.debug("Disabling MUX.")

    # GPIO tracing ---
    if tree.find('obsGpioMonitorConf'):
        logger.debug("Found config for GPIO monitoring.")
        # move the old log file
        if os.path.isfile(flocklab.tracinglog):
            os.replace(flocklab.tracinglog, flocklab.tracinglog + ".old")
        # Cycle trough all configurations and write them to a file which is then fed to the service.
        # Cycle through all configs and insert them into file:
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
            offset = 0
        tracingfile = "%s/%d/gpio_monitor_%s" % (config.get("observer", "testresultfolder"), testid, time.strftime("%Y%m%d%H%M%S", time.gmtime()))
        if flocklab.start_gpio_tracing(tracingfile, teststarttime, teststoptime, pins, offset) != flocklab.SUCCESS:
            flocklab.tg_off()
            flocklab.error_logandexit("Failed to start GPIO tracing service.")
        # touch the file
        open(tracingfile + ".csv", 'a').close()
        logger.debug("Started GPIO tracing (output file: %s, pins: 0x%x, offset: %u)." % (tracingfile, pins, offset))
    else:
        logger.debug("No config for GPIO monitoring service found.")
        # make sure the reset pin is actuated
        flocklab.start_gpio_actuation(teststarttime, teststoptime)

    # Power profiling ---
    if tree.find('obsPowerprofConf'):
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
            flocklab.tg_off()
            flocklab.error_logandexit("Failed to start power measurement.")
        logger.debug("Power measurement will start at %s (output: %s, sampling rate: %dHz, duration: %ds)." % (str(starttime), outputfile, samplingrate, duration))
    else:
        logger.debug("No config for powerprofiling service found.")

    # Timesync log ---
    try:
        flocklab.log_timesync_info(testid=testid)
        flocklab.store_pps_count(testid)
    except:
        flocklab.tg_off()
        flocklab.error_logandexit("Failed to collect timesync info (%s, %s)." % (str(sys.exc_info()[0]), str(sys.exc_info()[1])))

    flocklab.gpio_clr(flocklab.gpio_led_error)
    logger.info("Test successfully started.")

    sys.exit(flocklab.SUCCESS)
### END main()


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except Exception:
        flocklab.error_logandexit("Encountered error: %s\n%s\nCommandline was: %s" % (str(sys.exc_info()[1]), traceback.format_exc(), str(sys.argv)))
