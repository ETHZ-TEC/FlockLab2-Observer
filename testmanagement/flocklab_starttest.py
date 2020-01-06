#! /usr/bin/env python3

import os, sys, subprocess, getopt, errno, tempfile, time, shutil, serial
from xml.etree.ElementTree import ElementTree
import lib.flocklab as flocklab


### Global variables ###
debug = False

services = {
#'flocklab_powerprofiling':['obsPowerprofConf','powerprofiling','powerprofiling','Powerprofiling'], 
#'flocklab_gpiosetting':['obsGpioSettingConf','gpio_setting','gpiosetting','GPIO setting'],
#'flocklab_gpiomonitor':['obsGpioMonitorConf','gpio_monitor','gpiomonitoring','GPIO monitoring']
}# Userspace API name:[XML Element name, service name for DBD, Service short name, Service long name]


##############################################################################
#
# errchk_exit -    Check for errors, report them and exit with appropriate code
#
##############################################################################
def errchk_exit(led_path=None, errors=[], logger=None):
    if ((led_path==None) or (logger==None)):
        return errno.EINVAL 
    
    if errors:
        # Indicate errors of the script by blinking LED 4 on the FlockBoard
        flocklab.led_blink(led_path, 50, 500)
        if debug:
            logger.debug("Changed blink status of LED 4.")
        logger.error("Process finished with %s errors:" %str(len(errors)))
        for err in errors:
            logger.error(err)
        return errno.EPERM
    else:
        # Indicate success of the script by turning off LED 4 on the FlockBoard
        flocklab.led_on(led_path)
        if debug:
            logger.debug("Changed blink status of LED 4.")
        logger.info("Successfully started test.")
        return flocklab.SUCCESS
