#! /usr/bin/env python3

import os, sys, getopt, errno, subprocess, serial, time, configparser, shutil, syslog, xml.etree.ElementTree, traceback, datetime
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
# collect_error_logs
#
##############################################################################
def collect_error_logs(testid=None):
    # check if results directory exists
    if not os.path.isdir("%s/%d" % (flocklab.config.get("observer", "testresultfolder"), testid)):
        return
    
    # collect GPIO tracing error log
    errorlogfile = "%s/%d/error_%s.log" % (flocklab.config.get("observer", "testresultfolder"), testid, time.strftime("%Y%m%d%H%M%S", time.gmtime()))
    errorlog = open(errorlogfile, 'a')
    if os.path.isfile(flocklab.tracinglog):
        flocklab.logger.debug("Log file %s found." % flocklab.tracinglog)
        with open(flocklab.tracinglog) as logfile:
            lines = logfile.read().split("\n")
            for line in lines:
                try:
                    (timestamp, level, msg) = line.split("\t", 2)
                    t = time.mktime(datetime.datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S").timetuple())   # convert to UNIX timestamp
                    errorlog.write("%s,GPIO tracing error: %s\n" % (t, msg))
                except ValueError:
                    continue        # probably invalid line / empty line
    
    # collect RL error log
    if os.path.isfile(flocklab.rllog):
        flocklab.logger.debug("Log file %s found." % flocklab.rllog)
        with open(flocklab.rllog) as logfile:
            lines = logfile.read().split("\n")
            for line in lines:
                try:
                    (timestamp, level, msg) = line.split("\t", 2)
                    if level in ("ERROR", "WARN"):
                        t = time.mktime(datetime.datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S").timetuple())   # convert to UNIX timestamp
                        errorlog.write("%s,RocketLogger error: %s\n" % (t, msg))
                except ValueError:
                    continue        # probably invalid line / empty line
    
    errorlog.close()
### END collect_error_messages()


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
    if flocklab.stop_gdb_server() != flocklab.SUCCESS:
        errors.append("Failed to stop debug service.")
    else:
        logger.debug("Stopped debug service.")
    
    # allow some time for the above services to terminate properly ---
    time.sleep(10)
    
    # add some more info to the timesync log ---
    try:
        flocklab.log_timesync_info(testid=testid, includepps=True)
    except:
        errors.append("An error occurred while collecting timesync info: %s, %s" % (str(sys.exc_info()[0]), str(sys.exc_info()[1])))
    
    # collect error logs from services ---
    try:
        collect_error_logs(testid)
    except:
        errors.append("An error occurred while collecting error logs: %s, %s" % (str(sys.exc_info()[0]), str(sys.exc_info()[1])))
    
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
