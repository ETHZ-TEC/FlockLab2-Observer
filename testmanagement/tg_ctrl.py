#! /usr/bin/env python3

##############################################################################
# target control script
# - select target
# - reset target
# - set target voltage
# - enable / disable power
##############################################################################

import os, sys, getopt, errno
import lib.flocklab as flocklab


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
    print("Usage: %s --action=<action> [--target=<int>] [--vcc=<float>] [--help]" %sys.argv[0])
    print("Options:")
    print("  --enable, -e\t\tenable the target power")
    print("  --disable, -d\t\tdisable the target power")
    print("  --power, -p\t\tpoll the current power state")
    print("  --select, -s\t\tselect the target slot (1 - 4)")
    print("  --active, -a\t\tget the currently selected target adapter")
    print("  --voltage, -v\t\tset the target voltage (1.1 - 3.6)")
    print("  --reset, -r\t\treset the target")
    print("  --help, -h\t\tOptional. Print this help.")
### END usage()


##############################################################################
#
# Main
#
##############################################################################
def main(argv):

    action = None
    target = None
    vcc    = 3.0
    
    # Get command line parameters
    try:
        # Note: a ':' indicates that the option requires an argument
        opts, args = getopt.getopt(argv, "hedprs:av:", ["help", "enable", "disable", "power", "reset", "select", "active", "voltage"])
    except getopt.GetoptError as err:
        print(str(err))
        sys.exit(errno.EINVAL)
    
    # Parse arguments and execute commands
    for opt, arg in opts:
        if opt in ("-e", "--enable"):
            flocklab.tg_pwr_en(True)
            flocklab.tg_en(True)
        elif opt in ("-d", "--disable"):
            flocklab.tg_pwr_en(False)
            flocklab.tg_en(False)
        elif opt in ("-p", "--power"):
            if flocklab.tg_pwr_state() > 0:
                print("power state: ON")
            else:
                print("power state: OFF")
        elif opt in ("-r", "--reset"):
            flocklab.tg_reset()
        elif opt in ("-a", "--active"):
            print("active target slot: %d" % flocklab.tg_get_selected())
        elif opt in ("-s", "--select", "--sel"):
            try:
                target = int(arg)
                if ((target < 1) or (target > 4)):
                    raise ValueError
                flocklab.tg_select(target)
            except:
                print("Invalid target slot")
        elif opt in ("-v", "--vcc", "--voltage"):
            try:
                vcc = float(arg)
                if flocklab.tg_set_vcc(vcc) != flocklab.SUCCESS:
                    print("Failed to set target voltage.")
            except:
                print("Invalid voltage")
        elif opt in ("-h", "--help"):
            usage()
            sys.exit(flocklab.SUCCESS)
### END main()

if __name__ == "__main__":
    main(sys.argv[1:])
