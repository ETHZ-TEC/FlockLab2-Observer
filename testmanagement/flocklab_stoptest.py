#! /usr/bin/env python3

import os, sys, getopt, errno, subprocess, serial, time, configparser, shutil, syslog, xml.etree.ElementTree
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
    print("Usage: %s --testid=<testid> [--debug] [--help]" %sys.argv[0])
    print("Stop a running FlockLab test.")
    print("Options:")
    print("  --testid=<testid>\tID of the test.")
    print("  --debug\t\tOptional. Print out debug messages.")
    print("  --help\t\tOptional. Print this help.")
### END usage()


##############################################################################
#
# Main
#
##############################################################################
def main(argv):
    
    global debug, logger
    
    testid = None
    logger = flocklab.get_logger(os.path.basename(__file__))
    if not logger:
        print("Failed to get logger.")
        sys.exit(errno.EPERM)
    
    # Get config:
    config = flocklab.get_config()
    if not config:
        logger.error("Could not read configuration file.")
        sys.exit(errno.EPERM)
    if debug:
        logger.info("Read configuration file.")
    
    # Get command line parameters.
    try:
        opts, args = getopt.getopt(argv, "dht:", ["debug", "help", "testid="])
    except (getopt.GetoptError) as err:
        logger.error(str(err))
        usage()
        sys.exit(errno.EINVAL)
    for opt, arg in opts:
        if opt in ("-t", "--testid"):
            testid = int(arg)
        elif opt in ("-d", "--debug"):
            debug = True
        elif opt in ("-h", "--help"):
            usage()
            sys.exit(flocklab.SUCCESS)
        else:
            usage()
            logger.error("Wrong API usage", errno.EINVAL)
            sys.exit(errno.EINVAL)
    
    # Check for mandatory arguments:
    if not testid:
        logger.error("No test ID supplied")
        sys.exit(errno.EINVAL)
    
    errors = []
    
    # Check if SD card is mounted ---
    if not flocklab.is_sdcard_mounted():
        errors.append("SD card is not mounted.")
    
    # Get info from XML ---
    # Get xml file for current test, find out slot number, platform and image location:
    slotnr = None
    platform = None
    imagepath = []
    xmlfilename = "%s%d/config.xml" % (config.get("observer", "testconfigfolder"), testid)
    try:
        tree = ElementTree()
        tree.parse(xmlfilename)
        rs = tree.find('obsTargetConf')
        if rs != None:
            slotnr = int(rs.find('slotnr').text)
            platform = rs.find('platform')
            if platform != None:
                platform = platform.text.lower()
            imagefiles_to_process = rs.findall('image')
            for img in imagefiles_to_process:
                imagepath.append(img.text)
        else:
            errors.append("Could not find element <obsTargetConf> in %s" % xmlfilename)
    except (IOError) as err:
        errors.append("Could not find or open XML file.")
    
    # Activate interface ---
    if slotnr:
        flocklab.tg_interface_set(slotnr)
        if debug:
            logger.debug("Activated interface %d." % slotnr)
    else:
        # Assume that the interface is still activated.
        slotnr = flocklab.tg_get_selected()
        errors.append("Could not activate interface because slot number could not be determined. Working on currently active interface %d." % slotnr)
    
    # Stop serial service ---
    # This has to be done before turning off power since otherwise the service will encounter errors due to disappearing devices.
    cmd = ['flocklab_serial.py', '--stop', '--testid=%d' % testid]
    if debug:
        cmd.append('--debug')
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (out, err) = p.communicate()
    rs = p.returncode
    if (rs not in (flocklab.SUCCESS, errno.ENOPKG)):
        errors.append("Error %d when trying to stop serial service." % rs)
    elif debug:
        logger.debug("Stopped serial service.")
    
    # Reset all remaining services, regardless of previous errors ---
    flocklab.stop_gpio_tracing()
    if debug:
        logger.debug("Stopped GPIO tracing.")
    flocklab.stop_pwr_measurement()
    if debug:
        logger.debug("Stopped power measurement.")
    #flocklab.collect_pwr_measurement_data(str(testid))   TODO
    
    # Flash target with default image ---
    if platform:
        core = 0
        while True:
            try:
                imgfile = config.get("defaultimages", "img%d_%s" % (core,platform))
                optional_reprogramming = False
            except configparser.NoOptionError:
                try:
                    imgfile = config.get("defaultimages", "optional_img%d_%s" % (core,platform))
                    optional_reprogramming = True
                except configparser.NoOptionError:
                    break
            cmd = ['tg_prog.py', '--image=%s%s'%(config.get("observer", "defaultimgfolder"), imgfile), '--target=%s'%(platform), '--core=%d' % core]
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            (out, err) = p.communicate()
            rs = p.returncode
            if (rs != flocklab.SUCCESS):
                if not optional_reprogramming:
                    errors.append("Could not flash target with default image because error %d occurred." % rs)
            elif debug:
                logger.debug("Reprogrammed target with default image.")
            core = core + 1
    elif len(imagepath) > 0:
        logger.warn("Could not flash target with default image because slot number and/or platform could not be determined.")
    
    # Set voltage to 3.3V, turn target off ---
    flocklab.tg_set_vcc()
    flocklab.tg_pwr_en(False)
    flocklab.tg_en(False)
    
    # Remove config directory ---
    testresultspath = "%s/%d" % (config.get("observer", "testconfigfolder"), testid)
    if os.path.exists(testresultspath):
        shutil.rmtree(testresultspath)
    
    # Disable status LED
    flocklab.gpio_clr(flocklab.gpio_led_status)
    
    # Error checking ---
    if errors:
        flocklab.gpio_set(flocklab.gpio_led_error)
        logger.error("\r\n".join(errors))
        logger.error("Process finished with %s errors." % str(len(errors)))
        sys.exit(errno.EPERM)
    # Successful
    logger.info("Successfully stopped test.")
    flocklab.gpio_clr(flocklab.gpio_led_error)
    sys.exit(flocklab.SUCCESS)
### END main()


if __name__ == "__main__":
    main(sys.argv[1:])
