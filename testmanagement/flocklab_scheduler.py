#! /usr/bin/env python3

import os, sys, getopt, socket, time, subprocess, multiprocessing, queue, threading, errno, traceback, pickle, tempfile
from syslog import *
import lib.daemon as daemon
import lib.flocklab as flocklab


pidfile         = None
config          = None
debug           = False
current_test    = 0
last_collection = 0

def isDaemonRunning():
    try:
        pid = int(open(pidfile,'r').read())
        # Signal the process to stop:
        if (pid > 0):
            try:
                os.kill(pid, 0)
            except OSError:
                os.remove(pidfile)
                return False
        return True
    except ValueError:
        return False # empty pid file ?
    except (IOError, OSError):
        return False # no pid file ?

##############################################################################
#
# run_scheduler
#
##############################################################################
def scheduler_thread(msgQueue):
    schedule = []
    syslog(LOG_INFO, "Scheduler thread started.")
    print("Scheduler thread started.")

    while True:
        if len(schedule) == 0:
            _waittime = None
        else:
            _waittime = min([token["switchtime"] for token in schedule]) - time.time()
            if _waittime < 0:
                _waittime = 0
            syslog(LOG_INFO, "Action scheduled in %f seconds." % _waittime)
        try:
            newtoken = msgQueue.get(True, _waittime)
            if newtoken["action"] == "add":
                schedule.append(newtoken)
                syslog(LOG_INFO, "Add token, schedule is %s" % str(schedule))
            elif newtoken["action"] == "remove":
                flocklab.stop_gpio_tracing()
                flocklab.stop_pwr_measurement()
                flocklab.collect_pwr_measurement_data(str(newtoken["testid"]))
                current_test = 0
                for r in [test for test in schedule if test["testid"] == newtoken["testid"]]:
                    schedule.remove(r)
            elif newtoken["action"] == "stop":
                break
            else:
                syslog(LOG_ERROR,"Unknown action %s" % newtoken["action"])
        except Queue.Empty:
            pass

        now = time.time()
        syslog(LOG_INFO, "Time now: %s" % now)
        for s in [test for test in schedule if test["switchtime"] < now]:
            syslog(LOG_INFO, "Switch to test id %d." % s["testid"])
            current_test = s["testid"]
            last_collection = time.time()
            xml_file = "%s%d/config.xml" % (config.get("observer","testconfigfolder"), newtoken["testid"])
            log_file = "%s%d/" % (config.get("observer","obsdbfolder"), newtoken["testid"])
            flocklab.start_pwr_measurement()
            flocklab.tg_reset(0.0005)
            syslog(LOG_INFO, "Reset Target.")
            flocklab.start_gpio_tracing(xml_file, log_file)
            schedule.remove(s)

        #if current_test != 0 and (now - last_collection) > 120:
        #    syslog(LOG_INFO, "Collect data for test %d" % current_test)
        #    flocklab.collect_pwr_measurement_data(str(current_test))
        #    last_collection = time.time()

    syslog(LOG_INFO, "Scheduler thread stopped.")

##############################################################################
#
# run_scheduler
#
##############################################################################
def run_scheduler():
    try:
        os.remove(socketfile)
    except OSError:
        pass
    daemon.daemonize(pidfile=pidfile, closedesc=True)
    syslog(LOG_INFO, "Daemonized process")
    # start scheduler thread
    msgQueue = multiprocessing.Queue()
    th = threading.Thread(target = scheduler_thread, args=(msgQueue,))
    th.daemon = True
    th.start()
    
    # open socket
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.bind(socketfile)
    s.listen(1)
    while True:
        conn, addr = s.accept()
        try:
            f = conn.makefile('rb')
            data = pickle.load(f)
            if not data:
                continue
            if isinstance(data, dict) and "action" in data:
                if data["action"] == "add":
                    syslog(LOG_INFO, "Received <add> token.")
                    # inform scheduler thread
                    msgQueue.put(data)
                elif data["action"] == "remove":
                    syslog(LOG_INFO, "Received <remove> token.")
                    # inform scheduler thread
                    msgQueue.put(data)
                elif data["action"] == "stop":
                    syslog(LOG_INFO, "Received <stop> token.")
                    # inform scheduler thread
                    msgQueue.put(data)
                    th.join(10)
                    break
        except socket.error:
            syslog(LOG_INFO, "Socket error")
        except EOFError:
            pass
        f.close()
        conn.close()
    syslog(LOG_INFO, "Stopped scheduler.")

##############################################################################
#
# Usage
#
##############################################################################
def usage():
    print("Usage: %s [option] [--testid=<int>] [--switchtime=<int>] [--debug]" % sys.argv[0])
    print("Options:")
    print("  --add\t\t\tAdd a switch job. If there is no scheduler running, a new daemon instance will be started.")
    print("  --remove\t\tRemove an existing switch job.")
    print("  --stop\t\tStop the scheduler daemon.")
    print("  --start\t\tStart the scheduler daemon.")
    print("  --help\t\tOptional. Print this help.")
    print("Parameters:")
    print("  --testid=<int>\tID of the test.")
    print("  --switchtime=<int>\tTime at which the switch-over should take place (Unix timestamp), only needed for the --add option.")
    print("  --debug\t\tOptional. Print debug messages to log.")
    return(0)
