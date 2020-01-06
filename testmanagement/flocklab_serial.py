#! /usr/bin/env python3

import os, sys, getopt, signal, socket, time, subprocess, errno, queue, serial, select, multiprocessing, threading, traceback, syslog #, struct
import lib.daemon as daemon
import lib.flocklab as flocklab


### Global variables ###
pidfile                = None
config                 = None
logger                 = None
isdaemon               = False
debug                  = False
port_list              = ('usb', 'serial')                                 # List of possible ports to receive serial data from. 'usb' -> /dev/flocklab/usb/targetx, 'serial' -> /dev/ttyO2
baudrate_list          = (2400, 4800, 9600, 19200, 38400, 57600, 115200)   # List of allowed baud rates for general targets
baudrate_contiki2_list = (19200, 38400, 57600, 115200)                     # List of allowed baud rates for contiki2 targets
proc_list              = []                                                # List with all running processes
dbbuf_proc             = []                                                # Dbbuf process
msgQueueDbBuf          = None                                              # Queue used to send data to the DB buffer


##############################################################################
#
# Error classes
#
##############################################################################
class Error(Exception):
    """Base class for exceptions in this module."""
    pass

class SerialError(Error):
    """Exception raised for errors in the serial communication."""
    def __init__(self, value):
        self.value = value
    def __str__(self):
        return repr(self.value)
### END Error classes



##############################################################################
#
# sigterm_handler
#
##############################################################################
def sigterm_handler(signum, frame):
    """If the program is terminated by sending it the signal SIGTERM
    (e.g. by executing 'kill') or SIGINT (pressing ctrl-c),
    this signal handler is invoked for cleanup."""
    syslog.syslog(syslog.LOG_INFO, "Main process received SIGTERM signal")
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
            syslog.syslog(syslog.LOG_INFO, "Started socket %s:%d"%(self.sock_host, self.sock_port))
        except:
            self.sock = None
            syslog.syslog(syslog.LOG_INFO, "Encountered error in line %d: %s: %s" % (traceback.tb_lineno(sys.exc_info()[2]), str(sys.exc_info()[0]), str(sys.exc_info()[1])))

    def stop(self):
        if self.sock != None:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
                self.sock.close()
                syslog.syslog(syslog.LOG_INFO, "Stopped socket %s:%d"%(self.sock_host, self.sock_port))
            except:
                syslog.syslog(syslog.LOG_INFO, "Could not stop socket %s:%d due to error in line %d: %s: %s"%(self.sock_host, self.sock_port, traceback.tb_lineno(sys.exc_info()[2]), str(sys.exc_info()[0]), str(sys.exc_info()[1])))
            finally:
                self.connection = None
                self.address = None
                self.sock = None

    def waitForClient(self):
        if self.sock != None:
            # syslog.syslog(syslog.LOG_INFO, "Waiting for clients on socket %s:%d"%(self.sock_host, self.sock_port))
            try:
                self.sock.listen(1)
                self.connection, self.address = self.sock.accept()
                self.connection.setblocking(0)
                self.connection.settimeout(self.sock_rx_waittime)
                syslog.syslog(syslog.LOG_INFO, "Client %s:%d connected to socket %s:%d"%(self.address[0], self.address[1], self.sock_host, self.sock_port))
            except socket.timeout:
                self.connection = None
            return self.connection
        else:
            raise socket.error

    def disconnectClient(self):
        if self.connection != None:
            syslog.syslog(syslog.LOG_INFO, "Disconnect client %s:%d from socket %s:%d"%(self.address[0], self.address[1], self.sock_host, self.sock_port))
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
            syslog.syslog(syslog.LOG_INFO, "SerialForwarder started for device %s with baudrate %d"%(self.ser.port, self.ser.baudrate))
        except(Exception) as err:
            syslog.syslog(syslog.LOG_ERR, "SerialForwarder could not start because: %s" % (str(sys.exc_info()[1])))
            return None
        syslog.syslog(syslog.LOG_INFO, "SerialForwarder opened.")

    def close(self):
        self.ser.close()
        syslog.syslog(syslog.LOG_INFO, "SerialForwarder stopped")
        
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
            if (err[0] == 4):
                syslog.syslog(syslog.LOG_INFO, "SerialForwarder interrupted due to caught stop signal.")
        except:
            syslog.syslog(syslog.LOG_ERR, "SerialForwarder encountered error in line %d: %s: %s" % (traceback.tb_lineno(sys.exc_info()[2]), str(sys.exc_info()[0]), str(sys.exc_info()[1])))
        return ret

    def write(self, data):
        try:
            rs = self.ser.write(data)
            if rs != len(data):
                syslog.syslog(syslog.LOG_ERR, "SerialForwarder error while writing: no of bytes written (%d) != no of bytes in data (%d)." %str(rs, len(data)))
            self.num_elements_snd = self.num_elements_snd + 1
        except(socket.error) as err:
            syslog.syslog(syslog.LOG_ERR, "SerialForwarder error while writing to serial forwarder: %s" %str(err))
            self.close()
        except:
            syslog.syslog(syslog.LOG_ERR, "SerialForwarder encountered error in line %d: %s: %s" % (traceback.tb_lineno(sys.exc_info()[2]), str(sys.exc_info()[0]), str(sys.exc_info()[1])))
        return None
