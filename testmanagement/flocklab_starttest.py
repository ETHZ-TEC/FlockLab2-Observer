#! /usr/bin/env python3

import os, sys, subprocess, getopt, errno, tempfile, time, shutil, serial, xml.etree.ElementTree
import lib.flocklab as flocklab


### Global variables ###
debug  = False
logger = None


##############################################################################
#
# Usage
#
##############################################################################
def usage():
    print("Usage: %s --testid=<testid> --xml=<path> [--debug]" %sys.argv[0])
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
# log error message and terminate process
#
##############################################################################
def log_error_and_exit(msg, err = errno.EPERM):
    global logger
    flocklab.gpio_set(flocklab.gpio_led_error)
    flocklab.gpio_clr(flocklab.gpio_led_status)
    logger.error("Process finished with errors:\r\n%s" % msg)
    sys.exit(err)     # actual error code doesn't matter
### END log_error_and_exit()


##############################################################################
#
# Main
#
##############################################################################
def main(argv):
    
    ### Get global variables ###
    global debug, logger
    
    xmlfile = None
    testid  = None
    logger  = flocklab.get_logger("flocklab_starttest.py")
    if not logger:
        print("Failed to get logger.")
        sys.exit(errno.EPERM)
    
    # Get config:
    config = flocklab.get_config()
    if not config:
        log_error_and_exit("Could not read configuration file.")
    if debug:
        logger.info("Read configuration file.")
    
    # Get command line parameters.
    try:
        opts, args = getopt.getopt(argv, "hdt:x:p:", ["help", "debug", "testid=", "xml=", "serialport="])
    except (getopt.GetoptError) as err:
        print(str(err))
        log_error_and_exit(str(err), errno.EINVAL)
    except:
        log_error_and_exit("Error: %s: %s" % (str(sys.exc_info()[0]), str(sys.exc_info()[1])), errno.EINVAL)
    for opt, arg in opts:
        if opt in ("-t", "--testid"):
            testid = int(arg)
        elif opt in ("-x", "--xml"):
            xmlfile = arg
            if not (os.path.exists(xmlfile)):
                log_error_and_exit("Error: file %s does not exist" %(str(xmlfile)), errno.EINVAL)
        elif opt in ("-p", "--serialport"):
            serialport = int(arg)
        elif opt in ("-h", "--help"):
            usage()
            sys.exit(flocklab.SUCCESS)
        elif opt in ("-d", "--debug"):
            debug = True
        else:
            usage()
            log_error_and_exit("Wrong API usage", errno.EINVAL)
    
    # Check for mandatory arguments:
    if not xmlfile or not testid:
        usage()
        log_error_and_exit("Wrong API usage", errno.EINVAL)
    
    # Indicate start of the script by enabling status LED
    flocklab.gpio_set(flocklab.gpio_led_status)
    
    # Process XML ---
    # Open and parse XML:
    try:
        tree = ElementTree.ElementTree()
        tree.parse(xmlfile)
        if debug:
            logger.debug("Parsed XML.")
    except:
        log_error_and_exit("Could not find or open XML file at %s." % str(xmlfile))

    # Get basic information from <obsTargetConf> ---
    voltage         = None
    imagefile       = None
    slotnr          = None
    platform        = None
    operatingsystem = None
    noimage         = False

    imagefiles_to_process = tree.findall('obsTargetConf/image')
    imagefile = {}
    for img in imagefiles_to_process:
        imagefile[int(img.get('core'))] = img.text
    if len(imagefiles_to_process) == 0:
        if debug:
            logger.debug("Test without image")
        noimage = True
    
    try:
        voltage = float(tree.find('obsTargetConf/voltage').text)
        # limit the
        if voltage < flocklab.tg_vcc_min:
            voltage = flocklab.tg_vcc_min
        elif voltage > flocklab.tg_vcc_max:
            voltage = flocklab.tg_vcc_max
        slotnr = int(tree.find('obsTargetConf/slotnr').text)
        if not noimage:
            platform = tree.find('obsTargetConf/platform').text.lower()
        if debug:
            logger.debug("Got basic information from XML.")
    except:
        log_error_and_exit("XML: could not find mandatory element(s) in element <obsTargetConf>")
    
    # Activate interface, turn power on ---
    if slotnr:
        if flocklab.tg_select(slotnr) != flocklab.SUCCESS or flocklab.tg_pwr_en() != flocklab.SUCCESS or flocklab.tg_en() != flocklab.SUCCESS:
            log_error_and_exit("Failed to select / enable target %d!" % (slotnr))
        if debug:
            logger.debug("Target %d selected and enabled." % (slotnr))
    else:
        log_error_and_exit("Slot number could not be determined.")
        if debug:
            logger.error(msg)
    
    # Make sure no serial service scripts are running ---
    p = subprocess.Popen(['flocklab_serial.py', '--stop'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (out, err) = p.communicate()
    if (p.returncode not in (flocklab.SUCCESS, errno.ENOPKG)):
        log_error_and_exit("Error %d when trying to stop a potentially running serial service script: %s" % (p.returncode, str(err)))
        if debug:
            logger.error(msg)
    
    # Make sure no DBD is running --- 
    # send sigint to stop
    cmd = ['pkill', '-SIGINT', '-f', 'dbd']
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (out, err) = p.communicate()
    if p.returncode == 0:
        if debug:
            logger.debug("Sent SIGINT to at least one running database daemon (dbd) process.")
    time.sleep(0.5)
    # kill remaining processes
    cmd = ['pkill', '-SIGKILL', '-f', 'dbd']
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (out, err) = p.communicate()
    if p.returncode == 0:
        if debug:
            logger.debug("Killed at least one running database daemon (dbd) process.")
    
    # Pull down GPIO setting lines ---
    for pin in (flocklab.gpio_tg_sig1, flocklab.gpio_tg_sig2):
        if flocklab.gpio_set(pin, 0) != flocklab.SUCCESS:
            log_error_and_exit("Error %d when trying to pull down GPIO line %s: %s" % (r, pin, str(err)))
            if debug:
                logger.error(msg)
                logger.error("Tried to run command %s" % (str(cmd)))
    
    # Flash target ---
    if not noimage:
        for core, image in imagefile.items():
            if (platform in (flocklab.tg_platforms)):
                cmd = ['tg_prog.py', '--image=%s' % image, '--target=%s' % (platform), '--core=%d' % core, '--noreset']
            else:
                cmd = None
                log_error_and_exit("Unknown platform %s. Not known how to program this platform." % platform)
                if debug:
                    logger.error(msg)
                break
            if cmd:
                if debug:
                    logger.debug("Going to flash user image to %s..." % platform)
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                (out, err) = p.communicate()
                if (p.returncode != flocklab.SUCCESS):
                    log_error_and_exit("Error %d when programming target image: %s" % (p.returncode, str(err)))
                    if debug:
                        logger.error(msg)
                        logger.error("Tried reprogramming with %s" % (str(cmd)))
                    break
                else:
                    print("Programmed target with command: %s" % (str(cmd)))
                    if debug:
                        logger.debug("Programmed target with image with command: %s" % (str(cmd)))
    # Set voltage ---
    msg = None
    if flocklab.tg_set_vcc(voltage) != flocklab.SUCCESS:
        log_error_and_exit("Failed to set target voltage to %.1fV" % (voltage))
        if debug:
            logger.error(msg)
        else:
            if debug:
                logger.debug("Target voltage set to %.1fV" % voltage)
    
    # Create test results directory ---
    resfolder = "%s/%d" % (config.get("observer", "testresultfolder"), testid)
    os.makedirs(resfolder)
    print("DB folder '%s' created" % resfolder)
    
    # Configure needed services ---
    # Serial ---
    # As start and configuration of this service is done in one step, start is also done here:
    if (tree.find('obsSerialConf') != None):
        if debug:
            logger.debug("Found config for serial service.")
        if operatingsystem == None:
            targetos = "other"
        else:
            targetos = operatingsystem
        cmd = ['flocklab_serial.py', '--testid=%d' % testid]
        if slotnr:
            logger.debug("Set Socketport to: %d" %serialport)
            cmd.append('--socketport=%d' % (serialport)) # + slotnr - 1))
        if tree.find('obsSerialConf/port') != None:
            port = tree.find('obsSerialConf/port').text
            cmd.append('--port=%s'%(port))
        if (tree.find('obsSerialConf/baudrate') != None):
            cmd.append('--baudrate=%s'%(tree.find('obsSerialConf/baudrate').text))
        cmd.append('--daemon')
        if debug:
            cmd.append('--debug')
        p = subprocess.Popen(cmd)
        logger.debug("Started serial output with: %s" % cmd)
        rs = p.wait()
        if (rs != flocklab.SUCCESS):
            log_error_and_exit("Error %d when trying to start serial service." % (rs))
            if debug:
                logger.error(msg)
                logger.error("Tried to start with: %s" % (str(cmd)))
        else:
            # Wait some time to let all threads start
            time.sleep(10)
            if debug:
                logger.debug("Started and configured serial service using command: %s" %(str(cmd)))
    else:
        if debug:
            logger.debug("No config for serial service found.")

    # Power profiling ---
    if (tree.find('obsPowerprofConf') != None and False):
        if debug:
            logger.debug("Found config for power profiling.")
        # Cycle trough all configurations and write them to a file which is then fed to the service.
        # Create temporary file:
        (fd, batchfile) = tempfile.mkstemp() 
        f = os.fdopen(fd, 'w+b')
        # Cycle through all powerprof configs and insert them into file:
        subtree = tree.find('obsPowerprofConf')
        profconfs = list(subtree.getiterator("profConf"))
        for profconf in profconfs:
            duration = profconf.find('duration').text
            # Get time and bring it into right format:
            starttime = flocklab.timeformat_xml2service(config, profconf.find('absoluteTime/absoluteDateTime').text)
            microsecs = profconf.find('absoluteTime/absoluteMicrosecs').text
            nthsample = profconf.find('samplingDivider')
            if nthsample != None:
                nthsample = nthsample.text
            else:
                nthsample = config.get('powerprofiling', 'nthsample_default')
            f.write("%s;%s;%s;%s;\n" %(duration, starttime, microsecs, nthsample))
        f.close()
        # Feed service with batchfile:
        cmd = ['flocklab_powerprofiling', '-addbatch', '--file=%s'%batchfile]
        if not debug:
            cmd.append('--quiet')
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (out, err) = p.communicate()
        if (p.returncode != flocklab.SUCCESS):
            log_error_and_exit("Error %d when trying to configure powerprofiling service: %s" % (p.returncode, str(err)))
            if debug:
                logger.error(msg)
                logger.error("Tried to configure with: %s" % (str(cmd)))
        else:
            # Remove batch file:
            os.remove(batchfile)
            if debug:
                logger.debug("Configured powerprofiling service.")
    else:
        if debug:
            logger.debug("No config for powerprofiling service found.")
    
    # GPIO setting ---
    if (tree.find('obsGpioSettingConf') != None):
        if debug:
            logger.debug("Found config for GPIO setting.")
        # Cycle trough all configurations and write them to a file which is then fed to the service.
        # Create temporary file:
        (fd, batchfile) = tempfile.mkstemp() 
        f = os.fdopen(fd, 'w+b')
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
            log_error_and_exit("Error %d when trying to configure GPIO setting service: %s" % (p.returncode, str(err)))
            if debug:
                logger.error(msg)
                logger.error("Tried to configure with: %s" % (str(cmd)))
        else:
            # Remove batch file:
            os.remove(batchfile)
            if debug:
                logger.debug("Configured GPIO setting service.")
        if len(resets) == 2 and settingcount == 2 and (max(resets) - min(resets) > 30): # only reset setting, register test switch at end of test
            # switchtime = max(resets) - 30
            xml_file = "%s/%d/config.xml" % (config.get("observer","testconfigfolder"), testid)
            log_file = "%s/%d/" % (config.get("observer","testresultfolder"), testid)
            flocklab.start_pwr_measurement()
            flocklab.tg_reset()
            if debug:
                logger.debug("Target reset.")
            flocklab.start_gpio_tracing(xml_file, log_file)
    else:
        if debug:
            logger.debug("No config for GPIO setting service found.")
    
    # GPIO monitoring ---
    if (tree.find('obsGpioMonitorConf') != None and False):
        if debug:
            logger.debug("Found config for GPIO monitoring.")
        # Cycle trough all configurations and write them to a file which is then fed to the service.
        # Create temporary file:
        (fd, batchfile) = tempfile.mkstemp() 
        f = os.fdopen(fd, 'w+b')
        # Cycle through all configs and insert them into file:
        subtree = tree.find('obsGpioMonitorConf')
        pinconfs = list(subtree.getiterator("pinConf"))
        for pinconf in pinconfs:
            pin = flocklab.pin_abbr2num(pinconf.find('pin').text)
            edge = flocklab.edge_str2abbr(pinconf.find('edge').text)
            mode = flocklab.gpiomon_mode_str2abbr(pinconf.find('mode').text)
            # Check if there is a callback defined. If yes, add it.
            if (pinconf.find('callbackGpioSetAdd')):
                cbkpin = flocklab.pin_abbr2num(pinconf.find('callbackGpioSetAdd/pin').text)
                cbklevel = flocklab.level_str2abbr(pinconf.find('callbackGpioSetAdd/level').text)
                cbkoffsets  = pinconf.find('callbackGpioSetAdd/offsetSecs').text
                cbkoffsetms = pinconf.find('callbackGpioSetAdd/offsetMicrosecs').text
                callbackargs = "gpio_set_add,%s,%s,%s,%s" %(cbkpin, cbklevel, cbkoffsets, cbkoffsetms)
            elif (pinconf.find('callbackPowerprofAdd')):
                cbkdur      = pinconf.find('callbackPowerprofAdd/duration').text
                cbkoffsets  = pinconf.find('callbackPowerprofAdd/offsetSecs').text
                cbkoffsetms = pinconf.find('callbackPowerprofAdd/offsetMicrosecs').text
                callbackargs = "powerprof_add,%s,%s,%s" %(cbkdur, cbkoffsets, cbkoffsetms)
            else:
                callbackargs = ""
            # Write monitor command and possible callback to file:
            f.write("%s;%s;%s;%s;\n" %(pin, edge, mode, callbackargs))
        f.close()
        # Feed service with batchfile:
        cmd = ['flocklab_gpiomonitor', '-addbatch', '--file=%s'%batchfile]
        if not debug:
            cmd.append('--quiet')
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (out, err) = p.communicate()
        if (p.returncode != flocklab.SUCCESS):
            log_error_and_exit("Error %d when trying to configure GPIO monitoring service: %s" % (p.returncode, str(err)))
            if debug:
                logger.error(msg)
                logger.error("Tried to configure with: %s" % (str(cmd)))
        else:
            # Remove batch file:
            os.remove(batchfile)
            if debug:
                logger.debug("Configured GPIO monitoring service.")
    else:
        if debug:
            logger.debug("No config for GPIO monitoring service found.")
    
    # Rename XML ---
    try:
        os.rename(xmlfile, "%s/config.xml" % os.path.dirname(xmlfile))
    except (OSError) as err:
        log_error_and_exit("Could not rename XML config file.")
        if debug:
            logger.error(msg)
            logger.error("Error was: %s" %(str(err)))
    
    flocklab.gpio_clr(flocklab.gpio_led_error)
    logger.info("Test successfully started.")
    sys.exit(flocklab.SUCCESS)
### END main()


if __name__ == "__main__":
    main(sys.argv[1:])
