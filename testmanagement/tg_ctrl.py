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
    print("  --target, -t\t\tget the currently selected (active) target slot")
    print("  --voltage, -v\t\tset the target voltage (1.1 - 3.6)")
    print("  --mux, -m\t\tenable or disable the MUX")
    print("  --actuation, -a\tenable or disable actuation")
    print("  --reset, -r\t\treset the target")
    print("  --help, -h\t\tOptional. Print this help.")
### END usage()


##############################################################################
#
# Main
#
##############################################################################
def main(argv):
    
    # Get command line parameters
    try:
        # Note: a ':' indicates that the option requires an argument
        opts, args = getopt.getopt(argv, "hedprs:m:a:tv:", ["help", "enable", "disable", "power", "reset", "select=", "mux=", "actuation=", "target", "voltage="])
    except getopt.GetoptError as err:
        print(str(err))
        sys.exit(errno.EINVAL)
    
    # Parse arguments and execute commands
    for opt, arg in opts:
        if opt in ("-e", "--enable"):
            flocklab.tg_en(True)
            flocklab.tg_pwr_en(True)
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
        elif opt in ("-t", "--target"):
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
        elif opt in ("-m", "--mux"):
            if arg.lower() in ("e", "en", "enable", "1", "on"):
                flocklab.tg_mux_en(True)
            else:
                flocklab.tg_mux_en(False)
        elif opt in ("-a", "--act", "--actuation"):
            if arg.lower() in ("e", "en", "enable", "1", "on"):
                flocklab.tg_act_en(True)
            else:
                flocklab.tg_act_en(False)
        elif opt in ("-h", "--help"):
            usage()
            sys.exit(flocklab.SUCCESS)
### END main()

if __name__ == "__main__":
    main(sys.argv[1:])