### END SerialForwarder



##############################################################################
#
# ThreadSerialReader thread
#
##############################################################################
def ThreadSerialReader(sf, msgQueueDbBuf, msgQueueSockBuf, stopLock):
    data            = ''
    timestamp        = time.time()
    sf_err_back_init= 0.5        # Initial time to wait after error on opening serial port
    sf_err_back_step= 0.5        # Time to increase backoff time to wait after error on opening serial port
    sf_err_back_max    = 5.0        # Maximum backoff time to wait after error on opening serial port
    sf_err_backoff  = sf_err_back_init # Time to wait after error on opening serial port

    syslog.syslog(syslog.LOG_ERR, "ThreadSerialReader started.")
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
                            syslog.syslog(syslog.LOG_INFO, "[0,%s,%s]" %(str(data), str(timestamp)))
                        except Queue.Full:
                            syslog.syslog(syslog.LOG_ERR, "Queue msgQueueSockBuf full in ThreadSerialReader, dropping data.")
                        except:
                            syslog.syslog(syslog.LOG_ERR, "ThreadSerialReader could not insert data into queues because: %s: %s" % (str(sys.exc_info()[0]), str(sys.exc_info()[1])))
                        data = ''
                        timestamp = lastTimestamp = 0
            except:
                syslog.syslog(syslog.LOG_ERR, "ThreadSerialReader encountered error in line %d: %s: %s" % (traceback.tb_lineno(sys.exc_info()[2]), str(sys.exc_info()[0]), str(sys.exc_info()[1])))
                sf.close()
    # Stop thread:
    syslog.syslog(syslog.LOG_ERR, "ThreadSerialReader stopping...")
    if sf.isRunning():
        sf.close()
    syslog.syslog(syslog.LOG_ERR, "ThreadSerialReader stopped.")

### END ThreadSerialReader()


