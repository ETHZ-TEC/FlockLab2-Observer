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

Author: Lukas Daschinger
"""

"""
    usage from command line: python3.7 config_read_parse.py  jlink_serial, device_name, ts_prescaler,
                                                            trace_address0, access_mode0, trace_pc0,
                                                            trace_address1, access_mode1, trace_pc1,
                                                            trace_address2, access_mode2, trace_pc2,
                                                            trace_address3, access_mode3, trace_pc3)
"""
import pylink
try:
    import StringIO
except ImportError:
    import io as StringIO
import sys
import time
import datetime
import traceback
import numpy as np


jlinklibpath = '/opt/jlink/libjlinkarm.so'
logging_on   = False      # debug prints enabled?
running      = True
debuglogfile = '/home/flocklab/log/dwt_daemon.log'


def stop_swo_read():
    global running
    running = False
### END sigterm_handler()


def log(msg):
    try:
        with open(debuglogfile, "a") as f:
            f.write("%s  %s\n" % (str(datetime.datetime.now()), msg.strip()))
            f.flush()
    except:
        print("Failed to append message '%s' to log file." % msg)


def measure_sleep_overhead(numSamples=100, sleepTime=0.001):
    """
    Measure the overhead of time.sleep() which is platform (kernel version) dependent.
    Overhead can vary up to 300us with different kernel versions.

    Parameters:
        numSamples (int): number of samples for measuring sleep overhead
        device_name (string): the device name (eg STM32L433CC)

    Returns:
      overhead of time.sleep() in seconds

    """
    a = np.empty([numSamples], dtype=np.float64)
    for i in range(numSamples):
        a[i] = time.time()
        time.sleep(sleepTime)
    diff = np.diff(a)
    return np.mean(diff) - sleepTime


def disable_and_reset_all_comparators(jlink_serial=None, device_name='STM32L433CC'):
    """
    Writes 0 as the tracing address for all comparators and disable them

    Parameters:
        jlink_serial (int): the serial number of the jlink emulator (eg 801012958)
        device_name (string): the device name (eg STM32L433CC)

    Returns:
      int: True if configuration reset was successful

    """

    # convert in case wrong type given as input
    try:
        jlink_serial = int(jlink_serial)
    except TypeError:  # if the type is None we just pass
        pass
    if not isinstance(device_name, str):
        log('the device name must be a string like "STM32L433CC" ')
        log('setting the device name to default: "STM32L433CC"')
        device_name = 'STM32L433CC'


    buf = StringIO.StringIO()
    jlinklib = pylink.library.Library(dllpath=jlinklibpath)
    jlink = pylink.JLink(lib=jlinklib, log=buf.write, detailed_log=buf.write)

    if jlink_serial:  # if have several emulators connected, user can specify one by the serial number
        jlink.open(serial_no=jlink_serial)
    else:
        jlink.open()

    jlink.set_tif(pylink.enums.JLinkInterfaces.SWD)
    jlink.connect(device_name, verbose=True)
    jlink.coresight_configure()
    jlink.set_reset_strategy(pylink.enums.JLinkResetStrategyCortexM3.RESETPIN)

    # In case the reset pin is not low must halt MCU before config, throws error in case reset pin is low
    try:
        jlink.halt()
    except:
        pass

    # now disable all comparators
    dwt_fun0 = 0xe0001028  # Comparator Function registers, DWT_FUNCTIONn
    dwt_comp0 = 0xe0001020  # Comparator registers, DWT_COMP0
    jlink.memory_write32(dwt_fun0, [0x0])  # zero will disable the comparator
    jlink.memory_write32(dwt_comp0, [0x0])  # set tracing address to zero

    dwt_fun1 = 0xe0001038  # Comparator Function registers, DWT_FUNCTIONn
    dwt_comp1 = 0xe0001030  # Comparator registers, DWT_COMP1
    jlink.memory_write32(dwt_fun1, [0x0])  # zero will disable the comparator
    jlink.memory_write32(dwt_comp1, [0x0])  # set tracing address to zero

    dwt_fun2 = 0xe0001048  # Comparator Function registers, DWT_FUNCTIONnKipeli46
    dwt_comp2 = 0xe0001040  # Comparator registers, DWT_COMP1
    jlink.memory_write32(dwt_fun2, [0x0])  # zero will disable the comparator
    jlink.memory_write32(dwt_comp2, [0x0])  # set tracing address to zero

    dwt_fun3 = 0xe0001058  # Comparator Function registers, DWT_FUNCTIONn
    dwt_comp3 = 0xe0001050  # Comparator registers, DWT_COMP1
    jlink.memory_write32(dwt_fun3, [0x0])  # zero will disable the comparator
    jlink.memory_write32(dwt_comp3, [0x0])  # set tracing address to zero

    jlink.close()

    time.sleep(0.5)

    # reconnect in order to check the reset values
    jlink.open(serial_no=jlink_serial)
    jlink.set_tif(pylink.enums.JLinkInterfaces.SWD)
    jlink.connect(device_name, verbose=True)
    jlink.coresight_configure()
    jlink.set_reset_strategy(pylink.enums.JLinkResetStrategyCortexM3.RESETPIN)
    jlink.halt()

    if logging_on:
        log("\nall comparators are reset. To be sure the comparators are disabled check if the last four bits of the function value are zero")
        log("reset value comp0 function = " + hex(jlink.memory_read32(dwt_fun0, 1)[0]))
        log("reset value comp1 function = " + hex(jlink.memory_read32(dwt_fun1, 1)[0]))
        log("reset value comp2 function = " + hex(jlink.memory_read32(dwt_fun2, 1)[0]))
        log("reset value comp3 function = " +  hex(jlink.memory_read32(dwt_fun3, 1)[0]) + "\n")

    return 0


# trace address must be in hex
def config_dwt_for_data_trace(jlink_serial=None, device_name='STM32L433CC', ts_prescaler=64,
                              trace_address0=None, access_mode0='w', trace_pc0=0, size0=4,
                              trace_address1=None, access_mode1='w', trace_pc1=0, size1=4,
                              trace_address2=None, access_mode2='w', trace_pc2=0, size2=4,
                              trace_address3=None, access_mode3='w', trace_pc3=0, size3=4,
                              swo_speed=4000000, cpu_speed=80000000):
    """
    Configures the coresight components to trace variables with the DWT module

    Parameters:
        jlink_serial (int): the serial number of the jlink emulator (eg 801012958)
        device_name (string): the device name (eg STM32L433CC)
        ts_prescaler (int): the prescaler for local timestamps on the processor

        trace_address0 (int): the address of the variable that should be traced by comparator 0
        trace_address1 (int): the address of the variable that should be traced by comparator 1
        trace_address2 (int): the address of the variable that should be traced by comparator 2
        trace_address3 (int): the address of the variable that should be traced by comparator 3

        access_mode0 (string): specifies if should generate packet on ro, wo or on rw access of variable 0
        access_mode1 (string): specifies if should generate packet on ro, wo or on rw access of variable 1
        access_mode2 (string): specifies if should generate packet on ro, wo or on rw access of variable 2
        access_mode3 (string): specifies if should generate packet on ro, wo or on rw access of variable 3

        trace_pc0 (int): specifies if the PC should also be traced for variable 0 (if non-zero, PC is traced)
        trace_pc1 (int): specifies if the PC should also be traced for variable 1 (if non-zero, PC is traced)
        trace_pc2(int): specifies if the PC should also be traced for variable 2 (if non-zero, PC is traced)
        trace_pc3 (int): specifies if the PC should also be traced for variable 3 (if non-zero, PC is traced)

        sizen (int): size of the traced variable in bytes (allowed values: 1, 2 and 4)

    Returns:
      int: True if configuration was successful

    """

    def determine_config_value(trace_pc, access_mode):
        """
        The function implements this configuration table
                    read    write   read/write
                ----------------------------------
        data+PC |    0xe     0xf     0x3
        PC      |    n/a     n/a     0x1
        data    |    0xc     0xd     0x2

        Parameters:
            trace_pc (int): specifies if the PC should also be traced (if non-zero, PC is traced)
            access_mode (string): specifies if should generate packet on ro, wo or on rw access of variable

        Returns:
            config (int): The value that needs to be written into the function function register of the comparator

        """

        if trace_pc:  # tracing data and PC
            if access_mode == 'r':
                config = 0xe
            elif access_mode == 'w':
                config = 0xf
            elif access_mode == 'rw':
                config = 0x3
            else:
                config = 0x1    # PC only

        else:  # tracing data only
            if access_mode == 'r':
                config = 0xc
            elif access_mode == 'w':
                config = 0xd
            elif access_mode == 'rw':
                config = 0x2
            else:
                if logging_on:
                    log("access_mode must be r,w or rw. default is w")
                config = 0xd

        return config

    def convert_type(jlink_ser, dev_name, ts_pres, trace_addr0, trace_addr1,
                     trace_addr2, trace_addr3, swo_speed, cpu_speed):
        """
        takes the raw input values from function call and converts them to the right type (int or string)
        if type is "None", it stays

        """
        # convert in case wrong type given as input
        try:
            jlink_ser = int(jlink_ser)
        except TypeError:  # if the type is None we just pass
            pass
        if not isinstance(dev_name, str):
            log('the device name must be a string like "STM32L433CC" ')
            log('setting the device name to default: "STM32L433CC"')
            dev_name = 'STM32L433CC'
        try:
            ts_pres = int(ts_pres)
        except TypeError:  # if the type is None we just pass
            pass
        try:
            trace_addr0 = int(trace_addr0, 16)
        except TypeError:
            pass
        try:
            trace_addr1 = int(trace_addr1, 16)
        except TypeError:  # if the type is None we just pass
            pass
        try:
            trace_addr2 = int(trace_addr2, 16)
        except TypeError:
            pass
        try:
            trace_addr3 = int(trace_addr3, 16)
        except TypeError:  # if the type is None we just pass
            pass
        try:
            swo_speed = int(swo_speed)
            if swo_speed == 0 or swo_speed > 4000000:
                swo_speed = 4000000
        except:
            swo_speed = 4000000   # use default value
        try:
            cpu_speed = int(cpu_speed)
            if cpu_speed == 0:
                cpu_speed = 80000000
        except:
            cpu_speed = 80000000      # use default value

        return jlink_ser, dev_name, ts_pres, trace_addr0, trace_addr1, trace_addr2, trace_addr3, swo_speed, cpu_speed

    def convert_varsize(size):
        # convert variable size in bytes to the corresponding DWT mask register value
        try:
            size = int(size)
            if size == 1:
                size = 0
            elif size == 2:
                size = 1
            else:
                size = 2    # default (4 bytes)
        except:
            size = 2        # default (4 bytes)
        return size


    # convert in case wrong type given as input
    result = convert_type(jlink_serial, device_name, ts_prescaler, trace_address0, trace_address1,
                          trace_address2, trace_address3, swo_speed, cpu_speed)
    jlink_serial = result[0]
    device_name = result[1]
    ts_prescaler = result[2]
    trace_address0 = result[3]
    trace_address1 = result[4]
    trace_address2 = result[5]
    trace_address3 = result[6]
    swo_speed = result[7]
    cpu_speed = result[8]

    buf = StringIO.StringIO()
    jlinklib = pylink.library.Library(dllpath=jlinklibpath)
    jlink = pylink.JLink(lib=jlinklib, log=buf.write, detailed_log=buf.write)
    if jlink_serial:  # if have several emulators connected, user can specify one by the serial number
        jlink.open(serial_no=jlink_serial)
    else:
        jlink.open()

    jlink.set_tif(pylink.enums.JLinkInterfaces.SWD)
    jlink.connect(device_name, verbose=True)
    jlink.coresight_configure()
    jlink.set_reset_strategy(pylink.enums.JLinkResetStrategyCortexM3.RESETPIN)

    # In case the reset pin is not low must halt MCU before config, throws error in case reset pin is low
    try:
        jlink.halt()
    except:
        pass

    dwt_fun0 = 0xe0001028
    dwt_fun1 = 0xe0001038
    dwt_fun2 = 0xe0001048
    dwt_fun3 = 0xe0001058

    """general registers"""
    demcr = 0xe000edfc  # Debug Exception and Monitor Control Register, DEMCR
    enable_dwt_itm = [0x01000000]

    tpiu_sppr = 0xe00400f0  # Selected Pin Protocol Register, TPIU_SPPR
    async_swo_nrz = [0x00000002]  # Asynchronous SWO, using NRZ encoding. Manchester is not supported

    tpiu_acpr = 0xe0040010  # Asynchronous Clock Prescaler Register, TPIU_ACPR
    # SWO freq = Clock/(SWOSCALAR +1). 0x27 for 2MHz, 0x13 for 4MHz
    swo_rate_prescaler = [int(cpu_speed / swo_speed - 1)]
    if logging_on:
        log("using SWO rate prescaler %d" % int(cpu_speed / swo_speed - 1))

    itm_tcr = 0xe0000e80  # Trace Control Register, ITM_TCR
    # the value 0001000f will enable local timestamps, value 0001000d or 00010009  will disable them
    # the value 00010c0f will also print global timestamps (NOT WORKING)
    # bit 4 = 1 enables TPIU async counter freq (NOT WORKING)
    # the value 0001010f,0001020f,0001030f are prescaler 4,16,64
    if ts_prescaler == 0 or ts_prescaler == 1:
        itm_tcr_config = [0x0001000f]
    elif ts_prescaler == 4:
        itm_tcr_config = [0x0001010f]
    elif ts_prescaler == 16:
        itm_tcr_config = [0x0001020f]
    elif ts_prescaler == 64:
        itm_tcr_config = [0x0001030f]
    else:
        if logging_on:
            log("no or invalid ts_prescaler chosen. Setting it to 64\n")
        itm_tcr_config = [0x0001030f]

    int_prio1 = 0xe0000040  # Interrupt Priority Registers, NVIC_IPR0-NVIC_IPR123
    int_prio2 = 0xe0000000  # Interrupt Priority Registers, NVIC_IPR0-NVIC_IPR123

    dwt_ctrl = 0xe0001000  # Control register, DWT_CTRL
    dwt_ctrl_value = [0x000003ff]

    """comparator configuration"""
    # comp0
    if trace_address0:
        dwt_comp0 = 0xe0001020  # Comparator registers, DWT_COMP0
        dwt_comp0_value = [trace_address0]
        dwt_mask0 = 0xe0001024  # Comparator Mask registers, DWT_MASKn
        dwt_mask0_value = [convert_varsize(size0)]  # size of the mask

        config_value = determine_config_value(trace_pc0, access_mode0)
        dwt_fun0 = 0xe0001028  # Comparator Function registers, DWT_FUNCTIONn
        dwt_fun0_value = [config_value]

        jlink.memory_write32(dwt_comp0, dwt_comp0_value)
        jlink.memory_write32(dwt_mask0, dwt_mask0_value)
        jlink.memory_write32(dwt_fun0, dwt_fun0_value)
        if logging_on:
            log("function0 = " + hex(config_value))
            log("new value comp0 = " + hex(jlink.memory_read32(dwt_comp0, 1)[0]) + "\n")
    else:  # if comparator0 is not used, configure it to not trace anything
        dwt_fun0 = 0xe0001028  # Comparator Function registers, DWT_FUNCTIONn
        jlink.memory_write32(dwt_fun0, [0x0])  # zero will disable the comparator

    # comp1
    if trace_address1:
        dwt_comp1 = 0xe0001030  # Comparator registers, DWT_COMP1
        dwt_comp1_value = [trace_address1]
        dwt_mask1 = 0xe0001034  # Comparator Mask registers, DWT_MASKn
        dwt_mask1_value = [convert_varsize(size1)]  # size of the mask

        config_value1 = determine_config_value(trace_pc1, access_mode1)
        dwt_fun1 = 0xe0001038  # Comparator Function registers, DWT_FUNCTIONn
        dwt_fun1_value = [config_value1]

        jlink.memory_write32(dwt_comp1, dwt_comp1_value)
        jlink.memory_write32(dwt_mask1, dwt_mask1_value)
        jlink.memory_write32(dwt_fun1, dwt_fun1_value)
        if logging_on:
            log("function1 = " + hex(config_value1))
            log("new value comp1 = %" % hex(jlink.memory_read32(dwt_comp1, 1)[0]) + "\n")
    else:  # if comparator0 is not used, configure it to not trace anything
        dwt_fun1 = 0xe0001038  # Comparator Function registers, DWT_FUNCTIONn
        jlink.memory_write32(dwt_fun1, [0x0])  # zero will disable the comparator

    # comp2
    if trace_address2:
        dwt_comp2 = 0xe0001040  # Comparator registers, DWT_COMP2
        dwt_comp2_value = [trace_address2]
        dwt_mask2 = 0xe0001044  # Comparator Mask registers, DWT_MASKn
        dwt_mask2_value = [convert_varsize(size2)]  # size of the mask

        config_value2 = determine_config_value(trace_pc2, access_mode2)
        dwt_fun2 = 0xe0001048  # Comparator Function registers, DWT_FUNCTIONn
        dwt_fun2_value = [config_value2]

        jlink.memory_write32(dwt_comp2, dwt_comp2_value)
        jlink.memory_write32(dwt_mask2, dwt_mask2_value)
        jlink.memory_write32(dwt_fun2, dwt_fun2_value)
        if logging_on:
            log("function2 = " + hex(config_value2))
            log("new value comp2 = " + hex(jlink.memory_read32(dwt_comp2, 1)[0]) + "\n")
    else:  # if comparator0 is not used, configure it to not trace anything
        dwt_fun2 = 0xe0001048  # Comparator Function registers, DWT_FUNCTIONn
        jlink.memory_write32(dwt_fun2, [0x0])  # zero will disable the comparator

    # comp3
    if trace_address3:
        dwt_comp3 = 0xe0001050  # Comparator registers, DWT_COMP3
        dwt_comp3_value = [trace_address3]
        dwt_mask3 = 0xe0001054  # Comparator Mask registers, DWT_MASKn
        dwt_mask3_value = [convert_varsize(size3)]  # size of the mask

        config_value3 = determine_config_value(trace_pc3, access_mode3)
        dwt_fun3 = 0xe0001058  # Comparator Function registers, DWT_FUNCTIONn
        dwt_fun3_value = [config_value3]

        jlink.memory_write32(dwt_comp3, dwt_comp3_value)
        jlink.memory_write32(dwt_mask3, dwt_mask3_value)
        jlink.memory_write32(dwt_fun3, dwt_fun3_value)
        if logging_on:
            log("function3 = " + hex(config_value3))
            log("new value comp3 = " + hex(jlink.memory_read32(dwt_comp3, 1)[0]) + "\n")
    else:  # if comparator0 is not used, configure it to not trace anything
        dwt_fun3 = 0xe0001058  # Comparator Function registers, DWT_FUNCTIONn
        jlink.memory_write32(dwt_fun3, [0x0])  # zero will disable the comparator

    """unclear registers"""
    dbg_mcu_cr = 0xe0042004  # DBG_MCU_CR configures if for example timers stop when in debug mode
    dbg_mcu_cr_value = [0x00003337]  # search in stmcubeIDE projects for DBGMCU and find description

    cs_sw_lock = 0xe0000fb0  # coresight lock register
    cs_sw_lock_unlock = [0xc5acce55]  # c5acce55 will coresight available

    zero = [0x00000000]

    """general registers"""
    jlink.memory_write32(demcr, enable_dwt_itm)
    jlink.memory_write32(tpiu_sppr, async_swo_nrz)
    jlink.memory_write32(tpiu_acpr, swo_rate_prescaler)
    jlink.memory_write32(itm_tcr, itm_tcr_config)
    jlink.memory_write32(int_prio1, zero)
    jlink.memory_write32(int_prio2, zero)

    """code specific registers"""
    jlink.memory_write32(dwt_ctrl, dwt_ctrl_value)
    """jlink.memory_write32(0xe0001030, zero)  # DWT_COMP1
    jlink.memory_write32(0xe0001040, zero)  # DWT_COMP2
    jlink.memory_write32(0xe0001050, zero)  # DWT_COMP3"""

    """unclear registers"""
    jlink.memory_write32(dbg_mcu_cr, dbg_mcu_cr_value)
    value0 = [0x701]
    jlink.memory_write32(0xe0040304, value0)
    # ITM trace enable register, Each ITM_TER provides enable bits for 32 ITM_STIM registers.
    jlink.memory_write32(0xe0000e00, zero)
    jlink.memory_write32(cs_sw_lock, cs_sw_lock_unlock)

    jlink.memory_write32(0xe0000fd0, zero)

    jlink.close()

    return 0


