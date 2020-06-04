#!/usr/bin/env python3

"""
Copyright (c) 2020, ETH Zurich, Computer Engineering Group
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

* Redistributions of source code must retain the above copyright notice, this
  list of conditions and the following disclaimer.

* Redistributions in binary form must reproduce the above copyright notice,
  this list of conditions and the following disclaimer in the documentation
  and/or other materials provided with the distribution.

* Neither the name of the copyright holder nor the names of its
  contributors may be used to endorse or promote products derived from
  this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
POSSIBILITY OF SUCH DAMAGE.

Author: Reto Da Forno
"""

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
    print("  --reset-low\t\tset the target reset low")
    print("  --temperature\t\tget the current temperature (SHT31 sensor on the observer)")
    print("  --humidity\t\tget the current humidity (SHT31 sensor on the observer)")
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
        opts, args = getopt.getopt(argv, "hedprs:m:a:tv:", ["help", "enable", "disable", "power", "reset", "select=", "mux=", "actuation=", "target", "voltage=", "reset-low", "temperature", "humidity"])
    except getopt.GetoptError as err:
        print(str(err))
        sys.exit(errno.EINVAL)

    # Parse arguments and execute commands
    for opt, arg in opts:

        if opt in ("-e", "--enable"):
            flocklab.tg_en(True)
            flocklab.tg_pwr_en(True)
            print("target enabled")

        elif opt in ("-d", "--disable"):
            flocklab.tg_pwr_en(False)
            flocklab.tg_act_en(False)
            flocklab.tg_en(False)
            print("target disabled")
            print("actuation disabled")

        elif opt in ("-p", "--power"):
            if flocklab.tg_pwr_state() > 0:
                print("power state: ON")
                print("target voltage: %.3fV" % flocklab.tg_get_vcc())
            else:
                print("power state: OFF")

        elif opt in ("-r", "--reset"):
            flocklab.tg_reset()
            print("target reset")

        elif opt in ("--reset-low"):
            flocklab.tg_reset(False)
            print("holding target in reset state")

        elif opt in ("-t", "--target"):
            print("active target slot: %d" % flocklab.tg_get_selected())

        elif opt in ("-s", "--select", "--sel"):
            try:
                target = int(arg)
                if ((target < 1) or (target > 4)):
                    raise ValueError
                flocklab.tg_select(target)
                print("target %d selected" % target)
            except:
                print("invalid target slot")

        elif opt in ("-v", "--vcc", "--voltage"):
            try:
                vcc = float(arg)
                if flocklab.tg_set_vcc(vcc) != flocklab.SUCCESS:
                    print("Failed to set target voltage.")
                else:
                    print("target voltage set to %.3fV" % vcc)
            except:
                print("invalid voltage")

        elif opt in ("-m", "--mux"):
            if arg.lower() in ("e", "en", "enable", "1", "on"):
                flocklab.tg_mux_en(True)
                print("MUX enabled")
            else:
                flocklab.tg_mux_en(False)
                print("MUX disabled")

        elif opt in ("-a", "--act", "--actuation"):
            if arg.lower() in ("e", "en", "enable", "1", "on"):
                flocklab.tg_act_en(True)
                print("actuation enabled")
            else:
                flocklab.tg_act_en(False)
                print("actuation disabled")

        elif opt in ("-h", "--help"):
            usage()
            sys.exit(flocklab.SUCCESS)

        elif opt in ("--temperature"):
            data = flocklab.get_temp_humidity()
            print("temperature: %.2f C" % (data[0]))

        elif opt in ("--humidity"):
            data = flocklab.get_temp_humidity()
            print("humidity: %.1f%%" % data[1])
### END main()

if __name__ == "__main__":
    main(sys.argv[1:])
