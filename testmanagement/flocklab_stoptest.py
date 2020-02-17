#! /usr/bin/env python3

import os, sys, getopt, errno, subprocess, serial, time, configparser, shutil, syslog, xml.etree.ElementTree, traceback, re
import lib.flocklab as flocklab


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
    
    debug  = False
    errors = []
    testid = None
    
    # Get config:
    config = flocklab.get_config()
    if not config:
        flocklab.error_logandexit("Could not read configuration file.")
    
    # Get command line parameters.
    try:
        opts, args = getopt.getopt(argv, "dht:", ["debug", "help", "testid="])
    except (getopt.GetoptError) as err:
        flocklab.error_logandexit(str(err), errno.EINVAL)
    for opt, arg in opts:
        if opt in ("-t", "--testid"):
            testid = int(arg)
        elif opt in ("-d", "--debug"):
            debug = True
        elif opt in ("-h", "--help"):
            usage()
            sys.exit(flocklab.SUCCESS)
        else:
            flocklab.error_logandexit("Wrong API usage", errno.EINVAL)
    
    # Check for mandatory arguments:
    if not testid:
        flocklab.error_logandexit("No test ID supplied", errno.EINVAL)
    
    # Init logger
    logger = flocklab.get_logger(debug=debug)
    if not logger:
        flocklab.error_logandexit("Could not get logger.")
    
    # Check if SD card is mounted ---
    if not flocklab.is_sdcard_mounted():
        errors.append("SD card is not mounted.")
    
    # Get info from XML ---
    # Get xml file for current test, find out slot number, platform and image location:
    slotnr = None
    platform = None
    imagepath = []
    xmlfilename = "%s/%d/config.xml" % (config.get("observer", "testconfigfolder"), testid)
    try:
        tree = xml.etree.ElementTree.ElementTree()
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
        errors.append("Could not find or open XML file '%s'." % (xmlfilename))
    
    # Activate interface ---
    if slotnr:
        flocklab.tg_select(slotnr)
        logger.debug("Activated interface %d." % slotnr)
    else:
        # Assume that the interface is still activated.
        slotnr = flocklab.tg_get_selected()
        errors.append("Could not activate interface because slot number could not be determined. Working on currently active interface %d." % slotnr)
    
    # Stop serial service ---
    # This has to be done before turning off power since otherwise the service will encounter errors due to disappearing devices.
    cmd = [config.get("observer", "serialservice"), '--stop', '--testid=%d' % testid]
    if debug:
        cmd.append('--debug')
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    (out, err) = p.communicate()
    rs = p.returncode
    if (rs not in (flocklab.SUCCESS, errno.ENOPKG)):
        errors.append("Error %d when trying to stop serial service." % rs)
    else:
        logger.debug("Stopped serial service.")
    
    # Reset all remaining services, regardless of previous errors ---
    if flocklab.stop_gpio_tracing() != flocklab.SUCCESS:
        errors.append("Failed to stop GPIO tracing service.")
    else:
        logger.debug("Stopped GPIO tracing.")
    if flocklab.stop_pwr_measurement() != flocklab.SUCCESS:
        errors.append("Failed to stop power measurement.")
    else:
        logger.debug("Stopped power measurement.")
    
    # allow some time for the above services to terminate properly
    time.sleep(10)
    
    # add some more info to the timesync log ---
    timesynclogfile = "%s/%d/timesync_%s.log" % (config.get("observer", "testresultfolder"), testid, time.strftime("%Y%m%d%H%M%S", time.gmtime()))
    chronyinfo = "invalid"
    p = subprocess.Popen(['chronyc', 'sources'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    out, err = p.communicate(None)
    if (p.returncode == 0):
        lines = out.split('\n')
        for line in lines:
            res = re.match("^[#^]{1}\*\s+([a-zA-Z0-9.-_]+)[0-9\s]+([+-]{1}[0-9a-z]+)\[\s*([+-]{1}[0-9a-z]+)\]\s+(\+/\-[0-9a-z\s]*)$", line)
            if res:
                with open(timesynclogfile, "a") as tslog:
                    tslog.write("%s,time source: %s | adjusted offset: %s | measured offset: %s | estimated error: %s\n" % (str(time.time()), res.group(1), res.group(2), res.group(3), res.group(4)))
                break;
    else:
        flocklab.log_test_error("Failed to query time source.")
    ppsfile = "%s/%d/ppscount" % (config.get("observer", "testresultfolder"), testid)
    if os.path.isfile(ppsfile):
        try:
            with open(ppsfile) as f:
                ppsstatsstart = f.read().split()
                with open(flocklab.gmtimerstats) as ppsstats:
                    ppscountend = ppsstats.read().split()[1]
                    deltacount = int(ppscountend) - int(ppsstatsstart[1])
                    deltaT = int(time.time() - float(ppsstatsstart[0]))
                    with open(timesynclogfile, "a") as tslog:
                        tslog.write("%s,GNSS PPS reception: %.2f%%\n" % (str(time.time()), min(100.0, (deltacount * 100.0 / deltaT))))
        except:
            flocklab.log_test_error("Failed to calculate PPS count.");
    
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
            cmd = [config.get("observer", "progscript"), '--image=%s/%s' % (config.get("observer", "defaultimgfolder"), imgfile), '--target=%s' % (platform), '--core=%d' % core]
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            (out, err) = p.communicate()
            rs = p.returncode
            if (rs != flocklab.SUCCESS):
                if not optional_reprogramming:
                    errors.append("Could not flash target with default image because error %d occurred (%s)." % (rs, err.strip()))
            else:
                logger.debug("Reprogrammed target with default image.")
            core = core + 1
    elif len(imagepath) > 0:
        logger.warn("Could not flash target with default image because slot number and/or platform could not be determined.")
    
    # Set voltage to 3.3V, turn target off ---
    flocklab.tg_set_vcc()
    flocklab.tg_pwr_en(False)
    flocklab.tg_en(False)
    
    # Remove config directory ---
    testconfigpath = "%s/%d" % (config.get("observer", "testconfigfolder"), testid)
    if os.path.exists(testconfigpath):
        shutil.rmtree(testconfigpath)
        logger.debug("Test config '%s' removed." % (testconfigpath))
    
    # Disable status LED
    flocklab.gpio_clr(flocklab.gpio_led_status)
    
    # Error checking ---
    if errors:
        flocklab.error_logandexit("Process finished with %d errors:\n%s" % (len(errors), "\n".join(errors)))
    
    # Successful
    logger.info("Successfully stopped test.")
    flocklab.gpio_clr(flocklab.gpio_led_error)
    
    sys.exit(flocklab.SUCCESS)
### END main()


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except Exception:
        flocklab.error_logandexit("Encountered error: %s\n%s\nCommandline was: %s" % (str(sys.exc_info()[1]), traceback.format_exc(), str(sys.argv)))