### END errchk_exit()


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
# Main
#
##############################################################################
def main(argv):
    
    ### Get global variables ###
    global debug
    
    xmlfile = None
    testid = None
    # Get logger:
    logger = flocklab.get_logger("flocklab_starttest.py")
    
    # Get config:
    config = flocklab.get_config()
    if not config:
        logger.warn("Could not read configuration file. Exiting...")
        sys.exit(errno.EAGAIN)
    if debug:
        logger.info("Read configuration file.")
    led_path = config.get("observer","led_red")

    # Get command line parameters.
    try:
        opts, args = getopt.getopt(argv, "hdt:x:p:", ["help", "debug", "testid=", "xml=", "serialport="])
    except (getopt.GetoptError) as err:
        print(str(err))
        logger.error(str(err))
        usage()
        sys.exit(errno.EINVAL)
    except:
        logger.error("Error: %s: %s" %(str(sys.exc_info()[0]), str(sys.exc_info()[1])))
        sys.exit(errno.EINVAL)
    for opt, arg in opts:
        if opt in ("-t", "--testid"):
            testid = int(arg)
        elif opt in ("-x", "--xml"):
            xmlfile = arg
            if not (os.path.exists(xmlfile)):
                err = "Error: file %s does not exist" %(str(xmlfile))
                logger.error(err)
                sys.exit(errno.EINVAL)
        elif opt in ("-p", "--serialport"):
            serialport = int(arg)
        elif opt in ("-h", "--help"):
            debug = True
            usage()
            sys.exit(flocklab.SUCCESS)
        elif opt in ("-d", "--debug"):
            debug = True
        else:
            logger.error("Wrong API usage")
            usage()
            sys.exit(errno.EINVAL)
    
    # Check for mandatory arguments:
    if not xmlfile or not testid:
        print("Wrong API usage")
        logger.error("Wrong API usage")
        usage()
        sys.exit(errno.EINVAL)
            
    # Indicate start of the script by blinking LED 4 on the FlockBoard
    flocklab.led_blink(led_path, 200, 200)
    if debug:
        logger.debug("Changed blink status of LED 4.")
    
    errors = []
    
    # clear system caches to prevent memory fragmentation
    rs = subprocess.call('/bin/echo 3 > /proc/sys/vm/drop_caches', shell=True)
    # start gps log
    # rs = subprocess.call('/home/root/mmc/gpsdop/gpsdoplog.sh start', shell=True)
    
    # Process XML ---
    # Open and parse XML:
    try:
        tree = ElementTree()
        tree.parse(xmlfile)
        if debug:
            logger.debug("Parsed XML.")
    except:
        msg = "Could not find or open XML file at %s."%(str(xmlfile))
        errors.append(msg)
        if debug:
            logger.error(msg)
    # Get basic information from <obsTargetConf> ---
    voltage         = None
    imagefile       = None
    slotnr          = None
    platform        = None
    operatingsystem = None
    firmwareversion = None
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
        voltage = int(10*float(tree.find('obsTargetConf/voltage').text))
        slotnr = int(tree.find('obsTargetConf/slotnr').text)
        try:
            operatingsystem = tree.find('obsTargetConf/os').text.lower()
        except:
            if not noimage:
                raise
        if not noimage:
            firmwareversion = tree.find('obsTargetConf/firmware').text
            platform = tree.find('obsTargetConf/platform').text.lower()
            platform = "dpp"
            logger.info("Currently platform is set to dpp per default")
        if debug:
            logger.debug("Got basic information from XML.")
    except:
        msg = "XML: could not find mandatory element(s) in element <obsTargetConf>"
        errors.append(msg)
        if debug:
            logger.error(msg)
            
    # Make a list of used services ---
    used_services = []
    for key in services.keys():
        if (tree.find(services[key][0]) != None):
            used_services.append(key)
            if debug:
                logger.debug("Found config for %s."%(services[key][3]))
    
    # Activate interface, turn power off ---
    if slotnr:
        flocklab.tg_pwr_set(slotnr, 0)
        flocklab.tg_usbpwr_set(slotnr, 0)
        flocklab.tg_interface_set(slotnr)
        if debug:
            logger.debug("Turned power and USB power for target %d off, activated interface %d"%(slotnr, slotnr))
    else:
        msg = "Could not activate interface and turn off target power because slot number could not be determined."
        errors.append(msg)
        if debug:
            logger.error(msg)
            

    # Make sure no serial service scripts are running ---
    #p = subprocess.Popen(['flocklab_serial.py', '--stop'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    #(out, err) = p.communicate()
    #if (p.returncode not in (flocklab.SUCCESS, errno.ENOPKG)):
        #msg = "Error %d when trying to stop a potentially running serial service script: %s"%(p.returncode, str(err))
        #errors.append(msg)
        #if debug:
            #logger.error(msg)
            #logger.error("Tried to stop a potentially running serial service script")
    #else:
        #if debug:
            #logger.debug("Successfully stopped any potentially running serial service script")

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
        
    # Make sure all kernel-module based services are running ---
    flocklab.start_services(services, logger, debug)
    
    # Pull down GPIO setting lines ---
    for pin in ('SIG1', 'SIG2'):
        r = flocklab.tg_press_gpio(flocklab.pin_abbr2num(pin), 0)
        if (r not in (flocklab.SUCCESS, )):
            msg = "Error %d when trying to pull down GPIO line %s: %s"%(r, pin, str(err))
            errors.append(msg)
            if debug:
                logger.error(msg)
                logger.error("Tried to run command %s"%(str(cmd)))
        else:
            if debug:
                  logger.debug("Successfully pulled down GPIO line %s."%pin)
    
    # Flash target, set voltage ---
    if not errors:
        # Set voltage:
        if slotnr:
            flocklab.tg_pwr_set(slotnr, 1)
        msg = None
        for i in range(0,5):
            try:
                flocklab.tg_volt_set(voltage, config.get("observer", "tg_pwr_force_pwm"))
                break
            except (IOError) as err:
                msg = "Error when setting target voltage to %d: %s"%(voltage, str(err))
        if msg:
            errors.append(msg)
            if debug:
                logger.error(msg)
        else:
            if debug:
                logger.debug("Set target voltage to %d"%voltage)
        # Flash target: this is dependent on the operating system and the platform:
        if not noimage:
            for core, image in imagefile.items():
                if (platform in ('tmote', 'dpp')):
                    cmd = ['tg_prog.py', '--image=%s'%image, '--target=%s'%(platform), '--core=%d' % core, '--noreset']
                else:
                    cmd = None
                    msg = "Unknown platform %s. Not known how to program this platform."%platform
                    errors.append(msg)
                    if debug:
                        logger.error(msg)
                    break
                if cmd:
                    if debug:
                        logger.debug("Going to flash user image to %s..."%platform)
                    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    (out, err) = p.communicate()
                    if (p.returncode != flocklab.SUCCESS):
                        msg = "Error %d when programming target image: %s"%(p.returncode, str(err))
                        errors.append(msg)
                        if debug:
                            logger.error(msg)
                            logger.error("Tried reprogramming with %s"%(str(cmd)))
                        break
                    else:
                        print("Programmed target with image with command: %s"%(str(cmd)))
                        if debug:
                            logger.debug("Programmed target with image with command: %s"%(str(cmd)))
    else:
        msg = "Could not flash target image nor set target voltage because of previous errors in start script."
        errors.append(msg)
        if debug:
            logger.error(msg)

    # create db directory for this test
    dbfolder = "%s%d" % (config.get("observer", "obsdbfolder"), testid)
    print(dbfolder)
    os.makedirs(dbfolder)

    # Configure needed services ---
    if not errors:
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
                msg = "Error %d when trying to start serial service."%(rs)
                errors.append(msg)
                if debug:
                    logger.error(msg)
                    logger.error("Tried to start with: %s"%(str(cmd)))
            else:
                # Wait some time to let all threads start
                time.sleep(10)
                if debug:
                    logger.debug("Started and configured serial service using command: %s" %(str(cmd)))
        else:
            if debug:
                logger.debug("No config for serial service found.")

        #TODO: new power profiling! && new GPIO setting
        # Powerprofiling ---
        if (tree.find('obsPowerprofConf') != None and False):
            if debug:
                logger.debug("Found config for powerprofiling.")
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
                msg = "Error %d when trying to configure powerprofiling service: %s"%(p.returncode, str(err))
                errors.append(msg)
                if debug:
                    logger.error(msg)
                    logger.error("Tried to configure with: %s"%(str(cmd)))
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
                msg = "Error %d when trying to configure GPIO setting service: %s"%(p.returncode, str(err))
                errors.append(msg)
                if debug:
                    logger.error(msg)
                    logger.error("Tried to configure with: %s"%(str(cmd)))
            else:
                # Remove batch file:
                os.remove(batchfile)
                if debug:
                    logger.debug("Configured GPIO setting service.")
            if len(resets) == 2 and settingcount == 2 and (max(resets) - min(resets) > 30): # only reset setting, register test switch at end of test
                cmd = ['flocklab_scheduler.py', '--add', '--testid=%d'%testid, '--switchtime=%d' % (max(resets) - 30) ]
                if debug:
                    cmd.append('--debug')
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                (out, err) = p.communicate()
                if (p.returncode != flocklab.SUCCESS):
                    msg = "Error %d when trying to schedule test switch: %s"%(p.returncode, str(err))
                    errors.append(msg)
                    if debug:
                        logger.error(msg)
                        logger.error("Tried to configure with: %s"%(str(cmd)))
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
                msg = "Error %d when trying to configure GPIO monitoring service: %s"%(p.returncode, str(err))
                errors.append(msg)
                if debug:
                    logger.error(msg)
                    logger.error("Tried to configure with: %s"%(str(cmd)))
            else:
                # Remove batch file:
                os.remove(batchfile)
                if debug:
                    logger.debug("Configured GPIO monitoring service.")
        else:
            if debug:
                logger.debug("No config for GPIO monitoring service found.")

    else:
        msg = "Could not configure services because of previous errors in start script."
        errors.append(msg)
        if debug:
            logger.error(msg)
    # Rename XML ---
    try:
        os.rename(xmlfile, "%s/config.xml" % os.path.dirname(xmlfile))
    except (OSError) as err:
        msg = "Could not rename XML config file."
        errors.append(msg)
        if debug:
            logger.error(msg)
            logger.error("Error was: %s" %(str(err)))
    
    # Error checking ---
    rs = errchk_exit(led_path, errors, logger)
    sys.exit(rs)
### END main()

if __name__ == "__main__":
    main(sys.argv[1:])