##############################################################################
#
# ThreadSocketProxy thread
#
##############################################################################
def ThreadSocketProxy(msgQueueSockBuf, ServerSock, sf, msgQueueDbBuf, stopLock):
    poll_timeout        = 1000
    READ_ONLY            = select.POLLIN | select.POLLPRI | select.POLLHUP | select.POLLERR
    READ_WRITE            = READ_ONLY | select.POLLOUT
    message_queues        = {}
    connection            = None
    fd_to_socket        = {}


    try:
        syslog.syslog(syslog.LOG_INFO, "ThreadSocketProxy started")

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
                            #if debug:
                            #    syslog.syslog(syslog.LOG_INFO, "---> Received data from socket: %s: >%s<"%(str(timestamp), str(data)))
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
                                #if debug:
                                #    syslog.syslog(syslog.LOG_INFO, "<--- Wrote data to SF: >%s<"%(str(data)))
                                # Signal with 1, that data is from writer (use 0 for reader):
                                try:
                                    dataSanList = data.replace(b'\r', b'').split('\n')
                                    for i, dataSan in enumerate(dataSanList):
                                        ts = timestamp + i * 0.000001 # with sligthly different timestamps we make sure that ordering is preserved
                                        if(len(dataSan) > 0):
                                            msgQueueDbBuf.put([1, dataSan, ts], False)
                                except Queue.Full:
                                    syslog.syslog(syslog.LOG_ERR, "Queue msgQueueDbBuf full in ThreadSocketProxy, dropping data.")
                                except Exception:
                                    syslog.syslog(syslog.LOG_ERR, "Serial data could not be sanitized, dropping data.")
                        elif s is msgQueueSockBuf:
                            # Retrieve element from queue:
                            item = msgQueueSockBuf.get()
                            # Forward element to socket:
                            if ((ServerSock.isRunning()) and (ServerSock.clientConnected())):
                                try:
                                    rs = ServerSock.send(item)
                                    #if debug:
                                    #    syslog.syslog(syslog.LOG_INFO, "<--- Sent data to socket (rs: %s, len: %d)"%(str(rs), len(item)))
                                    if rs != len(item):
                                        raise socket.error
                                except(socket.error) as err:
                                    syslog.syslog(syslog.LOG_WARNING, "ThreadSocketProxy could not send data to socket because of encountered error in line %d: %s: %s" % (traceback.tb_lineno(sys.exc_info()[2]), str(sys.exc_info()[0]), str(sys.exc_info()[1])))
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
                syslog.syslog(syslog.LOG_ERR, "ThreadSocketProxy encountered error in line %d: %s: %s" % (traceback.tb_lineno(sys.exc_info()[2]), str(sys.exc_info()[0]), str(sys.exc_info()[1])))
        # Stop the thread
        syslog.syslog(syslog.LOG_INFO, "ThreadSocketProxy stopping...")
        try:
            if ServerSock.isRunning():
                ServerSock.disconnectClient()
                ServerSock.stop()
        except:
            pass

    except:
        syslog.syslog(syslog.LOG_ERR, "ThreadSocketProxy encountered error in line %d: %s: %s" % (traceback.tb_lineno(sys.exc_info()[2]), str(sys.exc_info()[0]), str(sys.exc_info()[1])))

    syslog.syslog(syslog.LOG_INFO, "ThreadSocketProxy stopped.")
### END ThreadSocketProxy()



