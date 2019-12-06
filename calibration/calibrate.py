#!/usr/bin/env python3
"""
Automated RocketLogger calibration measurement and generation using SMU2450.

Copyright (c) 2016-2019, ETH Zurich, Computer Engineering Group
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
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""

import os
import sys
import time
from datetime import date

from calibration.smu import SMU2450
from rocketlogger.data import RocketLoggerData
from rocketlogger.calibration import RocketLoggerCalibration, CALIBRATION_SETUP_SMU2450

DATA_DIR = '/home/flocklab/.config/rocketlogger/'

ROCKETLOGGER_SAMPLE_RATES = [1000, 2000, 4000, 8000, 16000, 32000, 64000]


def get_rocketlogger_command(measurement_type, filename,
                             sample_rate=1000, duration=75, calibration=True):
    """
    Get the RocketLogger command for automated measurements.
    """
    command = 'rocketlogger start'

    # sample rate option
    if sample_rate in ROCKETLOGGER_SAMPLE_RATES:
        command += ' --rate={:d}'.format(sample_rate)
    else:
        raise ValueError('unsupported sample rate {:d}'.format(sample_rate))

    # calibration option
    if calibration:
        command += ' --calibration'

    # channel options
    if action == 'v':
        command += ' --channel=V1,V2'
        command += ' --comment=\'RocketLogger voltage calibration measurement for FlockLab 2 using automated SMU2450 sweep.\''
    elif action == 'il':
        command += ' --channel=I1L'
        command += ' --comment=\'RocketLogger current low calibration measurement for FlockLab 2 using automated SMU2450 sweep.\''
    elif action == 'ih':
        command += ' --channel=I1H --high-range=I1H'
        command += ' --comment=\'RocketLogger high current calibration measurement for FlockLab 2 using automated SMU2450 sweep.\''
    else:
        raise ValueError('unsupported measurement type {:s}'.format(measurement_type))

    # total sample count
    command += ' --samples={:d}'.format(sample_rate * duration)

    # other options
    command += ' --ambient=false'
    command += ' --digital=false'
    command += ' --output={}'.format(filename)
    command += ' --format=rld'
    command += ' --size=0'
    command += ' --web=false'

    return command


if __name__ == "__main__":

    # handle first argument
    if len(sys.argv) < 2:
        raise TypeError('need at least one argument specifying the action')
    action = str(sys.argv[1]).lower()

    # create base directory path if not existing
    os.makedirs(DATA_DIR, exist_ok=True)

    # generate filenames
    filename_base = os.path.join(DATA_DIR, '{}_calibration'.format(date.today()))
    filename_v = '{}_v.rld'.format(filename_base)
    filename_il = '{}_il.rld'.format(filename_base)
    filename_ih = '{}_ih.rld'.format(filename_base)
    filename_cal = '{}.dat'.format(filename_base)
    filename_log = '{}.log'.format(filename_base)

    # for option "cal" perform calibration using todays measurements
    if action == 'cal':
        print('Generating calibration file from measurements.')

        if not os.path.isfile(filename_v):
            raise FileNotFoundError('Missing voltage calibration measurement.')
        elif not os.path.isfile(filename_il):
            raise FileNotFoundError('Missing current low calibration measurement.')
        elif not os.path.isfile(filename_ih):
            raise FileNotFoundError('Missing current high calibration measurement.')

        # load calibration measurement data
        data_v = RocketLoggerData(filename_v)
        data_il = RocketLoggerData(filename_il)
        data_ih = RocketLoggerData(filename_ih)

        # copy channel V1 to provide (fake) V3, V4 data
        channel_info3 = data_v._header['channels'][0].copy()
        channel_info4 = data_v._header['channels'][0].copy()
        channel_info3['name'] = 'V3'
        channel_info4['name'] = 'V4'
        data_v.add_channel(channel_info3, data_v.get_data('V1').squeeze())
        data_v.add_channel(channel_info4, data_v.get_data('V1').squeeze())

        # copy channel I1L to provide (fake) I2L data
        channel_info = data_il._header['channels'][0].copy()
        channel_info['name'] = 'I2L'
        data_il.add_channel(channel_info, data_il.get_data('I1L').squeeze())

        # copy channel I1H to provide (fake) I2H data
        channel_info = data_ih._header['channels'][0].copy()
        channel_info['name'] = 'I2H'
        data_ih.add_channel(channel_info, data_ih.get_data('I1H').squeeze())

        # perform calibration and print statistics
        cal = RocketLoggerCalibration(data_v, data_il, data_ih,
                                      data_il, data_ih)
        cal.recalibrate(CALIBRATION_SETUP_SMU2450)
        cal.print_statistics()

        # write calibration file and print statistics
        cal.write_calibration_file(filename_cal)
        cal.write_log_file(filename_log)

    # for option "deploy" install today generated calibration
    elif action == 'deploy':
        print('Deploying generated calibration file.')

        if not os.path.isfile(filename_cal):
            raise FileNotFoundError('Missing calibration file. Generate calibration file first.')

        print('Manual deployment for system wide application needed:')
        print('  sudo cp -f {} /etc/rocketlogger/calibration.dat'.format(filename_cal))
        if os.path.isfile(filename_log):
            print('  sudo cp -f {} /etc/rocketlogger/calibration.log'.format(filename_log))

    # for measurement options conncet to SMU and perform respective measurement
    elif action in ['v', 'il', 'ih']:
        print('Running measurement for {action}.')

        # parse hostname argument
        hostname = 'localhost'
        if len(sys.argv) >= 3:
            hostname = sys.argv[2]
        else:
            print('No hostname given as argument #2, assuming localhost')

        # connect SMU
        smu = SMU2450(hostname)
        smu.connect()

        if action == 'v':
            filename = filename_v
            smu.calibrate_voltage()
        elif action == 'il':
            filename = filename_il
            smu.calibrate_current_low()
        elif action == 'ih':
            filename = filename_ih
            smu.calibrate_current_high()

        # small delay for start beep
        time.sleep(0.5)

        # start rocketlogger measurement
        rocketlogger_command = get_rocketlogger_command(action, filename)
        print(rocketlogger_command)
        os.system(rocketlogger_command)

        print('Calibration measurement done.')
        print('Data saved to {}'.format(filename))

        smu.disconnect()

    else:
        print('invalid argument, valid options are: v, il, ih, cal, or deploy')
