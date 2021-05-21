#! /usr/bin/env python3

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

import os, sys, time, errno, traceback, getopt, subprocess, signal
import lib.flocklab as flocklab
import lib.daemon as daemon


# globals
debug        = False
running      = True
pidfile      = None
jlinkswopath = '/opt/jlink/JLinkSWOViewerCLExe'
scriptname   = os.path.splitext(os.path.basename(__file__))[0]
waitfor      = "-----------------------------------------------"


##############################################################################
#
# Usage
#
##############################################################################
def usage():
    print("Usage: %s --output --platform [--cpuspeed] [--swospeed] [--stop] [--debug] [--help]" % sys.argv[0])
    print("Options:")
    print("  --output=<string>\t\toutput filename")
    print("  --platform=<string>\t\tplatform name (e.g. dpp2lora or nrf5)")
    print("  --cpuspeed\t\t\tThe CPU clock frequency of the target device.")
    print("  --swospeed\t\t\tThe SWO speed (baudrate).")
    print("  --stop\t\t\tOptional. Causes the program to stop a possibly running instance of the serial reader service.")
    print("   --debug\t\t\tOptional. Enable verbose logging.")
    print("  --help\t\t\tOptional. Print this help.")
### END usage()


##############################################################################
#
# sigterm_handler
#
##############################################################################
def sigterm_handler(signum, frame):
    global running
    running = False
### END sigterm_handler()


##############################################################################
#
# start_logger
#
##############################################################################
def start_logger(outputfile=None):
    logger = flocklab.get_logger(debug=debug)
    if not outputfile:
        logger.error("Invalid output file.")
        return flocklab.FAILED
    logger.debug("Writing STDIN to file %s..." % outputfile)
    # start logging
    try:
        with open(outputfile, 'w') as f:
            startfound = False
            if not waitfor:
                startfound = True
            # read from standard input in a loop
            for line in sys.stdin:
                line = line.rstrip()
                if "Shutting down" in line:
                    break
                if not startfound:
                    if waitfor in line and len(waitfor) == len(line):
                        startfound = True
                        logger.debug("Start sequence found.")
                        sys.stdin.flush()   # discard input
                else:
                    try:
                        f.write("%.7f,%s\n" % (time.time(), line))
                    except UnicodeEncodeError:
                        pass
    except Exception:
        logger.error("Encountered error: %s\n%s" % (str(sys.exc_info()[1]), traceback.format_exc()))
        return flocklab.FAILED
    logger.debug("Logging stopped.")
    return flocklab.SUCCESS
### END start_logger()


##############################################################################
#
# stop_logger
#
##############################################################################
def stop_logger():
    logger = flocklab.get_logger(debug=debug)
    # first, send sigterm to the JLink process
    pid = flocklab.get_pid(jlinkswopath)
    if pid > 0:
        logger.debug("Sending SIGTERM signal to JLink process %d..." % pid)
        try:
            os.kill(pid, signal.SIGTERM)
            os.waitpid(pid, 0)
        except OSError:
            pass
        # before continuing, wait a bit
        time.sleep(3)
    # take the first PID that isn't our PID
    pids = flocklab.get_pids(scriptname)
    for p in pids:
        if p != os.getpid():
            pid = p
            break
    if pid > 0:
        logger.debug("Sending SIGTERM signal to SWO logger process %d..." % pid)
        try:
            os.kill(pid, signal.SIGTERM)
            os.waitpid(pid, 0)
        except OSError:
            # process probably didn't exist -> ignore error
            logger.debug("Process %d does not exist." % pid)
    else:
        logger.debug("No daemon process found.")
    return flocklab.SUCCESS
### END stop_logger()