##############################################################################
#
# ProcDbBuf
#
##############################################################################
def ProcDbBuf(msgQueueDbBuf, stopLock, testid):
    _num_elements  = 0
    _dbfile        = None
    _dbfile_creation_time = 0
    _dbflushinterval = config.getint("serial", "dbflushinterval")
    _obsdbfolder    = "%s/%d" % (os.path.realpath(config.get("observer", 'obsdbfolder')),testid)

    def _get_db_file_name():
        return "%s/serial_%s.db" % (_obsdbfolder, time.strftime("%Y%m%d%H%M%S", time.gmtime()))

    try:
        syslog.syslog(syslog.LOG_INFO, "ProcDbBuf started")
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
                        syslog.syslog(syslog.LOG_INFO, "ProcDbBuf closed dbfile %s" % _dbfilename)
                    _dbfilename = _get_db_file_name()
                    _dbfile = open(_dbfilename, "wb+")
                    _dbfile_creation_time = time.time()
                    _waittime = _dbflushinterval
                    syslog.syslog(syslog.LOG_INFO, "ProcDbBuf opened dbfile %s" % _dbfilename)
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
                        syslog.syslog(syslog.LOG_INFO, "ProcDbBuf opened dbfile %s" % _dbfilename)
                    #why Illl and why _len + 12, in decode iii is used..?
                    syslog.syslog(syslog.LOG_INFO, "SERVICE: %s - DATA: %s" % (str(_service), str(_data)))
                    packet = pack("<Illl%ds" % _len,_len + 12, _service, _ts_sec, int((_ts - _ts_sec) * 1e6), _data)
                    _dbfile.write(packet)
                    _num_elements = _num_elements+1
            except Queue.Empty:
                continue
            except(IOError) as err:
                if (err[0] == 4):
                    syslog.syslog(syslog.LOG_INFO, "ProcDbBuf interrupted due to caught stop signal.")
                    continue
            except:
                syslog.syslog(syslog.LOG_ERR, "ProcDbBuf encountered error in line %d: %s: %s" % (traceback.tb_lineno(sys.exc_info()[2]), str(sys.exc_info()[0]), str(sys.exc_info()[1])))

        # Stop the process
        syslog.syslog(syslog.LOG_INFO, "ProcDbBuf stopping... %d elements received "%_num_elements)
    except:
        syslog.syslog(syslog.LOG_ERR, "ProcDbBuf encountered error in line %d: %s: %s" % (traceback.tb_lineno(sys.exc_info()[2]), str(sys.exc_info()[0]), str(sys.exc_info()[1])))

    # flush dbfile and errorfile
    try:
        if _dbfile is not None:
            _dbfile.close()
            syslog.syslog(syslog.LOG_INFO, "ProcDbBuf closed dbfile %s" % _dbfilename)
        syslog.syslog(syslog.LOG_INFO, "ProcDbBuf stopped.")
    except:
        syslog.syslog(syslog.LOG_ERR, "ProcDbBuf encountered error in line %d: %s: %s" % (traceback.tb_lineno(sys.exc_info()[2]), str(sys.exc_info()[0]), str(sys.exc_info()[1])))

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
    syslog.syslog(syslog.LOG_INFO, "Closing %d processes/threads..."% len(proc_list))
    for (proc,stopLock) in proc_list:
        try:
            stopLock.acquire()
        except:
            syslog.syslog(syslog.LOG_ERR, "Could not acquire stop lock for process/thread.")
    syslog.syslog(syslog.LOG_INFO, "Joining %d processes/threads..."% len(proc_list))
    for (proc,stopLock) in proc_list:
        try:
            proc.join(10)
        except:
            syslog.syslog(syslog.LOG_ERR, "Could not stop process/thread.")
        if proc.is_alive():
            syslog.syslog(syslog.LOG_ERR, "Could not stop process/thread.")

    # Stop dbbuf process:
    syslog.syslog(syslog.LOG_INFO, "Closing ProcDbBuf process...")
    try:
        dbbuf_proc[1].acquire()
    except:
        syslog.syslog(syslog.LOG_ERR, "Could not acquire stoplock for ProcDbBuf process.")
    # Send some dummy data to the queue of the DB buffer to wake it up:
    msgQueueDbBuf.put([None, None, None])
    syslog.syslog(syslog.LOG_INFO, "Joining ProcDbBuf process...")
    try:
        dbbuf_proc[0].join(30)
    except:
        syslog.syslog(syslog.LOG_ERR, "Could not stop ProcDbBuf process.")
    if dbbuf_proc[0].is_alive():
        syslog.syslog(syslog.LOG_ERR, "Could not stop ProcDbBuf process.")

    # Remove the PID file if it exists:
    if os.path.exists(pidfile):
        try:
            os.remove(pidfile)
        except:
            syslog.syslog(syslog.LOG_WARN, "Could not remove pid file.")

    syslog.syslog(syslog.LOG_INFO, "FlockLab serial service stopped.")
    # Close the syslog and terminate the program
    closelog()
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
        pid = int(open(pidfile,'r').read())
        # Signal the process to stop:
        if (pid > 0):
            syslog.syslog(syslog.LOG_INFO, "Main process: sending SIGTERM signal to process %d" %pid)
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                os.remove(pidfile)
                raise
            try:
                os.waitpid(pid, 0)
            except OSError:
                pass
        return flocklab.SUCCESS
    except (IOError, OSError):
        #DEBUG syslog.syslog(syslog.LOG_ERR, "----->Main process: Error while trying to kill main process in line %d: %s: %s" % (traceback.tb_lineno(sys.exc_info()[2]), str(sys.exc_info()[0]), str(sys.exc_info()[1])))
        # The pid file was most probably not present. This can have two causes:
        #   1) The serial reader service is not running.
        #   2) The serial reader service did not shut down correctly the last time.
        # As consequence, try to kill all remaining serial reader servce threads (handles 1)) and if that
        # was not successful (meaning cause 2) takes effect), return ENOPKG.
        try:
            patterns = ['flocklab_serial.py',]
            ownpid = str(os.getpid())
            suc = False
            for pattern in patterns:
                p = subprocess.Popen(['pgrep', '-f', pattern], stdout=subprocess.PIPE)
                out, err = p.communicate(None)
                if (out != None):
                    for pid in out.split('\n'):
                        if ((pid != '') and (pid != ownpid)):
                            syslog.syslog(syslog.LOG_INFO, "Main process: Trying to kill process %s" %pid)
                            os.kill(int(pid), signal.SIGKILL)
                    suc = True
            if (suc == True):
                return flocklab.SUCCESS
            else:
                return errno.ENOPKG
        except (OSError, ValueError):
            syslog.syslog(syslog.LOG_ERR, "Main process: Error while trying to kill old zombie threads in line %d: %s: %s" % (traceback.tb_lineno(sys.exc_info()[2]), str(sys.exc_info()[0]), str(sys.exc_info()[1])))
            return errno.EINVAL
