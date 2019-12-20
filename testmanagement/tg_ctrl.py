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
    print("  --action, -a\tpossible values:")
    print("\t\t   enable\tenable the target power")
    print("\t\t   disable\tdisable the target power")
    print("\t\t   state\tpoll the current power state")
    print("\t\t   select\tselect the target specified with --target")
    print("\t\t   active\tget the currently selected target adapter")
    print("\t\t   volt\tset the target voltage")
    print("  --target, -t\tOptional. If set, the requested target's interface is enabled. If no target is given, all target's interfaces are turned off.")
    print("  --help, -h\tOptional. Print this help.")
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
        opts, args = getopt.getopt(argv, "ha:t:v:", ["help", "action", "target", "vcc"])
    except getopt.GetoptError as err:
        print(str(err))
        sys.exit(errno.EINVAL)
    
    # Parse arguments
    for opt, arg in opts:
        if opt in ("-a", "--action"):
            action = arg
        elif opt in ("-t", "--target"):
            try:
                target = int(arg)
                if ((target < 1) or (target > 4)):
                    raise ValueError
            except:
                print("Invalid target")
                sys.exit(errno.EINVAL)
        elif opt in ("-v", "--vcc"):
            try:
                vcc = float(arg)
            except:
                print("Invalid voltage")
                sys.exit(errno.EINVAL)
        elif opt in ("-h", "--help"):
            usage()
            sys.exit(flocklab.SUCCESS)
    
    # Check supplied arguments
    if action is None:
        print("No action specified")
        sys.exit(errno.EINVAL)

    if action in "enable":
        flocklab.tg_pwr_en(True)
    elif action in "disable":
        flocklab.tg_pwr_en(False)
    elif action in "state":
        if flocklab.tg_pwr_state():
            print("on")
        else:
            print("off")
    elif action in "active":
        print(flocklab.tg_get_selected())
    elif action in ("select", "sel"):
        if target is None:
            print("No target specified")
            sys.exit(errno.EINVAL)
        flocklab.tg_select(target)
    elif action in ("volt", "voltage"):
        if flocklab.tg_set_vcc(vcc) != flocklab.SUCCESS:
            print("Failed to set target voltage.")
            sys.exit(errno.EINVAL)
    else:
        print("unknown action '%s'" % action)
        sys.exit(errno.EINVAL)
    
    sys.exit(flocklab.SUCCESS)
    
    
### END main()

if __name__ == "__main__":
    main(sys.argv[1:])
