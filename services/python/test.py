#! /usr/bin/env python2
from serial.serialutil import SerialException

__author__ 		= "Christoph Walser <walser@tik.ee.ethz.ch>"
__copyright__ 	= "Copyright 2010, ETH Zurich, Switzerland, Christoph Walser"
__license__ 	= "GPL"
__version__ 	= "$Revision$"
__date__ 		= "$Date$"
__id__ 			= "$Id$"
__source__ 		= "$URL$"

"""
This file belongs to /usr/bin/ on the observer
"""

import os, sys, getopt, signal, socket, time, subprocess, errno, Queue, serial, select, multiprocessing, threading, traceback, __main__
from syslog import *
from struct import *
# Import local libraries:
sys.path.append('../../testmanagement/lib/')
import daemon
from flocklab import SUCCESS
import flocklab



file = open("/home/debian/flocklab/db/1/serial_20190515081935.db", "rb")
for line in file:
	_data = unpack("<Illl%ds" %(len(line) - 16),line)
	print((_data[0], _data[1], _data[4], "%i.%06i"%(_data[2],_data[3])))