### END usage()

def reset_thread(reset_time):
    usleep = 0.0005
    now = time.time()
    print("thread started, time: %d, now: %d" % (reset_time, now))
    while reset_time > now:
        now = time.time()

    flocklab.tg_reset(usleep)
    syslog(LOG_DEBUG, "Reset successful, tests have been started now.")
### END reset_thread()

##############################################################################
#
# Main
#
##############################################################################
def main(argv):
    
    global pidfile
    global config
    global debug
    global socketfile
    
    action = None
    testid = None
    switchtime = None
    socketfile = "/var/run/flocklab_scheduler.sock"
    
    # Open the syslog:
    openlog('flocklab_scheduler', LOG_CONS | LOG_PID | LOG_PERROR, LOG_USER)
    
    # Get config:
    config = flocklab.get_config()
    if not config:
        logger.warn("Could not read configuration file. Exiting...")
        sys.exit(errno.EAGAIN)

    # Get command line parameters.
    try:
        opts, args = getopt.getopt(argv, "arsthdi:w:", ["add", "remove", "stop", "start", "help", "debug", "testid=", "switchtime="])
    except (getopt.GetoptError) as err:
        syslog(LOG_ERR, str(err))
        usage()
        sys.exit(errno.EINVAL)

    for opt, arg in opts:
        if opt in ("-h", "--help"):
            usage()
            sys.exit(flocklab.SUCCESS)
        elif opt in ("-d", "--debug"):
            syslog(LOG_INFO, "Debug option detected.")
            debug = True
        elif opt in ("-a", "--add"):
            action = 'add'
        elif opt in ("-r", "--remove"):
            action = 'remove'
        elif opt in ("-s", "--stop"):
            action = 'stop'
        elif opt in ("-t", "--start"):
            action = 'start'
        elif opt in ("-i", "--testid"):
            testid = int(arg)
        elif opt in ("-w", "--switchtime"):
            try:
                switchtime = int(arg)
            except ValueError:
                print("Invalid switch time")
        else:
            syslog(LOG_ERR, "Wrong API usage")
            usage()
            sys.exit(errno.EINVAL)
    
    # check parameters for requested action 
    if action is None:
        m = "Wrong API usage"
        syslog(LOG_ERR, m)
        usage()
        sys.exit(errno.EINVAL)
    
    if action in ("add", "remove") and testid is None:
        m = "Test id missing for requested action %s" % action
        syslog(LOG_ERR, m)
        sys.exit(errno.EINVAL)

    pidfile = "%s%s" %(config.get("observer", "pidfolder"), "flocklab_scheduler.pid")
    
    if action == "start":
        """ Check if daemon option is on. If on, reopen the syslog without the ability to write to the console.
        If the daemon option is on, later on the process will also be daemonized.
        """
        if not isDaemonRunning():
            closelog()
            openlog('flocklab_scheduler', LOG_CONS | LOG_PID, LOG_USER)
            run_scheduler()
        else:
            syslog(LOG_DEBUG, "Scheduler was already started")

    #if action == "add":
    if False:
        print("Start thread with switchtime: %d" % switchtime)
        syslog(LOG_DEBUG, "Start thread with switchtime: %d" % switchtime)
        th = threading.Thread(target = reset_thread, args=(switchtime,))
        th.start()
        sys.exit(flocklab.SUCCESS)
    
    #if action in ("remove", "stop"):    
    if action in ("add", "remove", "stop"):
        if not isDaemonRunning():
            if action == "stop":
                syslog(LOG_DEBUG, "Scheduler was not running.")
                sys.exit(flocklab.SUCCESS)
            else:
                # start daemon
                cmd = [sys.argv[0], '--start']
                if debug:
                    cmd.append("--debug")
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
                p.wait()
        for i in xrange(5):
            try:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.connect(socketfile)
                s.send(pickle.dumps({"action":action, "testid":testid, "switchtime": switchtime}))
                s.close()
                break
            except:
                time.sleep(0.5)
        sys.exit(flocklab.SUCCESS)
### END main()


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except SystemExit:
        pass
    except:
        syslog(LOG_ERR, "Encountered error in line %d: %s: %s: %s\n\n--- traceback ---\n%s--- end traceback ---\n\nCommandline was: %s" % (traceback.tb_lineno(sys.exc_info()[2]), str(sys.exc_info()[0]), str(sys.exc_info()[1]), str(traceback.print_tb(sys.exc_info()[2])), traceback.format_exc(), str(sys.argv)))
        sys.exit(errno.EAGAIN)