##############################################################################
#
# Main
#
##############################################################################
def main(argv):
    global pidfile
    global debug

    stop      = False
    filename  = None
    waitfor   = None
    logger    = False
    cpuspeed  = None
    swospeed  = None
    platform  = None

    # Get config:
    config = flocklab.get_config()
    if not config:
        flocklab.error_logandexit("Could not read configuration file.")

    # Get command line parameters.
    try:
        opts, args = getopt.getopt(argv, "eho:p:ls:b:", ["stop", "help", "output=", "platform=", "logger", "cpuspeed=", "swospeed=", "debug"])
    except(getopt.GetoptError) as err:
        flocklab.error_logandexit(str(err), errno.EINVAL)
    for opt, arg in opts:
        if opt in ("-h", "--help"):
            usage()
            sys.exit(flocklab.SUCCESS)
        elif opt in ("-o", "--output"):
            filename = arg
        elif opt in ("-p", "--platform"):
            platform = arg
        elif opt in ("-e", "--stop"):
            stop = True
        elif opt in ("-l", "--logger"):
            logger = True
        elif opt in ("--debug"):
            debug = True
        elif opt in ("-s", "--cpuspeed"):
            cpuspeed = flocklab.parse_int(arg)
            if cpuspeed < 1000000 or cpuspeed > 100000000:
                flocklab.error_logandexit("Invalid CPU speed '%s'." (arg), errno.EINVAL)
        elif opt in ("-b", "--swospeed"):
            swospeed = flocklab.parse_int(arg)
            if swospeed < 9600 or swospeed > 4000000:
                flocklab.error_logandexit("Invalid SWO speed '%s'." (arg), errno.EINVAL)
        else:
            flocklab.error_logandexit("Unknown option '%s'." % (opt), errno.EINVAL)

    pidfile = "%s/%s.pid" % (config.get("observer", "pidfolder"), scriptname)

    if stop:
        sys.exit(stop_logger())
    elif logger:
        sys.exit(start_logger(filename))

    # Check mandatory parameters:
    if not filename or not flocklab.jlink_mcu_str(platform):
        flocklab.error_logandexit("Invalid or missing arguments.", errno.EINVAL)

    if len(flocklab.get_pids(scriptname)) > 1:
        flocklab.error_logandexit("There is already an instance of %s running (PIDs: %s)." % (scriptname, str(flocklab.get_pids(scriptname))))

    # Create daemon process
    daemon.daemonize(pidfile=pidfile, closedesc=True)

    signal.signal(signal.SIGTERM, sigterm_handler)
    signal.signal(signal.SIGINT, sigterm_handler)

    logger = flocklab.get_logger(debug=debug)
    if not logger:
        flocklab.error_logandexit("Could not get logger.")

    logger.info("Starting SWO logger (output file: %s, platform: %s, cpu speed: %s)." % (filename, platform, str(cpuspeed)))

    # make sure MUX is enabled
    if not flocklab.tg_mux_state():
        flocklab.tg_mux_en(True)
        logger.debug("MUX enabled.")
    nrst_state = flocklab.tg_reset_state()
    if nrst_state == 0:
        flocklab.tg_reset()
        logger.debug("Target reset released.")

    cmd = [jlinkswopath, '-device', flocklab.jlink_mcu_str(platform)]
    if cpuspeed:
        cmd.append('-cpufreq')
        cmd.append(str(cpuspeed))
    if swospeed:
        cmd.append('-swofreq')
        cmd.append(str(swospeed))
    jlinkproc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    cmd = [config.get("observer", "swologger"), '--logger', '--output=%s' % filename]
    if debug:
        cmd.append("--debug")
    loggerproc = subprocess.Popen(cmd, stdin=jlinkproc.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # wait for the process to finish
    #rs = jlinkproc.wait()
    rs = loggerproc.wait()
    if rs != 0:
        logger.warning("SWO logger stopped with code %d." % rs)
    else:
        logger.info("SWO logger stopped.")

### END main()


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except Exception:
        flocklab.error_logandexit("Encountered error: %s\n%s\nCommand line was: %s" % (str(sys.exc_info()[1]), traceback.format_exc(), " ".join(sys.argv)))
        sys.exit(flocklab.FAILED)
