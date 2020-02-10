#! /usr/bin/env python3

import os, sys, getopt, errno, subprocess, time, syslog
import lib.flocklab as flocklab
from lib.flocklab import SUCCESS


maxretries = 5      # Number of times the script retries to read when no serial ID was read.
searchtime = 0.1    # How long to wait for master search


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
# Usage
#
##############################################################################
def usage():
    print("Usage: %s [--target=<int>] [--searchtime=<float>] [--maxretries=<int>] [--help] [--version]" %sys.argv[0])
    print("Get serial ID of target adaptor(s).")
    print("Options:")
    print("  --target\tOptional. If set, the serial ID of the requested target is fetched. Otherwise ID's of all targets are fetched.")
    print("  --searchtime\tOptional. If set, standard time of %.1fs for waiting for the ID search is overwritten." %searchtime)
    print("  --maxretries\tOptional. If set, standard number of retries of %d for reading an ID is overwritten." %maxretries)
    print("  --help\tOptional. Print this help.")
    print("  --version\tOptional. Print version number of software and exit.")
### END usage()



##############################################################################
#
# Main
#
##############################################################################
def main(argv):

    target = None
    global searchtime
    global maxretries
        
    # Open the syslog:
    syslog.openlog('tg_serialid', syslog.LOG_CONS | syslog.LOG_PID | syslog.LOG_PERROR, syslog.LOG_USER)

    # Get command line parameters.
    try:
        opts, args = getopt.getopt(argv, "hvt:s:m:", ["help", "version", "target=", "searchtime=", "maxretries="])
    except (getopt.GetoptError) as err:
        syslog.syslog(syslog.LOG_ERR, str(err))
        usage()
        sys.exit(errno.EINVAL)
    for opt, arg in opts:
        if opt in ("-t", "--target"):
            try:
                target = int(arg)
                if ( (target < 1) or (target > 4) ):
                    raise ValueError
            except:
                syslog.syslog(syslog.LOG_ERR, "Wrong API usage: %s" %str(arg))
                usage()
                sys.exit(errno.EINVAL)
                
        elif opt in ("-s", "--searchtime"):
            try:
                searchtime = float(arg)
                if (searchtime <= 0.0):
                    raise ValueError
            except:
                syslog.syslog(syslog.LOG_ERR, "Wrong API usage: %s" %str(arg))
                usage()
                sys.exit(errno.EINVAL)
        
        elif opt in ("-m", "--maxretries"):
            try:
                maxretries = int(arg)
                if (maxretries < 0):
                    raise ValueError
            except:
                syslog.syslog(syslog.LOG_ERR, "Wrong API usage: %s" %str(arg))
                usage()
                sys.exit(errno.EINVAL)
            
        elif opt in ("-h", "--help"):
            usage()
            sys.exit(SUCCESS)
        
        elif opt in ("-v", "--version"):
            print(version)
            sys.exit(SUCCESS)
        
        else:
            print("Wrong API usage")
            syslog.syslog(syslog.LOG_ERR, "Wrong API usage")
            usage()
            sys.exit(errno.EINVAL)
    
    # Check if module loaded
    p = subprocess.Popen(["lsmod"], stdout=subprocess.PIPE, universal_newlines=True)
    out = p.communicate()[0]
    if not "w1_gpio" in out:
        err = "kernel module w1_gpio not loaded"
        print(err)
        syslog.syslog(syslog.LOG_ERR, err)
        sys.exit(errno.ENXIO)
    
    # Enable MUX
    flocklab.tg_mux_en()
    
    # Save currently selected target and enable state
    sel_target = flocklab.tg_get_selected()
    tg_is_enabled = flocklab.tg_en_state()
    
    # Enable target (required for backwards compatibility with old target adapters, otherwise GND_sensed is not connected!)
    flocklab.tg_en()
    
    # Get the serial ID of the requested targets:
    if (target == None):
        targets = [1,2,3,4]
    else:
        targets = [target]
    for target in targets:
        # Remove all stored serial ID's:
        FILE = open('/sys/bus/w1/devices/w1_bus_master1/w1_master_slaves', 'r')
        lines = FILE.readlines()
        FILE.close()
        if (lines[0].startswith("not found.") == False):
            for line in lines:
                FILE = open('/sys/bus/w1/devices/w1_bus_master1/w1_master_remove', 'w')
                FILE.write(line)
                FILE.close()
        
        # Turn on interface:
        if flocklab.tg_select(target) != SUCCESS:
            err = "Could not enable interface for target %i." %target
            print(err)
            syslog.syslog(syslog.LOG_ERR, err)
            sys.exit(errno.EFAULT)
        # Read out serial ID:
        retries = 0
        while (retries < maxretries):
            FILE = open('/sys/bus/w1/devices/w1_bus_master1/w1_master_search', 'w')
            FILE.write(str(1))
            FILE.close()
            time.sleep(searchtime)
            FILE = open('/sys/bus/w1/devices/w1_bus_master1/w1_master_slaves', 'r')
            sid = FILE.readline()
            FILE.close()
            if not sid.startswith("not found."):
                break
            retries += 1
        print("%i: %s" %(target, sid.strip()))
        
    flocklab.tg_select(sel_target)
    flocklab.tg_en(tg_is_enabled)
    
    sys.exit(SUCCESS)
    
### END main()

if __name__ == "__main__":
    main(sys.argv[1:])
