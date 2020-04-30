"""
    usage: python3.7 config_read_parse.py  jlink_serial, device_name, ts_prescaler,
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


def disable_and_reset_all_comparators(jlink_serial=None, device_name='STM32L433CC' ):
    """this function will write 0 as the tracing address for all comparators and disable them"""

    buf = StringIO.StringIO()
    jlink = pylink.JLink(log=buf.write, detailed_log=buf.write)

    if jlink_serial:  # if have several emulators connected, user can specify one by the serial number
        jlink.open(serial_no=jlink_serial)
    else:
        jlink.open()

    jlink.set_tif(pylink.enums.JLinkInterfaces.SWD)
    jlink.connect(device_name, verbose=True)
    jlink.coresight_configure()
    jlink.set_reset_strategy(pylink.enums.JLinkResetStrategyCortexM3.RESETPIN)

    # Have to halt the CPU before writing regs
    jlink.halt()

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

    jlink.open(serial_no=jlink_serial)
    jlink.set_tif(pylink.enums.JLinkInterfaces.SWD)
    jlink.connect(device_name, verbose=True)
    jlink.coresight_configure()
    jlink.set_reset_strategy(pylink.enums.JLinkResetStrategyCortexM3.RESETPIN)
    jlink.halt()

    print("\n", "If the last 4 bits of the function value are zero then the comparator is disabled")
    print("reset value comp0 function = ", hex(jlink.memory_read32(dwt_fun0, 1)[0]))
    print("reset value comp1 function = ", hex(jlink.memory_read32(dwt_fun1, 1)[0]))
    print("reset value comp2 function = ", hex(jlink.memory_read32(dwt_fun2, 1)[0]))
    print("reset value comp3 function = ", hex(jlink.memory_read32(dwt_fun3, 1)[0]), "\n")


# trace address must be in hex
def config_dwt_for_data_trace(jlink_serial=None, device_name='STM32L433CC', ts_prescaler=64,
                              trace_address0=None, access_mode0='w', trace_pc0=0,
                              trace_address1=None, access_mode1='w', trace_pc1=0,
                              trace_address2=None, access_mode2='w', trace_pc2=0,
                              trace_address3=None, access_mode3='w', trace_pc3=0):

    def determine_config_value(trace_pc, access_mode):
        """
        The function implements this configuration table
                    read    write   read/write
                ----------------------------------
        data+PC |    0xe     0xf     0x3
        PC      |    n/a     n/a     0x1
        data    |    0xc     0xd     0x2
        """
        if trace_pc:  # tracing data and PC
            if access_mode == 'r':
                config = 0xe
            elif access_mode == 'w':
                config = 0xf
            elif access_mode == 'rw':
                config = 0x3
            else:
                print("access_mode must be r,w or rw. default is w")
                config = 0xf

        else:  # tracing data only
            if access_mode == 'r':
                config = 0xc
            elif access_mode == 'w':
                config = 0xd
            elif access_mode == 'rw':
                config = 0x2
            else:
                print("access_mode must be r,w or rw. default is w")
                config = 0xd

        return config

    buf = StringIO.StringIO()
    jlink = pylink.JLink(log=buf.write, detailed_log=buf.write)
    if jlink_serial:  # if have several emulators connected, user can specify one by the serial number
        jlink.open(serial_no=jlink_serial)
    else:
        jlink.open()

    jlink.set_tif(pylink.enums.JLinkInterfaces.SWD)
    jlink.connect(device_name, verbose=True)
    jlink.coresight_configure()
    jlink.set_reset_strategy(pylink.enums.JLinkResetStrategyCortexM3.RESETPIN)

    # Have to halt the CPU before writing regs
    jlink.halt()

    dwt_fun0 = 0xe0001028
    dwt_fun1 = 0xe0001038
    dwt_fun2 = 0xe0001048
    dwt_fun3 = 0xe0001058
    print("\n", "function values at start of config")
    print("reset value comp0 function = ", hex(jlink.memory_read32(dwt_fun0, 1)[0]))
    print("reset value comp1 function = ", hex(jlink.memory_read32(dwt_fun1, 1)[0]))
    print("reset value comp2 function = ", hex(jlink.memory_read32(dwt_fun2, 1)[0]))
    print("reset value comp3 function = ", hex(jlink.memory_read32(dwt_fun3, 1)[0]), "\n")


    print("old value comp0 = ", hex(jlink.memory_read32(0xe0001020, 1)[0]))
    print("old value comp1= ", hex(jlink.memory_read32(0xe0001030, 1)[0]))
    print("old value comp2= ", hex(jlink.memory_read32(0xe0001040, 1)[0]))
    print("old value comp3= ", hex(jlink.memory_read32(0xe0001050, 1)[0]), "\n")

    """general registers"""
    demcr = 0xe000edfc  # Debug Exception and Monitor Control Register, DEMCR
    enable_dwt_itm = [0x01000000]

    tpiu_sppr = 0xe00400f0  # Selected Pin Protocol Register, TPIU_SPPR
    async_swo_nrz = [0x00000002]  # Asynchronous SWO, using NRZ encoding.

    tpiu_acpr = 0xe0040010  # Asynchronous Clock Prescaler Register, TPIU_ACPR
    swo_rate_prescaler = [0x00000013]  # SWO freq = Clock/(SWOSCALAR +1). 0x27 for 2MHz, 0x13 for 4MHz

    itm_tcr = 0xe0000e80  # Trace Control Register, ITM_TCR
    # the value 0001000f will enable local timestamps, value 0001000d or 00010009  will disable them
    # the value 00010c0f will also print global timestamps (NOT WORKING)
    # bit 4 = 1 enables TPIU async counter freq (NOT WORKING)
    # the value 0001010f,0001020f,0001030f are prescaler 4,16,64
    if ts_prescaler == 0:
        itm_tcr_config = [0x0001000f]
    elif ts_prescaler == 4:
        itm_tcr_config = [0x0001010f]
    elif ts_prescaler == 16:
        itm_tcr_config = [0x0001020f]
    elif ts_prescaler == 64:
        itm_tcr_config = [0x0001030f]
    else:
        print("no or invalid ts_prescaler chosen. Setting it to 64", "\n")
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
        dwt_mask0_value = [0x00000002]  # size of the mask

        config_value = determine_config_value(trace_pc0, access_mode0)
        dwt_fun0 = 0xe0001028  # Comparator Function registers, DWT_FUNCTIONn
        dwt_fun0_value = [config_value]

        jlink.memory_write32(dwt_comp0, dwt_comp0_value)
        jlink.memory_write32(dwt_mask0, dwt_mask0_value)
        jlink.memory_write32(dwt_fun0, dwt_fun0_value)
        print("function0 = ", hex(config_value))
        print("new value comp0= ", hex(jlink.memory_read32(dwt_comp0, 1)[0]), "\n")
    else:  # if comparator0 is not used, configure it to not trace anything
        dwt_fun0 = 0xe0001028  # Comparator Function registers, DWT_FUNCTIONn
        jlink.memory_write32(dwt_fun0, [0x0])  # zero will disable the comparator

    # comp1
    if trace_address1:
        dwt_comp1 = 0xe0001030  # Comparator registers, DWT_COMP1
        dwt_comp1_value = [trace_address1]
        dwt_mask1 = 0xe0001034  # Comparator Mask registers, DWT_MASKn
        dwt_mask1_value = [0x00000002]  # size of the mask

        config_value1 = determine_config_value(trace_pc1, access_mode1)
        dwt_fun1 = 0xe0001038  # Comparator Function registers, DWT_FUNCTIONn
        dwt_fun1_value = [config_value1]

        jlink.memory_write32(dwt_comp1, dwt_comp1_value)
        jlink.memory_write32(dwt_mask1, dwt_mask1_value)
        jlink.memory_write32(dwt_fun1, dwt_fun1_value)
        print("function1 = ", hex(config_value1))
        print("new value comp1= ", hex(jlink.memory_read32(dwt_comp1, 1)[0]), "\n")
    else:  # if comparator0 is not used, configure it to not trace anything
        dwt_fun1 = 0xe0001038  # Comparator Function registers, DWT_FUNCTIONn
        jlink.memory_write32(dwt_fun1, [0x0])  # zero will disable the comparator

    # comp2
    if trace_address2:
        dwt_comp2 = 0xe0001040  # Comparator registers, DWT_COMP2
        dwt_comp2_value = [trace_address2]
        dwt_mask2 = 0xe0001044  # Comparator Mask registers, DWT_MASKn
        dwt_mask2_value = [0x00000002]  # size of the mask

        config_value2 = determine_config_value(trace_pc2, access_mode2)
        dwt_fun2 = 0xe0001048  # Comparator Function registers, DWT_FUNCTIONn
        dwt_fun2_value = [config_value2]

        jlink.memory_write32(dwt_comp2, dwt_comp2_value)
        jlink.memory_write32(dwt_mask2, dwt_mask2_value)
        jlink.memory_write32(dwt_fun2, dwt_fun2_value)
        print("function2 = ", hex(config_value2))
        print("new value comp2= ", hex(jlink.memory_read32(dwt_comp2, 1)[0]), "\n")
    else:  # if comparator0 is not used, configure it to not trace anything
        dwt_fun2 = 0xe0001048  # Comparator Function registers, DWT_FUNCTIONn
        jlink.memory_write32(dwt_fun2, [0x0])  # zero will disable the comparator

    # comp3
    if trace_address3:
        dwt_comp3 = 0xe0001050  # Comparator registers, DWT_COMP3
        dwt_comp3_value = [trace_address3]
        dwt_mask3 = 0xe0001054  # Comparator Mask registers, DWT_MASKn
        dwt_mask3_value = [0x00000002]  # size of the mask

        config_value3 = determine_config_value(trace_pc3, access_mode3)
        dwt_fun3 = 0xe0001058  # Comparator Function registers, DWT_FUNCTIONn
        dwt_fun3_value = [config_value3]

        jlink.memory_write32(dwt_comp3, dwt_comp3_value)
        jlink.memory_write32(dwt_mask3, dwt_mask3_value)
        jlink.memory_write32(dwt_fun3, dwt_fun3_value)
        print("function3 = ", hex(config_value3))
        print("new value comp3= ", hex(jlink.memory_read32(dwt_comp3, 1)[0]), "\n")
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


def read_swo_buffer(jlink_serial=None, device_name='STM32L433CC', loop_delay_in_ms=2, output_file="swo_read_log"):
    buf = StringIO.StringIO()
    jlink = pylink.JLink(log=buf.write, detailed_log=buf.write)

    # Output the information about the program.
    sys.stdout.write('Press Ctrl-C to Exit\n')

    # reconnect
    if jlink_serial:  # if have several emulators connected, user can specify one by the serial number
        jlink.open(serial_no=jlink_serial)
    else:
        jlink.open()
    jlink.set_tif(pylink.enums.JLinkInterfaces.SWD)
    jlink.connect(device_name, verbose=True)
    jlink.coresight_configure()
    jlink.set_reset_strategy(pylink.enums.JLinkResetStrategyCortexM3.RESETPIN)

    # swo_speed = jlink.swo_supported_speeds(cpu_speed, 10)[0]
    swo_speed = 4000000
    # Start logging serial wire output.
    jlink.swo_start(swo_speed)
    jlink.swo_flush()
    jlink.swo_start(swo_speed)

    loop_delay_in_s = loop_delay_in_ms/1000

    jlink.reset(ms=10, halt=True)  # ATTENTION we need this reset for SWO reader to work.

    file = open(output_file, "w")
    # catch the keyboard interrupt telling execution to stop
    try:
        while True:
            num_bytes = jlink.swo_num_bytes()
            if num_bytes:
                global_time = time.time()
                data = jlink.swo_read(0, num_bytes, remove=True)
                file.write(' '.join(str(x) for x in data) + "\n" + str(global_time) + "\n")
            time.sleep(loop_delay_in_s)  # time in seconds to sleep.
    except KeyboardInterrupt:
        pass
    jlink.swo_stop()
    jlink.swo_flush()
    jlink.close()

    file.close()
    sys.stdout.write('\n')

    return 0  # exit the program execution


def configure_read(jlink_serial, device_name, ts_prescaler=64, loop_delay_in_ms=2,
                   trace_address0=None, access_mode0='w', trace_pc0=0,
                   trace_address1=None, access_mode1='w', trace_pc1=0,
                   trace_address2=None, access_mode2='w', trace_pc2=0,
                   trace_address3=None, access_mode3='w', trace_pc3=0):

    disable_and_reset_all_comparators(jlink_serial, device_name)

    # time.sleep(0.5)

    config_dwt_for_data_trace(jlink_serial, device_name, ts_prescaler=ts_prescaler,
                              trace_address0=trace_address0, access_mode0=access_mode0, trace_pc0=trace_pc0,
                              trace_address1=trace_address1, access_mode1=access_mode1, trace_pc1=trace_pc1,
                              trace_address2=trace_address2, access_mode2=access_mode2, trace_pc2=trace_pc2,
                              trace_address3=trace_address3, access_mode3=access_mode3, trace_pc3=trace_pc3)

    # time.sleep(0.5)

    read_swo_buffer(jlink_serial=jlink_serial, device_name=device_name, loop_delay_in_ms=loop_delay_in_ms)
    # read_swo_buffer(device_name='STM32L433CC', loop_delay_in_ms=2)

if __name__ == '__main__':
    exit(configure_read(sys.argv[1], sys.argv[2], int(sys.argv[3], 10), int(sys.argv[4], 10),
                        int(sys.argv[5], 16), sys.argv[6], int(sys.argv[7]),
                        int(sys.argv[8], 16), sys.argv[9], int(sys.argv[10]),
                        int(sys.argv[11], 16), sys.argv[12], int(sys.argv[13]),
                        int(sys.argv[14], 16), sys.argv[15], int(sys.argv[16]),))