### END stop_on_api()




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
    print("\t\t\t\tPossible values are: %s" %(str(port_list)))
    print("  --baudrate=<int>\t\tOptional. Baudrate of serial device. Default is 115200.")
    print("\t\t\t\tPossible values are: %s" %(str(baudrate_list)))
    print("  --socketport=<int>\t\tOptional. If set, a server socket will be created on the specified port.")
    print("  --stop\t\t\tOptional. Causes the program to stop a possibly running instance of the serial reader service.")
    print("  --daemon\t\t\tOptional. If set, program will run as a daemon. If not specified, all output will be written to STDOUT and STDERR.")
    print("  --debug\t\t\tOptional. Print debug messages to log.")
    print("  --help\t\t\tOptional. Print this help.")
    return(0)
### END usage()



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
    global debug
    global msgQueueDbBuf

    port         = 'serial'        # Standard port. Can be overwritten by the user.
    serialdev     = None
    baudrate     = 115200        # Standard baudrate. Can be overwritten by the user.
    slotnr         = None
    testid        = None
    socketport  = None
    stop        = False
    logger        = flocklab.get_logger("flocklab_serial.py")

    # Open the syslog:
    syslog.openlog('flocklab_serial', syslog.LOG_CONS | syslog.LOG_PID | syslog.LOG_PERROR, syslog.LOG_USER)

    # Get config:
    config = flocklab.get_config()
    if not config:
        logger.warn("Could not read configuration file. Exiting...")
        sys.exit(errno.EAGAIN)

    # Get command line parameters.
    try:
        opts, args = getopt.getopt(argv, "ehqdt:p:m:b:i:l:", ["stop", "help", "daemon", "debug", "port=", "baudrate=", "testid=", "socketport="])
    except(getopt.GetoptError) as err:
        syslog.syslog(syslog.LOG_ERR, str(err))
        usage()
        sys.exit(errno.EINVAL)
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
            if int(arg) not in baudrate_list:
                err = "Wrong API usage: baudrate not valid. Check help for possible baud rates."
                syslog.syslog(syslog.LOG_ERR, str(err))
                sys.exit(errno.EINVAL)
            else:
                baudrate = int(arg)
        elif opt in ("-p", "--port"):
            if arg not in port_list:
                err = "Wrong API usage: port not valid. Possible values are: %s" %(str(port_list))
                syslog.syslog(syslog.LOG_ERR, str(err))
                sys.exit(errno.EINVAL)
            else:
                port = arg
        elif opt in ("-i", "--testid"):
            testid = int(arg)
        elif opt in ("-l", "--socketport"):
            socketport = int(arg)
        else:
            syslog.syslog(syslog.LOG_ERR, "Wrong API usage")
            usage()
            sys.exit(errno.EINVAL)

    # Check if the mandatory parameter --testid is set:
    if testid==None:
        syslog.syslog(syslog.LOG_ERR, "Wrong API usage")
        usage()
        sys.exit(errno.EINVAL)

    pidfile = "%s/%s" %(config.get("observer", "pidfolder"), "flocklab_serial_%d.pid" % testid)

    if stop:
        rs = stop_on_api()
        sys.exit(rs)

    """ Check if daemon option is on. If on, reopen the syslog without the ability to write to the console.
        If the daemon option is on, later on the process will also be daemonized.
    """
    if isdaemon:
        closelog()
        syslog.openlog('flocklab_serial', syslog.LOG_CONS | syslog.LOG_PID, syslog.LOG_USER)
        daemon.daemonize(pidfile=pidfile, closedesc=True)
        syslog.syslog(syslog.LOG_INFO, "Daemonized process")
    else:
        open(pidfile,'w').write("%d"%(os.getpid()))


    # Find out which target interface is currently activated.
    slotnr = flocklab.tg_interface_get()
    if not slotnr:
        err = "No interface active. Please activate one first."
        syslog.syslog(syslog.LOG_ERR, err)
        sys.exit(errno.EINVAL)
    syslog.syslog(syslog.LOG_INFO, "Active target interface detected as %d"%slotnr)
    # Set the serial path:
    serialdev = '/dev/ttyO2'

    # Initialize message queues ---
    msgQueueDbBuf = multiprocessing.Queue()
    msgQueueSockBuf = multiprocessing.Queue()

    # Initialize socket ---
    if not socketport is None:
        ServerSock = ServerSockets(socketport)

    # Initialize serial forwarder ---
    sf = SerialForwarder(slotnr,serialdev,baudrate)

    # Start process for DB buffer ---
    stopLock = multiprocessing.Lock()
    p =  multiprocessing.Process(target=ProcDbBuf, args=(msgQueueDbBuf,stopLock, testid), name="ProcDbBuf")
    try:
        p.daemon = True
        p.start()
        time.sleep(1)
        if p.is_alive():
            dbbuf_proc = [p, stopLock]
            if debug:
                syslog.syslog(syslog.LOG_INFO, "DB buffer process running.")
        else:
            syslog.syslog(syslog.LOG_INFO, "DB buffer process is not running anymore.")
            raise Error
    except:
        syslog.syslog(syslog.LOG_ERR, "Error when starting DB buffer process: %s: %s" % (str(sys.exc_info()[0]), str(sys.exc_info()[1])))
        print("Error when starting DB buffer process: %s: %s" % (str(sys.exc_info()[0]), str(sys.exc_info()[1])))
        stop_on_sig(flocklab.SUCCESS)
        sys.exit(errno.ECONNABORTED)

    # Start thread for serial reader ---
    stopLock = multiprocessing.Lock()
    p =  threading.Thread(target=ThreadSerialReader, args=(sf,msgQueueDbBuf,msgQueueSockBuf,stopLock))
    try:
        p.daemon = True
        p.start()
        time.sleep(1)
        if p.is_alive():
            proc_list.append((p, stopLock))
            if debug:
                syslog.syslog(syslog.LOG_INFO, "Serial reader thread running.")
        else:
            syslog.syslog(syslog.LOG_INFO, "Serial reader thread is not running anymore.")
            raise Error
    except:
        syslog.syslog(syslog.LOG_ERR, "Error when starting serial reader thread: %s: %s" % (str(sys.exc_info()[0]), str(sys.exc_info()[1])))
        stop_on_sig(flocklab.SUCCESS)
        sys.exit(errno.ECONNABORTED)

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
                if debug:
                    syslog.syslog(syslog.LOG_INFO, "Socket proxy thread running.")
            else:
                syslog.syslog(syslog.LOG_INFO, "Socket proxy thread is not running anymore.")
                raise Error
        except:
            syslog.syslog(syslog.LOG_ERR, "Error when starting socket proxy thread: %s: %s" % (str(sys.exc_info()[0]), str(sys.exc_info()[1])))
            stop_on_sig(flocklab.SUCCESS)
            sys.exit(errno.ECONNABORTED)

    # Catch kill signal and ctrl-c
    signal.signal(signal.SIGTERM, sigterm_handler)
    signal.signal(signal.SIGINT, sigterm_handler)
    syslog.syslog(syslog.LOG_INFO, "Signal handler registered")

    syslog.syslog(syslog.LOG_INFO, "FlockLab serial service started.")

    """ Enter an infinite loop which hinders the program from exiting.
        This is needed as otherwise the thread list would get lost which would make it
        impossible to stop all threads when the service is stopped.
        The loop is stopped as soon as the program receives a stop signal.
    """
    while 1:
        # Wake up once every now and then:
        time.sleep(10)

    sys.exit(flocklab.SUCCESS)
### END main()


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except SystemExit:
        pass
    except:
        syslog.syslog(syslog.LOG_ERR, "Encountered error: %s: %s: %s\n\n--- traceback ---\n%s--- end traceback ---\n\nCommandline was: %s" % (str(sys.exc_info()[0]), str(sys.exc_info()[1]), str(traceback.print_tb(sys.exc_info()[2])), traceback.format_exc(), str(sys.argv)))
        sys.exit(errno.EAGAIN)
