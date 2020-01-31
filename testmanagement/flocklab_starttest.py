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
        if flocklab.tg_select(slotnr) != flocklab.SUCCESS or flocklab.tg_pwr_en() != flocklab.SUCCESS or flocklab.tg_en() != flocklab.SUCCESS:
            flocklab.error_logandexit("Failed to select / enable target %d!" % (slotnr))
        logger.debug("Target %d selected and enabled." % (slotnr))
    else:
        flocklab.error_logandexit("Slot number could not be determined.")
    
    # Ensure MUX is enabled
    flocklab.tg_mux_en()
    
    # Make sure no serial service scripts are running ---
    p = subprocess.Popen([config.get("observer", "serialservice"), '--stop'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    (out, err) = p.communicate()
    if (p.returncode not in (flocklab.SUCCESS, errno.ENOPKG)):
        flocklab.error_logandexit("Error %d when trying to stop a potentially running serial service script: %s" % (p.returncode, str(err)))
    
    # Pull down GPIO setting lines ---
    if flocklab.gpio_clr(flocklab.gpio_tg_sig1) != flocklab.SUCCESS or flocklab.gpio_clr(flocklab.gpio_tg_sig2) != flocklab.SUCCESS:
        flocklab.error_logandexit("Failed to set GPIO lines")
    
    # Flash target (will set target voltage to 3.3V) ---
    if not noimage:
        for core, image in imagefile.items():
            if (platform in (flocklab.tg_platforms)):
                cmd = [config.get("observer", "progscript"), '--image=%s' % image, '--target=%s' % (platform), '--core=%d' % core]
            else:
                cmd = None
                flocklab.error_logandexit("Unknown platform %s. Not known how to program this platform." % platform)
            if cmd:
                logger.debug("Going to flash user image to %s..." % platform)
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
                (out, err) = p.communicate()
                if (p.returncode != flocklab.SUCCESS):
                    flocklab.error_logandexit("Error %d when programming target image: %s" % (p.returncode, str(out)))
                logger.debug("Programmed target with image %s" % (image))
                flocklab.tg_reset(False)    # hold target in reset state
    
    # Set voltage ---
    msg = None
    if flocklab.tg_set_vcc(voltage) != flocklab.SUCCESS:
        flocklab.error_logandexit("Failed to set target voltage to %.1fV" % (voltage))
    logger.debug("Target voltage set to %.1fV" % voltage)
    
    # Create test results directory ---
    resfolder = "%s/%d" % (config.get("observer", "testresultfolder"), testid)
    try:
        os.makedirs(resfolder)
    except Exception as e:
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
        if (tree.find('obsSerialConf/baudrate') != None):
            logger.debug("Baudrate: %s" % (tree.find('obsSerialConf/baudrate').text))
            cmd.append('--baudrate=%s' % (tree.find('obsSerialConf/baudrate').text))
        cmd.append('--daemon')
        if debug:
            cmd.append('--debug')
        p = subprocess.Popen(cmd)
        rs = p.wait()
        if (rs != flocklab.SUCCESS):
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
            if pinconf.find('pin').text == 'RST':
                resets.append(flocklab.timeformat_xml2timestamp(config, pinconf.find('absoluteTime/absoluteDateTime').text))
            settingcount = settingcount + 1
            level = flocklab.level_str2abbr(pinconf.find('level').text)
            interval = pinconf.find('intervalMicrosecs').text
            count = pinconf.find('count').text
            # Get time and bring it into right format:
            starttime = flocklab.timeformat_xml2service(config, pinconf.find('absoluteTime/absoluteDateTime').text)
            microsecs = pinconf.find('absoluteTime/absoluteMicrosecs').text
            f.write("%s;%s;%s;%s;%s;%s;\n" %(pin, level, starttime, microsecs, interval, count))
        f.close()
        # Feed service with batchfile:
        #cmd = ['flocklab_gpiosetting', '-addbatch', '--file=%s'%batchfile]
        #if not debug:
        #    cmd.append('--quiet')
        #p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        #(out, err) = p.communicate()
        #if (p.returncode != flocklab.SUCCESS):
        if False:
            flocklab.error_logandexit("Error %d when trying to configure GPIO setting service: %s" % (p.returncode, str(err)))
            if debug:
                logger.error(msg)
                logger.error("Tried to configure with: %s" % (str(cmd)))
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
    
    # GPIO tracing ---
    if (tree.find('obsGpioMonitorConf') != None):
        logger.debug("Found config for GPIO monitoring.")
        # Cycle trough all configurations and write them to a file which is then fed to the service.
        # Cycle through all configs and insert them into file:
        subtree = tree.find('obsGpioMonitorConf')
        pinconfs = list(subtree.getiterator("pinConf"))
        pins = []
        for pinconf in pinconfs:
            pins.append(flocklab.pin_abbr2num(pinconf.find('pin').text))
        # TODO use pins config
        tracingfile = "%s/%d/gpio_monitor_%s" % (config.get("observer", "testresultfolder"), testid, time.strftime("%Y%m%d%H%M%S", time.gmtime()))
        if flocklab.start_gpio_tracing(tracingfile, teststarttime, teststoptime) != flocklab.SUCCESS:
            logger.error
        # touch the file
        open(tracingfile + ".csv", 'a').close()
        logger.debug("Started GPIO tracing (output file: %s)." % tracingfile)
    else:
        logger.debug("No config for GPIO monitoring service found.")
    
    # Power profiling ---
    if tree.find('obsPowerprofConf') != None:
        logger.debug("Found config for power profiling.")
        # Cycle through all powerprof configs and insert them into file:
        subtree = tree.find('obsPowerprofConf')
        profconfs = list(subtree.getiterator("profConf"))
        # For now, only accept one powerprofiling config
        profconf = profconfs[0]
        duration = profconf.find('duration').text
        # Get time and bring it into right format:
        starttime = flocklab.timeformat_xml2service(config, profconf.find('absoluteTime/absoluteDateTime').text)
        microsecs = profconf.find('absoluteTime/absoluteMicrosecs').text
        nthsample = profconf.find('samplingDivider')
        if nthsample != None:
            try:
                nthsample = int(nthsample.text)
            except:
                logger.error("Sampling divider is not an integer value.")
                nthsample = 0
        if nthsample:
            samplingrate = flocklab.rl_max_rate / nthsample
        else:
            samplingrate = flocklab.rl_default_rate
        # Start profiling
        outputfile = "%s/%d/powerprofiling_%s.rld" % (config.get("observer", "testresultfolder"), testid, time.strftime("%Y%m%d%H%M%S", time.gmtime()))
        # TODO use start_time=teststarttime
        if flocklab.start_pwr_measurement(out_file=outputfile, sampling_rate=samplingrate) != flocklab.SUCCESS:
            flocklab.error_logandexit("Failed to start power measurement.")
        logger.debug("Started power measurement (output file: %s)." % outputfile)
    else:
        logger.debug("No config for powerprofiling service found.")
    
    flocklab.gpio_clr(flocklab.gpio_led_error)
    logger.info("Test successfully started.")
    
    sys.exit(flocklab.SUCCESS)
### END main()


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except Exception:
        flocklab.error_logandexit("Encountered error: %s\n%s\nCommandline was: %s" % (str(sys.exc_info()[1]), traceback.format_exc(), str(sys.argv)))
