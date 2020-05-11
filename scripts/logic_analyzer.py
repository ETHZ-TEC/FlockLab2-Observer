#!/usr/bin/python3

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

"""
Helper script that utilizes fl_logic on a BeagleBone to collect signal traces

Notes:
- 8 pins are traces (P8.39 - P8.46)
- pin P8.40 can also be used as an output (fl_logic will set it high at the beginning of the test and low at the end)

How to:
- make sure the beaglebone is accessible via SSH (adjust your ssh config to include the key file and port number)
- make sure fl_logic is installed on the beaglebone (cd observer/pru/fl_logic && sudo make install)
- The pins need to be configured as PRU input pins. Either install an overlay or enable the universal cape and use the following command to configure each pin:
  config-pin -a P839 pruin
- install the flocklab-tools on your computer:
  python3 -m pip install flocklab-tools

"""

import sys
import os
import time
import getopt
import traceback
import subprocess
import flocklab


# --- config ---

host      = "fl-03"
outputdir = "/tmp/fl_logic_analyzer"
showplot  = True


def usage(argv):
    print("""Usage:
\t%s [options]\n
\t-H, --host\tthe host name or IP address of the BeagleBone
\t-o, --out\tthe output directory for the result files
""" % __file__)

# execute a command on the target beaglebone
def execute_cmd(command=None, return_output=True):
    if not command:
        return None
    cmd = ['ssh' , host, command]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    if return_output:
        out, err = p.communicate(None)
        rs = p.returncode
        if (rs != 0):
            print("failed to execute command '%s' on %s" % (command, host))
            sys.exit(2)
        return out


def transfer_file(filename):
    if not filename:
        return
    cmd = ['scp' , "%s:/tmp/%s" % (host, filename), outputdir]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    out, err = p.communicate(None)
    rs = p.returncode
    if (rs != 0):
        print("failed to retrieve file '%s'" % (filename))
        sys.exit(2)


def main(argv):
    global host, outputdir

    # Get command line parameters.
    try:
        opts, args = getopt.getopt(argv, "hH:o:", ["help", "host=", "out="])
    except getopt.GetoptError  as err:
        print(str(err), errno.EINVAL)
    for opt, arg in opts:
        if opt in ("-h", "--help"):
            usage(argv)
            sys.exit(0)
        elif opt in ("-H", "--host"):
            host = arg
        elif opt in ("-o", "--out"):
            outputdir = arg
        else:
            flocklab.error_logandexit("Unknown argument %s" % opt, errno.EINVAL)

    try:
        os.mkdir(outputdir)
    except FileExistsError:
        if not os.path.isdir(outputdir):
            print("failed to create output directory %s" % outputdir)
            sys.exit(1)

    out = execute_cmd("which fl_logic")
    if "/bin/fl_logic" not in out:
        print("fl_logic not found on target %s" % host)
        sys.exit(1)

    filename = "logic_trace_%d" % time.time()
    execute_cmd("fl_logic /tmp/%s 0 0 0xff 0 0x00000701" % filename, return_output=False)

    try:
        input("logic analyzer started... (press enter or ctrl+c to stop)\n")
    except KeyboardInterrupt:
        sys.stdout.write("\b\b")
        pass

    out = execute_cmd("pgrep -f fl_logic")
    try:
        pid = int(out)
    except:
        print("PID of fl_logic process not found")
        sys.exit(3)
    out = execute_cmd("kill -2 %d" % pid)
    print("sampling stopped")

    transfer_file(filename + ".csv")

    print("parsing results...")
    filename = outputdir + '/' + filename + ".csv"
    with open(filename, 'r') as csvinfile, open(outputdir + '/gpiotracing.csv', 'w') as csvoutfile:
        csvoutfile.write("timestamp,node_id,pin_name,value\n")
        for line in csvinfile.readlines():
            try:
                (timestamp, pin, val) = line.split(',', 2)
            except:
                print("failed to parse line %s" % line)
                continue
            csvoutfile.write("%s,1,%s,%s" % (timestamp, pin, val))
    os.remove(filename)
    if not os.path.isfile(outputdir + '/powerprofiling.csv'):
        with open(outputdir + '/powerprofiling.csv', 'w') as f:
            f.write("timestamp,observer_id,node_id,current_mA,voltage_V\n")   # create empty file to suppress warning of flocklab tools

    print("results stored in %s/gpiotracing.csv" % outputdir)

    print("generating plot...")
    flocklab.visualizeFlocklabTrace(outputdir, outputDir=outputdir, interactive=showplot)


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except Exception:
        print("Encountered error: %s\n%s" % (str(sys.exc_info()[1]), traceback.format_exc()))