def read_swo_buffer(jlink_serial=None, device_name='STM32L433CC', loop_delay_in_ms=2, filename='swo_read_log', swo_speed=None, cpu_speed=None):
    """
    Starts the SWO reading from the SWO buffer, Resets the MCU but halts the execution

    The function reads the out the whole SWO buffer after every loop_delay_in_ms and saves its raw contents
    together with the python timestamp (time.time()) in the file "filename".
    The reset will toggle the reset pin such that it is on high again. The execution will be halted but
    the SWO reading loop is running.

    Parameters:
      jlink_serial (int): the serial number of the jlink emulator (eg 801012958)
      device_name (string): the device name (eg STM32L433CC)
      loop_delay_in_ms (int): the delay between buffer readouts in ms
      filename (string): name of the file where the buffer readouts and timestamps are saved in

    Returns:
      int: True if the program was halted by Key interrupt

    """

    if logging_on:
        log("starting swo reader...")

    # convert in case wrong type given as input
    try:
        jlink_serial = int(jlink_serial)
    except TypeError:  # if the type is None we just pass
        pass

    if not isinstance(device_name, str):
        log('the device name must be a string like "STM32L433CC" ')
        log('setting the device name to default: "STM32L433CC"')
        device_name = 'STM32L433CC'

    try:
        loop_delay_in_ms = int(loop_delay_in_ms)
    except TypeError:
        pass

    if not isinstance(filename, str):
        log('the file name must be a string like "swo_read_log" ')
        log('setting the file name to default: "swo_read_log"')
        filename = 'swo_read_log'

    try:
        buf = StringIO.StringIO()
        jlinklib = pylink.library.Library(dllpath=jlinklibpath)
        jlink = pylink.JLink(lib=jlinklib, log=buf.write, detailed_log=buf.write)

        # reconnect
        if jlink_serial:  # if have several emulators connected, user can specify one by the serial number
            jlink.open(serial_no=jlink_serial)
        else:
            jlink.open()
        jlink.set_tif(pylink.enums.JLinkInterfaces.SWD)

        try:
            jlink.connect(device_name, verbose=True)
        except:
            log('could not connect to the target')
            return 1

        jlink.coresight_configure()
        jlink.set_reset_strategy(pylink.enums.JLinkResetStrategyCortexM3.RESETPIN)

        if not swo_speed:
            if cpu_speed:
                swo_speed = jlink.swo_supported_speeds(cpu_speed, 10)[0]    # pick the fastest supported speed
            else:
                swo_speed = 4000000   # use the max. SWO speed
        else:
            swo_speed = int(swo_speed)
        if logging_on:
            log('target CPU speed is %d Hz, using SWO speed %d Hz' % (cpu_speed, swo_speed))

        # Start logging serial wire output.
        #if cpu_speed:
        #    jlink.swo_enable(cpu_speed=cpu_speed, swo_speed=swo_speed, port_mask=0xffffffff)   # enable SWO on the target and set the CPU and SWO speed
        #else:
        jlink.swo_start(swo_speed)
        jlink.swo_flush()

        loop_delay_in_s = loop_delay_in_ms/1000

        sleep_overhead = measure_sleep_overhead()

        #jlink.reset(ms=10, halt=True)  # -> also seems to work without this (at least if the target is held in reset state)

        file = open(filename, "a")   # append to file

        # catch the keyboard interrupt telling execution to stop
        try:
            # # DEBUG START
            # numSamples = 3000
            # tmp_arr_global = np.empty([numSamples], dtype=np.float64)
            # tmp_arr_comp = np.empty([numSamples], dtype=np.float64)
            # # DEBUG END
            # vars for loopdelay compensation
            last_global_time = None
            delta = 5e-6
            comp_val = 0
            # for i in range(numSamples): # DEBUG
            while running:
                # log global timestamp and data (if data is available)
                global_time = time.time()
                # tmp_arr_global[i] = global_time # DEBUG
                num_bytes = jlink.swo_num_bytes()
                if num_bytes:
                    data = jlink.swo_read(0, num_bytes, remove=True)
                    file.write(' '.join(str(x) for x in data) + "\n" + str(global_time) + "\n")

                # update loopdelay compensation value (control loop)
                if last_global_time:
                    if global_time - last_global_time > loop_delay_in_s:
                        comp_val -= delta
                    else:
                        comp_val += delta
                # tmp_arr_comp[i] = comp_val # DEBUG
                last_global_time = global_time

                # sleep
                time_used = time.time() - global_time
                time_sleep = (loop_delay_in_s) - sleep_overhead - time_used + comp_val
                if time_sleep > 0:
                    time.sleep(time_sleep)
            # np.savetxt('/home/flocklab/tmp_arr_global.txt', tmp_arr_global) # DEBUG
            # np.savetxt('/home/flocklab/tmp_arr_comp.txt', tmp_arr_comp) # DEBUG
        except KeyboardInterrupt:
            pass
        jlink.swo_stop()
        jlink.swo_flush()
        jlink.close()
        file.flush()
        file.close()

    except:
        log('an error occurred in read_swo_buffer(): %s\n%s' % (str(sys.exc_info()[1]), traceback.format_exc()))
        return 1

    return 0
