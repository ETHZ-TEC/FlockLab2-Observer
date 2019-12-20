#! /usr/bin/env python3

import os, sys, getopt, errno, subprocess, serial, time, configparser, shutil, syslog
from xml.etree.ElementTree import ElementTree
import lib.flocklab as flocklab


### Global variables ###
debug = False


##############################################################################
#
# Error classes
#
##############################################################################
class Error(Exception):
    """Base class for exceptions in this module."""
    pass
### END Error classes



##############################################################################
#
# errchk_exit -    Check for errors, report them and exit with appropriate code
#
##############################################################################
def errchk_exit(led_path=None, errors=[], logger=None, rs=flocklab.SUCCESS):
    if ((led_path==None) or (logger==None)):
        return errno.EINVAL 
    
    if errors:
        # Indicate errors of the script by blinking LED 4 on the FlockBoard
        flocklab.led_blink(led_path, 50, 500)
        if debug:
            logger.debug("Changed blink status of LED 4.")
        logger.error("Process finished with %s errors." %str(len(errors)))
        return errno.EPERM
    else:
        # Indicate success of the script by turning off LED 4 on the FlockBoard
        if debug:
            logger.debug("Exiting program with return code %d: %s" %(rs, os.strerror(rs)))
        logger.info("Successfully stopped test.")
        flocklab.led_off(led_path)
        if debug:
            logger.debug("Changed blink status of LED 4.")
        return flocklab.SUCCESS
### END errchk_exit()



##############################################################################
#
# Usage
#
##############################################################################
def usage():
    print("Usage: %s --testid=<testid> [--debug] [--help] [--version]" %sys.argv[0])
    print("Stop a running FlockLab test.")
    print("Options:")
    print("  --testid=<testid>\t\tID of the test.")
    print("  --debug\t\t\tOptional. Print out debug messages.")
    print("  --help\t\t\tOptional. Print this help.")
    print("  --version\t\t\tOptional. Print version number of software and exit.")
### END usage()



