#!/usr/bin/env python3

import os, sys, shutil

# Default daemon parameters.
# File mode creation mask of the daemon.
UMASK = 0
# Default working directory for the daemon.
WORKDIR = "/"
# Default maximum for the number of available file descriptors.
MAXFD = 1024
# The standard I/O file descriptors are redirected to /dev/null by default.
if (hasattr(os, "devnull")):
    REDIRECT_TO = os.devnull
else:
    REDIRECT_TO = "/dev/null"


##############################################################################
#
# Function to create a daemon out of the program.
#
# Input: 
#    pidfile: File to store the PID in. This files needs to be deleted when 
#        closing the daemon
#    closedesc: When set to True, all file descriptors will be closed.
#
##############################################################################
def daemonize(pidfile, closedesc):
    """Detach a process from the controlling terminal and run it in the
    background as a daemon.
    """

    # do the UNIX double-fork magic, see Stevens' "Advanced
    # Programming in the UNIX Environment" for details (ISBN 0201563177)
    try:
        pid = os.fork()
        if pid > 0:
            # exit first parent
            sys.exit(0)
    except OSError as err:
        print("fork #1 failed: %d (%s)" % (err.errno, err.strerror), file=sys.stderr)
        sys.exit(1)

    # decouple from parent environment
    os.chdir("/")   #don't prevent unmounting....
    os.setsid()
    os.umask(0)

    # do second fork
    try:
        pid = os.fork()
        if pid > 0:
            # exit from second parent, print eventual PID before
            #print "Daemon PID %d" % pid
            if pidfile != None:
                if not os.path.isdir(os.path.dirname(pidfile)):
                    shutil.rmtree(pidfile, ignore_errors=True)
                if not os.path.exists(os.path.dirname(pidfile)):
                    os.makedirs(os.path.dirname(pidfile))
            	open(pidfile,'w').write("%d"%pid)
            sys.exit(0)
    except OSError as err:
        print("fork #2 failed: %d (%s)" % (err.errno, err.strerror), file=sys.stderr)
        sys.exit(1)

    if closedesc:
        # Close all open file descriptors.  This prevents the child from keeping
        # open any file descriptors inherited from the parent.  
        try:
            maxfd = os.sysconf('SC_OPEN_MAX')
        except (AttributeError, ValueError):
            maxfd = MAXFD
        
        # Iterate through and close all file descriptors.
        for fd in range(0, maxfd):
            try:
                os.close(fd)
            except OSError:    # ERROR, fd wasn't open to begin with (ignored)
                pass
    
        # Redirect the standard I/O file descriptors to the specified file.  
        # This call to open is guaranteed to return the lowest file descriptor,
        # which will be 0 (stdin), since it was closed above.
        os.open(REDIRECT_TO, os.O_RDWR)    # standard input (0)
    
        # Duplicate standard input to standard output and standard error.
        os.dup2(0, 1)            # standard output (1)
        os.dup2(0, 2)            # standard error (2)

### END daemonize()
