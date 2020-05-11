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

"""

import os, sys, getopt, signal, socket, time, subprocess, errno, queue, serial, select, multiprocessing, threading, traceback, struct
import lib.daemon as daemon
import lib.flocklab as flocklab


### Global variables ###
pidfile       = None
config        = None
isdaemon      = False
proc_list     = []                  # List with all running processes
dbbuf_proc    = []                  # Dbbuf process
msgQueueDbBuf = None                # Queue used to send data to the DB buffer


##############################################################################
#
# Usage
#
##############################################################################
def usage():
    print("Usage: %s --testid=<int> [--port=<string>] [--baudrate=<int>] [--socketport=<int>] [--stop] [--daemon] [--debug] [--help]" %sys.argv[0])
    print("Options:")
    print("  --testid=<int>\t\tID of the test.")
    print("  --port=<string>\t\tOptional. Port over which serial communication is done. Default is serial.")
    print("\t\t\t\tPossible values are: %s" % (str(flocklab.tg_port_types)))
    print("  --baudrate=<int>\t\tOptional. Baudrate of serial device. Default is 115200.")
    print("\t\t\t\tPossible values are: %s" % (" ".join([str(x) for x in flocklab.tg_baud_rates])))
    print("  --socketport=<int>\t\tOptional. If set, a server socket will be created on the specified port.")
    print("  --stop\t\t\tOptional. Causes the program to stop a possibly running instance of the serial reader service.")
    print("  --daemon\t\t\tOptional. If set, program will run as a daemon. If not specified, all output will be written to STDOUT and STDERR.")
    print("  --debug\t\t\tOptional. Print debug messages to log.")
    print("  --help\t\t\tOptional. Print this help.")
    return(0)
### END usage()


##############################################################################
#
# sigterm_handler
#
##############################################################################
def sigterm_handler(signum, frame):
    """If the program is terminated by sending it the signal SIGTERM
    (e.g. by executing 'kill') or SIGINT (pressing ctrl-c),
    this signal handler is invoked for cleanup."""
    flocklab.log_info("Main process received SIGTERM signal")
    # Close serial forwarder object:
    retval = stop_on_sig(flocklab.SUCCESS)
    sys.exit(retval)
### END sigterm_handler()


##############################################################################
#
# ServerSockets class
#
##############################################################################
class ServerSockets():
    def __init__(self, port):
        self.sock                = None
        self.sock_host           = ''
        self.sock_port           = port
        self.sock_rx_waittime    = 5.0
        self.sock_rx_bufsize     = 4096
        self.sock_listen_timeout = 0.2
        self.connection          = None
        self.address             = None

    def start(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind((self.sock_host, self.sock_port))
            self.sock.settimeout(self.sock_listen_timeout)
            flocklab.log_info("Started socket %s:%d" % (self.sock_host, self.sock_port))
        except:
            self.sock = None
            flocklab.log_error("Encountered error: %s, %s" % (str(sys.exc_info()[0]), str(sys.exc_info()[1])))

    def stop(self):
        if self.sock != None:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
                self.sock.close()
                flocklab.log_info("Stopped socket %s:%d" % (self.sock_host, self.sock_port))
            except:
                flocklab.log_error("Could not stop socket %s:%d due to error: %s, %s" % (self.sock_host, self.sock_port, str(sys.exc_info()[0]), str(sys.exc_info()[1])))
            finally:
                self.connection = None
                self.address = None
                self.sock = None

    def waitForClient(self):
        if self.sock != None:
            # flocklab.log_info("Waiting for clients on socket %s:%d" % (self.sock_host, self.sock_port))
            try:
                self.sock.listen(1)
                self.connection, self.address = self.sock.accept()
                self.connection.setblocking(0)
                self.connection.settimeout(self.sock_rx_waittime)
                flocklab.log_info("Client %s:%d connected to socket %s:%d" % (self.address[0], self.address[1], self.sock_host, self.sock_port))
            except socket.timeout:
                self.connection = None
            return self.connection
        else:
            raise socket.error

    def disconnectClient(self):
        if self.connection != None:
            flocklab.log_info("Disconnect client %s:%d from socket %s:%d" % (self.address[0], self.address[1], self.sock_host, self.sock_port))
            self.connection.close()
            self.connection = None
            self.address = None

    def send(self, data):
        if self.connection != None:
            return self.connection.send(data)
        else:
            raise socket.error

    def recv(self, bufsize=None):
        if ((self.sock != None) and (self.connection != None)):
            if bufsize == None:
                bufsize = self.sock_rx_bufsize
            return self.connection.recv(bufsize)
        else:
            raise socket.error

    def isRunning(self):
        if self.sock != None:
            return True
        return False

    def clientConnected(self):
        if self.connection != None:
            return True
        return False
### END ServerSockets()


##############################################################################
#
# SerialForwarder class
#
##############################################################################
class SerialForwarder():
    def __init__(self, slotnr, serialdev, baudrate):
        self.ser = serial.Serial()
        self.ser.port = serialdev
        self.ser.baudrate = baudrate
        self.num_elements_rcv = 0
        self.num_elements_snd = 0
        # If it breaks try the below
        #self.serConf() # Uncomment lines here till it works

        self.addr = None

    def cmd(self, cmd_str):
        self.ser.write(cmd_str + "\n")
        sleep(0.5)
        return self.ser.readline()

    def serConf(self):
        self.ser.baudrate = baudrate
        self.ser.bytesize = serial.EIGHTBITS
        self.ser.parity = serial.PARITY_NONE
        self.ser.stopbits = serial.STOPBITS_ONE
        self.ser.timeout = 0 # Non-Block reading
        self.ser.xonxoff = False # Disable Software Flow Control
        self.ser.rtscts = False # Disable (RTS/CTS) flow Control
        self.ser.dsrdtr = False # Disable (DSR/DTR) flow Control
        self.ser.writeTimeout = 2

    def open(self):
        try:
            self.ser.open()
            flocklab.log_info("SerialForwarder started for device %s with baudrate %d" % (self.ser.port, self.ser.baudrate))
        except(Exception) as err:
            flocklab.log_error("SerialForwarder could not start because: %s" % (str(sys.exc_info()[1])))
            return None
        flocklab.log_info("SerialForwarder opened.")

    def close(self):
        self.ser.close()
        flocklab.log_info("SerialForwarder stopped")
        
    def isRunning(self):
        if self.ser.is_open:
            return True
        return False

    def read(self):
        ret = None
        # Get data from serialdump:
        try:
            data = self.ser.readline()
            if (data != ''):
                # Useful data was retrieved, insert it into queue:
                timestamp = time.time()
                self.num_elements_rcv = self.num_elements_rcv +1
                ret = [data, timestamp]
        except(select.error) as err:
            if (err.errno == 4):
                flocklab.log_info("SerialForwarder interrupted due to caught stop signal.")
        except:
            flocklab.log_error("SerialForwarder encountered error: %s: %s" % (str(sys.exc_info()[0]), str(sys.exc_info()[1])))
        return ret

    def write(self, data):
        try:
            rs = self.ser.write(data)
            if rs != len(data):
                flocklab.log_error("SerialForwarder error while writing: no of bytes written (%d) != no of bytes in data (%d)." %str(rs, len(data)))
            self.num_elements_snd = self.num_elements_snd + 1
        except(socket.error) as err:
            flocklab.log_error("SerialForwarder error while writing to serial forwarder: %s" %str(err))
            self.close()
        except:
            flocklab.log_error("SerialForwarder encountered error: %s: %s" % (str(sys.exc_info()[0]), str(sys.exc_info()[1])))
        return None
### END SerialForwarder


##############################################################################
#
# ThreadSerialReader thread
#
##############################################################################
def ThreadSerialReader(sf, msgQueueDbBuf, msgQueueSockBuf, stopLock):
    data             = ''
    timestamp        = time.time()
    sf_err_back_init = 0.5        # Initial time to wait after error on opening serial port
    sf_err_back_step = 0.5        # Time to increase backoff time to wait after error on opening serial port
    sf_err_back_max  = 5.0        # Maximum backoff time to wait after error on opening serial port
    sf_err_backoff   = sf_err_back_init # Time to wait after error on opening serial port

    flocklab.log_info("ThreadSerialReader started.")
    while stopLock.acquire(False):
        stopLock.release()
        if not sf.isRunning():
            rs = sf.open()
            if rs == None:
                # There was an error opening the serial device. Wait some time before trying again:
                time.sleep(sf_err_backoff)
                # Increase backoff time to wait
                sf_err_backoff = sf_err_backoff + sf_err_back_step
                if sf_err_backoff > sf_err_back_max:
                    sf_err_backoff = sf_err_back_max
            else:
                sf_err_backoff = sf_err_back_init
            data = ''
            timestamp = 0
        if sf.isRunning():
            # Read data:
            try:
                [data, timestamp] = sf.read()
                if data != None:
                    # Data has been received.
                    if len(data) > 0:
                        try:
                            # Data is put directly onto the buffer queue for the socket:
                            msgQueueSockBuf.put(data, False)
                            # Data is wirtten directly into the DB bufferr queue:
                            msgQueueDbBuf.put([0,data,timestamp], False)
                            #flocklab.log_debug("[0,%s,%s]" %(str(data), str(timestamp)))
                        except queue.Full:
                            flocklab.log_error("Queue msgQueueSockBuf full in ThreadSerialReader, dropping data.")
                        except:
                            flocklab.log_error("ThreadSerialReader could not insert data into queues because: %s: %s" % (str(sys.exc_info()[0]), str(sys.exc_info()[1])))
                        data = ''
                        timestamp = lastTimestamp = 0
            except:
                flocklab.log_error("ThreadSerialReader encountered error: %s: %s" % (str(sys.exc_info()[0]), str(sys.exc_info()[1])))
                sf.close()
    # Stop thread:
    flocklab.log_error("ThreadSerialReader stopping...")
    if sf.isRunning():
        sf.close()
    flocklab.log_error("ThreadSerialReader stopped.")
### END ThreadSerialReader()


##############################################################################
#
# ThreadSocketProxy thread
#
##############################################################################
def ThreadSocketProxy(msgQueueSockBuf, ServerSock, sf, msgQueueDbBuf, stopLock):
    poll_timeout   = 1000
    READ_ONLY      = select.POLLIN | select.POLLPRI | select.POLLHUP | select.POLLERR
    READ_WRITE     = READ_ONLY | select.POLLOUT
    message_queues = {}
    connection     = None
    fd_to_socket   = {}

    try:
        flocklab.log_info("ThreadSocketProxy started")

        # Initialize poller:
        poller = select.poll()
        poller.register(msgQueueSockBuf._reader, READ_ONLY)
        fd_to_socket[msgQueueSockBuf._reader.fileno()] = msgQueueSockBuf

        # Let thread run until stopLock is acquired:
        while stopLock.acquire(False):
            stopLock.release()
            try:
                if not ServerSock.isRunning():
                    ServerSock.start()
                if not ServerSock.clientConnected():
                    connection = ServerSock.waitForClient()
                    if ServerSock.clientConnected():
                        fd_to_socket[connection.fileno()] = connection
                        poller.register(connection, READ_ONLY)
                # Wait for data:
                # drop data if client is not connected
                events = poller.poll(poll_timeout)

                for fd, flag in events:
                    # Retrieve the actual socket from its file descriptor
                    s = fd_to_socket[fd]
                    # Handle inputs
                    if flag & (select.POLLIN | select.POLLPRI):
                        if s is connection:
                            data = ServerSock.recv()
                            timestamp = time.time()
                            #flocklab.log_debug("---> Received data from socket: %s: >%s<" % (str(timestamp), str(data)))
                            if data == '':
                                # That can only mean that the socket has been closed.
                                poller.unregister(s)
                                if ServerSock.isRunning():
                                    ServerSock.disconnectClient()
                                    continue
                            # Send received data to serial forwarder and the DB buffer
                            if not sf.isRunning():
                                sf.close()
                                sf.open()
                            if sf.isRunning():
                                sf.write(data)
                                #flocklab.log_debug("<--- Wrote data to SF: >%s<" % (str(data)))
                                # Signal with 1, that data is from writer (use 0 for reader):
                                try:
                                    dataSanList = data.replace(b'\r', b'').split(b'\n')
                                    for i, dataSan in enumerate(dataSanList):
                                        ts = timestamp + i * 0.000001 # with sligthly different timestamps we make sure that ordering is preserved
                                        if(len(dataSan) > 0):
                                            msgQueueDbBuf.put([1, dataSan, ts], False)
                                except queue.Full:
                                    flocklab.log_error("Queue msgQueueDbBuf full in ThreadSocketProxy, dropping data.")
                                except Exception:
                                    flocklab.log_error("An error occurred, serial data dropped (%s, %s)." % (str(sys.exc_info()[1]), traceback.format_exc()))
                        elif s is msgQueueSockBuf:
                            # Retrieve element from queue:
                            item = msgQueueSockBuf.get()
                            # Forward element to socket:
                            if ((ServerSock.isRunning()) and (ServerSock.clientConnected())):
                                try:
                                    rs = ServerSock.send(item)
                                    #flocklab.log_debug("<--- Sent data to socket (rs: %s, len: %d)" % (str(rs), len(item)))
                                    if rs != len(item):
                                        raise socket.error
                                except(socket.error) as err:
                                    flocklab.log_warning("ThreadSocketProxy could not send data to socket because of encountered error: %s: %s" % (str(sys.exc_info()[0]), str(sys.exc_info()[1])))
                                    poller.unregister(connection)
                                    if ServerSock.clientConnected():
                                        ServerSock.disconnectClient()
                                        continue
                    elif flag & select.POLLHUP:
                        # The POLLHUP flag indicates a client that "hung up" the connection without closing it cleanly.
                        if ((s is connection) and (ServerSock.isRunning())):
                            poller.unregister(s)
                            if ServerSock.clientConnected():
                                ServerSock.disconnectClient()
                                continue
                    elif flag & select.POLLERR:
                        if ((s is connection) and (ServerSock.isRunning())):
                            poller.unregister(s)
                            ServerSock.disconnectClient()
                            ServerSock.stop()
                            continue
            except:
                flocklab.log_error("ThreadSocketProxy encountered error: %s: %s" % (str(sys.exc_info()[0]), str(sys.exc_info()[1])))
        # Stop the thread
        flocklab.log_info("ThreadSocketProxy stopping...")
        try:
            if ServerSock.isRunning():
                ServerSock.disconnectClient()
                ServerSock.stop()
        except:
            flocklab.log_error("Error in ServerSock.disconnectClient(): %s: %s" % (str(sys.exc_info()[0]), str(sys.exc_info()[1])))

    except:
        flocklab.log_error("ThreadSocketProxy encountered error: %s: %s" % (str(sys.exc_info()[0]), str(sys.exc_info()[1])))

    flocklab.log_info("ThreadSocketProxy stopped.")
### END ThreadSocketProxy()


##############################################################################
#
# ProcDbBuf
#
##############################################################################
def ProcDbBuf(msgQueueDbBuf, stopLock, testid):
    _num_elements         = 0
    _dbfile               = None
    _dbfile_creation_time = 0
    _dbflushinterval      = 300
    _obsresfolder         = "%s/%d" % (os.path.realpath(config.get("observer", 'testresultfolder')), testid)

    def _get_db_file_name():
        return "%s/serial_%s.db" % (_obsresfolder, time.strftime("%Y%m%d%H%M%S", time.gmtime()))

    try:
        flocklab.log_info("ProcDbBuf started")
        # set lower priority
        os.nice(1)

        # Let process run until stoplock is acquired:
        while stopLock.acquire(False):
            stopLock.release()
            try:
                # Wait for data in the queue:
                _waittime = _dbfile_creation_time + _dbflushinterval - time.time()
                if _waittime <= 0:
                    if _dbfile is not None:
                        _dbfile.close()
                        flocklab.log_info("ProcDbBuf closed dbfile %s" % _dbfilename)
                    _dbfilename = _get_db_file_name()
                    _dbfile = open(_dbfilename, "wb+")
                    _dbfile_creation_time = time.time()
                    _waittime = _dbflushinterval
                    flocklab.log_info("ProcDbBuf opened dbfile %s" % _dbfilename)
                _service, _data, _ts = msgQueueDbBuf.get(True, _waittime)
                try:
                    _len = len(_data)
                except:
                    continue
                if _len > 0:
                    _ts_sec = int(_ts)
                    # Write to dbfile:
                    if _dbfile is None:
                        _dbfilename = _get_db_file_name()
                        _dbfile = open(_dbfilename, "wb+")
                        _dbfile_creation_time = time.time()
                        flocklab.log_info("ProcDbBuf opened dbfile %s" % _dbfilename)
                    #why Illl and why _len + 12, in decode iii is used..?
                    #flocklab.log_debug("SERVICE: %s - DATA: %s" % (str(_service), str(_data)))
                    packet = struct.pack("<Illl%ds" % _len,_len + 12, _service, _ts_sec, int((_ts - _ts_sec) * 1e6), _data)
                    _dbfile.write(packet)
                    _num_elements = _num_elements + 1
            except queue.Empty:
                continue
            except(IOError) as err:
                if (err.errno == 4):
                    flocklab.log_info("ProcDbBuf interrupted due to caught stop signal.")
                    continue
                else:
                    raise

        # Stop the process
        flocklab.log_info("ProcDbBuf stopping... %d elements received " % _num_elements)
    except KeyboardInterrupt:
        pass
    except:
        flocklab.log_error("ProcDbBuf encountered error: %s: %s" % (str(sys.exc_info()[0]), str(sys.exc_info()[1])))

    # flush dbfile and errorfile
    try:
        if _dbfile is not None:
            _dbfile.close()
            flocklab.log_info("ProcDbBuf closed dbfile %s" % _dbfilename)
        flocklab.log_info("ProcDbBuf stopped.")
    except:
        flocklab.log_error("ProcDbBuf encountered error: %s: %s" % (str(sys.exc_info()[0]), str(sys.exc_info()[1])))
### END ProcDbBuf


##############################################################################
#
# stop_on_sig
#
##############################################################################
def stop_on_sig(ret_val=flocklab.SUCCESS):
    """Stop all serial forwarder threads and the output socket
    and exit the application.
    Arguments:
        ret_val:        Return value to exit the program with.
    """
    global proc_list

    # Close all threads:
    flocklab.log_info("Closing %d processes/threads..." %  len(proc_list))
    for (proc,stopLock) in proc_list:
        try:
            stopLock.acquire()
        except:
            flocklab.log_error("Could not acquire stop lock for process/thread.")
    flocklab.log_info("Joining %d processes/threads..." %  len(proc_list))
    for (proc,stopLock) in proc_list:
        try:
            proc.join(10)
        except:
            flocklab.log_warning("Could not stop process/thread.")
        if proc.is_alive():
            flocklab.log_error("Could not stop process/thread.")

    # Stop dbbuf process:
    flocklab.log_info("Closing ProcDbBuf process...")
    try:
        dbbuf_proc[1].acquire()
    except:
        flocklab.log_error("Could not acquire stoplock for ProcDbBuf process.")
    # Send some dummy data to the queue of the DB buffer to wake it up:
    msgQueueDbBuf.put([None, None, None])
    flocklab.log_info("Joining ProcDbBuf process...")
    try:
        dbbuf_proc[0].join(30)
    except:
        flocklab.log_error("Could not stop ProcDbBuf process.")
    if dbbuf_proc and dbbuf_proc[0].is_alive():
        flocklab.log_error("Could not stop ProcDbBuf process.")

    # Remove the PID file if it exists:
    if os.path.exists(pidfile):
        try:
            os.remove(pidfile)
        except:
            flocklab.log_warning("Could not remove pid file.")

    flocklab.log_info("FlockLab serial service stopped.")
    return ret_val
### END stop_on_sig()


##############################################################################
#
# stop_on_api
#
##############################################################################
def stop_on_api():
    """Stop all already running serial reader processes
    """
    # Get PID of running serial reader (if any) from pidfile and send it the terminate signal.
    try:
        pid = int(open(pidfile, 'r').read())
        # Signal the process to stop:
        if (pid > 0):
            flocklab.log_info("Sending SIGTERM signal to process %d" %pid)
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                os.remove(pidfile)
                raise
            try:
                os.waitpid(pid, 0)
            except OSError:
                pass    # can occur, no need to print a warning
        return flocklab.SUCCESS
    except (IOError, OSError):
        # The pid file was most probably not present. This can have two causes:
        #   1) The serial reader service is not running.
        #   2) The serial reader service did not shut down correctly the last time.
        # As consequence, try to kill all remaining serial reader servce threads (handles 1)) and if that
        # was not successful (meaning cause 2) takes effect), return ENOPKG.
        try:
            patterns = [os.path.basename(__file__),]
            ownpid = str(os.getpid())
            for pattern in patterns:
                p = subprocess.Popen(['pgrep', '-f', pattern], stdout=subprocess.PIPE, universal_newlines=True)
                out, err = p.communicate(None)
                if (out != None):
                    for pid in out.split('\n'):
                        if ((pid != '') and (pid != ownpid)):
                            flocklab.log_info("Trying to kill process %s" %pid)
                            os.kill(int(pid), signal.SIGKILL)
                    return flocklab.SUCCESS
            return errno.ENOPKG
        except (OSError, ValueError):
            flocklab.log_error("Error while trying to kill serial service threads: %s, %s" % (str(sys.exc_info()[0]), str(sys.exc_info()[1])))
            return errno.EINVAL
### END stop_on_api()


##############################################################################
#
# Main
#
##############################################################################
def main(argv):

    global proc_list
    global isdaemon
    global dbbuf_proc
    global pidfile
    global config
    global msgQueueDbBuf

    debug      = False
    port       = 'serial'      # Standard port. Can be overwritten by the user.
    serialdev  = None
    baudrate   = 115200        # Standard baudrate. Can be overwritten by the user.
    slotnr     = None
    testid     = None
    socketport = None
    stop       = False

    # Get config:
    config = flocklab.get_config()
    if not config:
        flocklab.error_logandexit("Could not read configuration file.")

    # Get command line parameters.
    try:
        opts, args = getopt.getopt(argv, "ehqdt:p:m:b:i:l:", ["stop", "help", "daemon", "debug", "port=", "baudrate=", "testid=", "socketport="])
    except(getopt.GetoptError) as err:
        flocklab.error_logandexit(str(err), errno.EINVAL)
    for opt, arg in opts:
        if opt in ("-h", "--help"):
            usage()
            sys.exit(flocklab.SUCCESS)
        elif opt in ("-d", "--debug"):
            debug = True
        elif opt in ("-q", "--daemon"):
            isdaemon = True
        elif opt in ("-e", "--stop"):
            stop = True
        elif opt in ("-b", "--baudrate"):
            if int(arg) not in flocklab.tg_baud_rates:
                flocklab.error_logandexit("Baudrate not valid. Check help for possible baud rates.", errno.EINVAL)
            else:
                baudrate = int(arg)
        elif opt in ("-p", "--port"):
            if arg not in flocklab.tg_port_types:
                flocklab.error_logandexit("Port not valid. Possible values are: %s" % (str(flocklab.tg_port_types)), errno.EINVAL)
            else:
                port = arg
        elif opt in ("-i", "--testid"):
            testid = int(arg)
        elif opt in ("-l", "--socketport"):
            socketport = int(arg)
        else:
            flocklab.error_logandexit("Unknown option '%s'." % (opt), errno.EINVAL)

    # Check if the mandatory parameter --testid is set:
    if not stop:
        if not testid:
            flocklab.error_logandexit("No test ID specified.", errno.EINVAL)
        # Check if folder exists
        if not os.path.isdir("%s/%d" % (os.path.realpath(config.get("observer", 'testresultfolder')), testid)):
            flocklab.error_logandexit("Test results folder does not exist.")

    pidfile = "%s/flocklab_serial.pid" % (config.get("observer", "pidfolder"))

    if stop:
        logger = flocklab.get_logger(debug=debug)
        rs = stop_on_api()
        sys.exit(rs)

    # If the daemon option is on, later on the process will be daemonized.
    if isdaemon:
        daemon.daemonize(pidfile=pidfile, closedesc=True)
    else:
        open(pidfile, 'w').write("%d" % (os.getpid()))

    # init logger AFTER daemonizing the process
    logger = flocklab.get_logger(debug=debug)
    if not logger:
        flocklab.error_logandexit("Could not get logger.")

    # Find out which target interface is currently activated.
    slotnr = flocklab.tg_get_selected()
    if not slotnr:
        flocklab.error_logandexit("Could not determine slot number.")
    logger.debug("Selected slot number is %d." % slotnr)
    # Set the serial path:
    if port == 'usb':
        serialdev = flocklab.tg_usb_port
    else:
        serialdev = flocklab.tg_serial_port

    # Initialize message queues ---
    msgQueueDbBuf = multiprocessing.Queue()
    msgQueueSockBuf = multiprocessing.Queue()

    # Initialize socket ---
    if not socketport is None:
        ServerSock = ServerSockets(socketport)

    # Initialize serial forwarder ---
    sf = SerialForwarder(slotnr, serialdev, baudrate)

    # Start process for DB buffer ---
    stopLock = multiprocessing.Lock()
    p =  multiprocessing.Process(target=ProcDbBuf, args=(msgQueueDbBuf, stopLock, testid), name="ProcDbBuf")
    try:
        p.daemon = True
        p.start()
        time.sleep(1)
        if p.is_alive():
            dbbuf_proc = [p, stopLock]
            logger.debug("DB buffer process running.")
        else:
            flocklab.error_logandexit("DB buffer process is not running.", errno.ESRCH)
    except:
        stop_on_sig(flocklab.SUCCESS)
        flocklab.error_logandexit("Error when starting DB buffer process: %s, %s" % (str(sys.exc_info()[0]), str(sys.exc_info()[1])), errno.ECONNABORTED)

    # Start thread for serial reader ---
    stopLock = multiprocessing.Lock()
    p =  threading.Thread(target=ThreadSerialReader, args=(sf,msgQueueDbBuf,msgQueueSockBuf,stopLock))
    try:
        p.daemon = True
        p.start()
        time.sleep(1)
        if p.is_alive():
            proc_list.append((p, stopLock))
            logger.debug("Serial reader thread running.")
        else:
            flocklab.error_logandexit("Serial reader thread is not running.", errno.ESRCH)
    except:
        stop_on_sig(flocklab.SUCCESS)
        flocklab.error_logandexit("Error when starting serial reader thread: %s, %s" % (str(sys.exc_info()[0]), str(sys.exc_info()[1])), errno.ECONNABORTED)

    # Start thread for socket proxy ---
    if not socketport is None:
        stopLock = multiprocessing.Lock()
        p =  threading.Thread(target=ThreadSocketProxy, args=(msgQueueSockBuf,ServerSock,
        sf,msgQueueDbBuf,stopLock))
        try:
            p.daemon = True
            p.start()
            time.sleep(1)
            if p.is_alive():
                proc_list.append((p, stopLock))
                logger.debug("Socket proxy thread running.")
            else:
                flocklab.error_logandexit("Socket proxy thread is not running.", errno.ESRCH)
        except:
            stop_on_sig(flocklab.SUCCESS)
            error_logandexit("Error when starting socket proxy thread: %s, %s" % (str(sys.exc_info()[0]), str(sys.exc_info()[1])), errno.ECONNABORTED)

    # Catch kill signal and ctrl-c
    signal.signal(signal.SIGTERM, sigterm_handler)
    signal.signal(signal.SIGINT, sigterm_handler)
    logger.debug("Signal handler registered.")

    logger.info("FlockLab serial service started.")

    """ Enter an infinite loop which hinders the program from exiting.
        This is needed as otherwise the thread list would get lost which would make it
        impossible to stop all threads when the service is stopped.
        The loop is stopped as soon as the program receives a stop signal.
    """
    while True:
        # Wake up once every now and then:
        time.sleep(10)

    sys.exit(flocklab.SUCCESS)
### END main()


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except Exception:
        flocklab.error_logandexit("Encountered error: %s\n%s\nCommandline was: %s" % (str(sys.exc_info()[1]), traceback.format_exc(), str(sys.argv)))