##############################################################################
#
# Main
#
##############################################################################
def main(argv):
    global debug
    
    FlockDAQ = "false"
    testid = None
    
    # Get logger:
    logger = flocklab.get_logger("flocklab_stoptest.py")
    
    # Get config:
    config = flocklab.get_config()
    if not config:
        logger.warn("Could not read configuration file. Exiting...")
        sys.exit(errno.EAGAIN)
    if debug:
        logger.info("Read configuration file.")
    led_path = config.get("observer", "led_red")
    

    # Get command line parameters.
    try:                                
        opts, args = getopt.getopt(argv, "dhvt:", ["debug", "help", "version", "testid="])
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
        
        elif opt in ("-v", "--version"):
            print(version)
            sys.exit(flocklab.SUCCESS)
        
        else:
            print("Wrong API usage")
            logger.error("Wrong API usage")
            usage()
            sys.exit(errno.EINVAL)
    
    # Check for mandatory arguments:
    if not testid:
        print("Wrong API usage")
        logger.error("Wrong API usage")
        usage()
        sys.exit(errno.EINVAL)
        
    # Indicate start of the script by blinking LED 4 on the FlockBoard
    flocklab.led_blink(led_path, 100, 100)
    if debug:
        logger.debug("Changed blink status of LED 4.")
        
    errors = []
    
    # Check if SD card is mounted ---
    if not flocklab.is_sdcard_mounted():
        msg = "SD card is not mounted."
        errors.append(msg)
        logger.error(msg)
        # Output error and exit:
        rs = errchk_exit(led_path, errors, logger, flocklab.SUCCESS)
        sys.exit(rs)
        
    # Get info from XML ---
    # Get xml file for current test, find out slot number, platform and image location:
    slotnr = None
    platform = None
    imagepath = []
    operatingsystem = None
    xmlfilename = "%s%d/config.xml" % (config.get("observer", "testconfigfolder"), testid)
    try:
        tree = ElementTree()
        tree.parse(xmlfilename)
        rs = tree.find('obsTargetConf')
        if rs != None:
            slotnr = int(rs.find('slotnr').text)
            platform = rs.find('platform')
            #FlockDAQ = rs.find('FlockDAQ').text
            if platform != None:
                platform = platform.text.lower()
            imagefiles_to_process = rs.findall('image')
            for img in imagefiles_to_process:
                imagepath.append(img.text)
            operatingsystem = rs.find('os')
            if operatingsystem != None:
                operatingsystem = operatingsystem.text.lower()
        else:
            msg = "Could not find element <obsTargetConf> in %s" % xmlfilename
            errors.append(msg)
            logger.error(msg)
    except (IOError) as err:
        msg = "Could not find or open XML file."
        logger.error(msg)
    
    # Activate interface ---
    if slotnr:
        flocklab.tg_interface_set(slotnr)
        if debug:
            logger.debug("Activated interface %d."%slotnr)
    else:
        # Assume that the interface is still activated.
        slotnr = flocklab.tg_interface_get()
        msg = "Could not activate interface because slot number could not be determined. Working on currently active interface %d."%slotnr
        logger.error(msg)
    
    # Stop serial service ---
    # This has to be done before turning off power since otherwise the service will encounter errors due to disappearing devices.
    cmd = ['flocklab_serial.py', '--stop', '--testid=%d' % testid]
    if debug:
        cmd.append('--debug')
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (out, err) = p.communicate()
    rs = p.returncode
    if (rs not in (flocklab.SUCCESS, errno.ENOPKG)):
        msg = "Error %d when trying to stop serial service."%rs
        errors.append(msg)
        logger.error(msg)
    else:
        if debug:
            logger.debug("Stopped serial service.")
    
    # Turn off target power (normal and usb) ---
    if slotnr != None:
        flocklab.tg_pwr_set(slotnr, 0)
        if debug:
            logger.debug("Turned power off.")
        flocklab.tg_usbpwr_set(slotnr, 0)
        if debug:
            logger.debug("Turned USB power off.")
    else:
        msg = "Could not turn off power. Test image might thus still be running."
        errors.append(msg)
        logger.error(msg)
        
    # Reset all remaining services ---
    # This is done regardless of earlier errors.
    # For all remaining services: don't stop them but remove all pending jobs and flush the output buffers and stop the database daemon:
    services = {
#'flocklab_powerprofiling':['powerprofiling','Powerprofiling'], 
#'flocklab_gpiosetting':['gpio_setting','GPIO setting'],
#'flocklab_gpiomonitor':['gpio_monitor','GPIO monitoring']
}
    if FlockDAQ != "true":
        cmd = ['flocklab_scheduler.py', '--remove', '--testid=%d' % testid]
        p = subprocess.Popen(cmd, stdout=open('/dev/null', 'w'), stderr=subprocess.STDOUT)
        (out, err) = p.communicate()
        rs = p.returncode
        if (rs not in (flocklab.SUCCESS,)):
            msg = "Error when trying to remove test from observer scheduler."
            errors.append(msg)
            logger.error(msg)
            if debug:
                logger.error("Tried to start with: %s"%(str(cmd)))
        errors.extend(flocklab.stop_services(services, logger, testid, debug))
    else:
        # stop potentially running daq config daemon
        killtimeout = 10
        while killtimeout > 0:
            cmd = ['pkill', '-SIGINT', '-f', '^flocklab_config_daemon']
            p = subprocess.Popen(cmd, stdout=open('/dev/null', 'w'), stderr=subprocess.STDOUT)
            (out, err) = p.communicate()
            killtimeout = killtimeout - 1
            if p.returncode == 0: # there was a config_daemon process
                time.sleep(1)
            else:
                break
        # put FPGA to route through mode
        daq_port = config.get("daq","serialport")
        if (os.path.exists(daq_port)):
            serDaq = serial.Serial(daq_port, 1000000, timeout=1)
            # stop test
            stopCmd = chr(int('0' + '100' + '0000',2))
            serDaq.write(stopCmd)
            # sleep for 1 second, so the there is enough time to fully transmit possible data in the SRAM (up to 250k*32Bit) over SPI to the database daemon
            time.sleep(1)
            if debug:
                logger.debug("Stopped DAQ test.")
        
        # NOTE: BSL lines to program the target are routed through the FPGA, script will therefore fail without setting route through to on
        # stop database daemon
        cmd = ['flocklab_dbd', '-stop', '--testid=%d' % testid, '--service=flockdaq']
        #p = subprocess.Popen(cmd, stdout=open('/dev/null', 'w'), stderr=subprocess.STDOUT)
        #(out, err) = p.communicate()
        #rs = p.returncode
        rs = flocklab.SUCCESS
        if (rs not in (flocklab.SUCCESS,)):
            msg = "Error when trying to stop database daemon for flockdaq service."
            errors.append(msg)
            logger.error(msg)
            if debug:
                logger.error("Tried to start with: %s"%(str(cmd)))
        # wait some time until dbd has finished
        dbd_max_wait_count = int(config.get("daq", "dbd_max_wait_count"))
        while dbd_max_wait_count > 0:
            p = subprocess.Popen(['pgrep', '-f', 'dbd_flockdaq'], stdout=subprocess.PIPE)
            out, err = p.communicate(None)
            if (out != None) and len(out)>0:
                time.sleep(1)
            else:
                logger.debug("dbd finished after %d seconds"%(int(config.get("daq", "dbd_max_wait_count")) - dbd_max_wait_count))
                break
            dbd_max_wait_count = dbd_max_wait_count - 1
        #setting route through on
        if (serDaq.isOpen()):
            routeCmd = chr(int('0' + '000' + '1111',2))
            serDaq.write(routeCmd)
            if debug:
                logger.debug("Configured DAQ to route through mode.")
            serDaq.close()
        
    # Stop Moterunner LIP proxy:
    if (operatingsystem == 'moterunner'):
        cmd = ['pkill', '-f', 'lip-proxy']
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (out, err) = p.communicate()
        if p.returncode == 0:
            if debug:
                logger.debug("Killed Moterunner LIP proxy.")
        
    
    # Flash target with default image ---
    if slotnr and platform:
        #if (platform in ('tinynode', 'tmote', 'opal', 'iris', 'mica2', 'wismote', 'cc430', 'acm2', 'openmote','dpp')):
            core = 0
            while True:
                try:
                    imgfile = config.get("defaultimages", "img%d_%s"%(core,platform))
                    optional_reprogramming = False
                except configparser.NoOptionError:
                    try:
                        imgfile = config.get("defaultimages", "optional_img%d_%s"%(core,platform))
                        optional_reprogramming = True
                    except configparser.NoOptionError:
                        break
                cmd = ['tg_prog.py', '--image=%s%s'%(config.get("observer", "templatesfolder"), imgfile), '--target=%s'%(platform), '--core=%d' % core]
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                (out, err) = p.communicate()
                rs = p.returncode
                if (rs != flocklab.SUCCESS):
                    msg = "Could not flash target with default image because error %d occurred."%rs
                    if not optional_reprogramming:
                        errors.append(msg)
                    logger.error(msg)
                    if debug:
                        logger.error("Tried reprogramming with %s"%(str(cmd)))
                else:
                    if debug:
                        logger.debug("Reprogrammed target with default image.")
                core = core + 1
        #else:
        #    msg = "Could not flash target with default image because platform %s is unknown."%platform
        #    errors.append(msg)
        #    logger.error(msg)
    elif len(imagepath) > 0:
        msg = "Could not flash target with default image because slot number and/or platform could not be determined."
        if debug:
            logger.warn(msg)
    # Set voltage to maximum, turn target off ---
    if slotnr != None:
        #if flocklab.tg_pwr_get(slotnr) != 1:
        #    flocklab.tg_pwr_set(slotnr, 1)
        msg = None
        for i in range(0,5):
            try:
                flocklab.tg_volt_set(33, config.get("observer", "tg_pwr_force_pwm"))
                break
            except (IOError) as err:
                msg = "Error when setting target voltage to 33: %s"%(str(err))
        if msg:
            errors.append(msg)
            logger.error(msg)
        # Turn target off
        if flocklab.tg_pwr_get(slotnr) != 0:
            flocklab.tg_pwr_set(slotnr, 0)
    
    # Remove config directory ---
    if os.path.exists("%s%d" % (config.get("observer", "testconfigfolder"), testid)):
        shutil.rmtree("%s%d" % (config.get("observer", "testconfigfolder"), testid))

    if FlockDAQ == "true":
        p = subprocess.Popen(['echo "out set" > %s' % config.get("daq","fpga_reset")], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        time.sleep(1)
        p = subprocess.Popen(['echo "out clear" > %s' % config.get("daq","fpga_reset")], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        p = subprocess.Popen(['modprobe -rf daq_spi'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    
    # stop gps log
    #rs = subprocess.call('/home/root/mmc/gpsdop/gpsdoplog.sh stop', shell=True)
    
    # Error checking ---
    rs = errchk_exit(led_path, errors, logger)
    sys.exit(rs)
    
### END main()

if __name__ == "__main__":
    main(sys.argv[1:])
