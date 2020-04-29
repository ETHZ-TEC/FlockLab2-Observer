;-----------------------------------------------------------------
; Beaglebone PRU1 firmware for FlockLab2 GPIO tracing
;
; 2020, rdaforno
;-----------------------------------------------------------------


; Includes
        .cdecls C,LIST, "config.h"


; Define symbols
PRUSS_INTC              .set    C0
PRUSS_CFG               .set    C4
PRU1_CTRL               .set    0x00024000
PRUSS_SYSCFG_OFS        .set    0x4
PRUSS_CYCLECNT_OFS      .set    0xC
PRUSS_STALLCNT_OFS      .set    0x10
PRUSS_SICR_OFS          .set    0x24
TRACING_PINS            .set    0x7F           ; trace all pins incl. actuation (but without reset pin)
ACTUATION_PINS          .set    0xe0
DBG_GPIO                .set    10             ; 0x400    (P8.28)
PPS_PIN                 .set    8              ; 0x100    (P8.27)
SYSEVT_GEN_VALID_BIT    .set    0x20
PRU_EVTOUT_2            .set    0x04           ; INTC system event number 16 + 4 = 20  (pr1_pru_mst_intr[4]_intr_req)
PRU_CRTL_CTR_ON         .set    0x0B
PRU_CRTL_CTR_OFF        .set    0x03
BUFFER_ADDR_OFS         .set    0              ; buffer address offset in config structure
BUFFER_SIZE_OFS         .set    4              ; buffer size offset in config structure
START_DELAY_OFS         .set    8              ; delay for the sampling start after releasing the reset pin
PIN_MASK_OFS            .set    12             ; pin mask offset in config structure (defines which pins are sampled)
ARM_PRU1_INTERRUPT      .set    22             ; event number (see https://github.com/beagleboard/am335x_pru_package/blob/master/pru_sw/app_loader/include/pruss_intc_mapping.h)
PRU1_PRU0_INTERRUPT     .set    2              ; event number
CONFIG_ADDR_PRU0        .set    0x00002000     ; on PRU0, use config stored in PRU1 data RAM


; Register mapping
TMP     .set R0     ; temporary storage
TMP2    .set R1     ; temporary storage
CTRL    .set R2     ; PRU control register address
CVAL    .set R3     ; current value
PVAL    .set R4     ; previous value
SCNT    .set R5     ; sample counter (counts the number of main loop passes)
ADDR    .set R6     ; buffer address
OFS     .set R7     ; buffer index
SIZE    .set R8     ; buffer size - 1
SIZE2   .set R9     ; half buffer size
DATAIN  .set R10    ; input sample buffer (R10 - R25, 64 bytes)
DATAOUT .set R10    ; output sample buffer (R10 - R25, 64 bytes)
IPTR    .set R26    ; instruction pointer for jump to the correct buffer
IPTR0   .set R27    ; initial value for IPTR
PINMASK .set R28    ; pin mask
CCNT    .set R29    ; cycle counter 1
GPO     .set R30    ; GPIO output pin register
GPI     .set R31    ; GPIO input pin register


; Macros
DELAYU .macro us        ; delay microseconds (pass immediate value)
        LDI32   TMP, 100*us
$M?:    SUB     TMP, TMP, 1
        QBNE    $M?, TMP, 0
        .endm

DELAYI  .macro cycles   ; delay cycles (pass immediate value)
    .if cycles >= 4
        LDI32   TMP, (cycles - 2)/2     ; LDI32 takes 2 cycles
$M?:    SUB     TMP, TMP, 1             ; 1
        QBNE    $M?, TMP, 0             ; 1
    .endif
        .endm

DELAY   .macro Rx       ; delay cycles (pass register)
$M?:    SUB Rx, Rx, 2
        QBNE    $M?, Rx, 0
        .endm

ASSERT  .macro exp      ; if argument is zero, then stall indefinitely
$M?:    NOP
        QBEQ    $M?, exp, 0
        .endm

START_COUNTER   .macro  ; enable the cycle counter
        LDI     TMP, PRU_CRTL_CTR_ON
        SBBO    &TMP, CTRL, 0, 1
        .endm

STOP_COUNTER    .macro  ; disable the cycle counter and reset its value to 0
        LDI     TMP, PRU_CRTL_CTR_OFF
        SBBO    &TMP, CTRL, 0, 1
        LDI     TMP, 0
        SBBO    &TMP, CTRL, PRUSS_CYCLECNT_OFS, 4
        .endm

CAPTURE_CCNT  .macro    ; get the current cycle counter value and store it in CCNT
        LBBO    &CCNT, CTRL, PRUSS_CYCLECNT_OFS, 4
        .endm

CAPTURE_CCNT2 .macro    ; get the current cycle counter value and store it in CCNT2
        LBBO    &CCNT2, CTRL, PRUSS_CYCLECNT_OFS, 4
        .endm

PIN_XOR .macro  pin_bit
        XOR     GPO, GPO, 1<<pin_bit
        .endm

PIN_SET .macro  pin_bit
        SET     GPO, GPO, pin_bit
        .endm

PIN_CLR .macro  pin_bit
        CLR     GPO, GPO, pin_bit
        .endm

DEBUG_PIN_TOGGLE  .macro
        XOR     GPO.b0, GPO.b0, 0x80
        .endm


; -----------------------------------------------------------------------

; Code
        .sect ".text:main"
        .global main

main:
        ; --- init ---

        ; determine whether this is PRU0 or 1
        LDI     TMP, CONFIG_ADDR_PRU0
        LBBO    &TMP2, TMP, BUFFER_ADDR_OFS, 4
        QBNE    main_pru0, TMP2, 0        ; if the buffer offset is valid, then this is PRU0

        ; set inital values
        LDI     CVAL, 0
        LDI     PVAL, 0x0                 ; GPIO initial state
        LDI     SCNT, 1
        LDI32   CTRL, PRU1_CTRL           ; address of CFG register

        ; load the config
        LDI     TMP, CONFIG_ADDR
    .if USE_SCRATCHPAD
        LDI     IPTR0, wait_start_copy_value
        LSR     IPTR0, IPTR0, 2           ; divide by 4 to get #instr instead of address
        MOV     IPTR, IPTR0
    .else
        LDI     OFS, 0
        LBBO    &ADDR, TMP, BUFFER_ADDR_OFS, 4
        LBBO    &SIZE, TMP, BUFFER_SIZE_OFS, 4
        LSR     SIZE2, SIZE, 1            ; divide by 2
        SUB     SIZE, SIZE, 1
    .endif ; USE_SCRATCHPAD
        LBBO    &CCNT, TMP, START_DELAY_OFS, 4      ; use counter register to temporarily hold the start delay
        LBBO    &PINMASK, TMP, PIN_MASK_OFS, 1      ; apply a custom pin mask if given

        ; if tracing pin mask is invalid (0x0), use the default mask
        QBEQ    use_default_mask, PINMASK, 0
        JMP     skip_use_default_mask
use_default_mask:
        LDI     PINMASK, TRACING_PINS
skip_use_default_mask:
        AND     PINMASK, PINMASK, TRACING_PINS      ; make sure the upper bits are cleared

        ; enable OCP master port
        LBCO    &TMP, PRUSS_CFG, PRUSS_SYSCFG_OFS, 4
        CLR     TMP, TMP, 4               ; clear bit 4 (STANDBY_INIT)
        SBCO    &TMP, PRUSS_CFG, PRUSS_SYSCFG_OFS, 4

        ; --- handshake ---
        ; wait for status bit (host event)
        WBS     GPI, 31

        ; clear event status bit (R31.t31)
        LDI     TMP, ARM_PRU1_INTERRUPT
        SBCO    &TMP, PRUSS_INTC, PRUSS_SICR_OFS, 4

    .if WAIT_FOR_PPS
        ; wait for the next rising edge of the PPS signal
        WBC     GPI, PPS_PIN
        WBS     GPI, PPS_PIN
    .endif ; WAIT_FOR_PPS

        ; signal to host processor that PRU is ready by generating an event
        LDI     GPI.b0, SYSEVT_GEN_VALID_BIT | PRU_EVTOUT_2

        ; release target reset (P8.40)
        SET     GPO.t7

        ; delay (time offset to sampling start, in seconds)
        QBEQ    main_loop, CCNT, 0

        ; note: assume at this point that the buffer is large enough to hold all samples during this delay period!
        ; copy the initial state into the buffer
        LDI     PVAL, 0x0180              ; all pins low, reset high, cycle count = 1
    .if !USE_SCRATCHPAD
        SBBO    &PVAL, ADDR, OFS, 4       ; copy into RAM buffer
        ADD     OFS, OFS, 4               ; increment buffer offset
    .else
        MOV     R10, PVAL
        ADD     IPTR, IPTR, 2             ; increment instruction pointer
    .endif ; USE_SCRATCHPAD
        LDI32   TMP2, ((SAMPLING_RATE << 8) | 0x80)    ; all pins low, reset high

wait_start:
        DELAYI  (CPU_FREQ - 8)            ; wait 1s
        SUB     CCNT, CCNT, 1

    .if !USE_SCRATCHPAD
        SBBO    &TMP2, ADDR, OFS, 4       ; copy into RAM buffer
        ADD     OFS, OFS, 4               ; increment buffer offset
        AND     OFS, OFS, SIZE            ; keep offset in the range 0..SIZE
        NOP
        NOP
        NOP
    .else
        ; copy value into local registers (6 cycles)
        JMP     IPTR                  ; jump target must be in # instructions from the start
wait_start_copy_value:
        MOV     R10, TMP2
        JMP     wait_start_copy_value_done
        MOV     R11, TMP2
        JMP     wait_start_copy_value_done
        MOV     R12, TMP2
        JMP     wait_start_copy_value_done
        MOV     R13, TMP2
        JMP     wait_start_copy_value_done
        MOV     R14, TMP2
        JMP     wait_start_copy_value_done
        MOV     R15, TMP2
        JMP     wait_start_copy_value_done
        MOV     R16, TMP2
        JMP     wait_start_copy_value_done
        MOV     R17, TMP2
        JMP     wait_start_copy_value_done
        MOV     R18, TMP2
        JMP     wait_start_copy_value_done
        MOV     R19, TMP2
        JMP     wait_start_copy_value_done
        MOV     R20, TMP2
        JMP     wait_start_copy_value_done
        MOV     R21, TMP2
        JMP     wait_start_copy_value_done
        MOV     R22, TMP2
        JMP     wait_start_copy_value_done
        MOV     R23, TMP2
        JMP     wait_start_copy_value_done
        MOV     R24, TMP2
        JMP     wait_start_copy_value_done
        MOV     R25, TMP2
        MOV     IPTR, IPTR0
        ; when full, copy all 8 registers into the scratchpad (takes 1 cycle)
        XOUT    10, &DATAOUT, 64
        ; notify other PRU
        LDI     GPI.b0, SYSEVT_GEN_VALID_BIT | PRU1_PRU0_INTERRUPT
        JMP     wait_start_copy_value_done2
wait_start_copy_value_done:
        ADD     IPTR, IPTR, 2       ; increment instruction pointer
        NOP
        NOP
wait_start_copy_value_done2:
    .endif ; USE_SCRATCHPAD
        QBNE    wait_start, CCNT, 0

    .if USE_SCRATCHPAD
        LDI     IPTR0, copy_sample
        LSR     IPTR0, IPTR0, 2           ; divide by 4 to get #instr instead of address
        MOV     IPTR, IPTR0
    .endif ; USE_SCRATCHPAD


        ; --- sampling loop ---
main_loop:

        ; sample pins (3 cycles)
        AND     CVAL, GPI, PINMASK        ; sample tracing and actuation pins

        QBBS    set_pps_bit, GPI, PPS_PIN
        JMP     set_pps_bit_end
set_pps_bit:
        SET     CVAL.t7
set_pps_bit_end:

        ; check whether value has changed (4 cycles)
        QBNE    update_val, CVAL, PVAL
        LDI32   TMP, 0xFFFFFF             ; pseudo instruction, takes 2 cycles -> if need be, this value could be permanently held in a register instead
        QBEQ    update_val2, SCNT, TMP
        ; value has not changed -> just increment counter and wait (10 cycles)
        ADD     SCNT, SCNT, 1
        NOP
        NOP
        NOP
        NOP
        NOP
        NOP
        NOP
        NOP
        JMP     done

update_val:
        NOP
        NOP
        NOP
update_val2:
        ; append counter to the value and reset counter (4 cycles)
        LSL     SCNT, SCNT, 8
        OR      TMP, CVAL, SCNT
        MOV     PVAL, CVAL                ; previous = current
        LDI     SCNT, 1                   ; reset sample counter to value 1

    .if !USE_SCRATCHPAD

        ; copy value into the RAM buffer, update the offset (3 cycles)
        SBBO    &TMP, ADDR, OFS, 4        ; takes 1 cycle for 4 bytes in the best/average case
        ; update offset (2 cycles)
        ADD     OFS, OFS, 4
        AND     OFS, OFS, SIZE            ; keep offset in the range 0..SIZE
        ; notify host processor when buffer full (3 cycles)
        QBEQ    notify_host, OFS, 0
        QBEQ    notify_host2, OFS, SIZE2
        JMP     done

    .else ; USE_SCRATCHPAD

        ; copy value into local registers (6 cycles)
        JMP     IPTR                      ; jump target must be in # instructions from the start
copy_sample:
        MOV     R10, TMP
        JMP     copy_done
        MOV     R11, TMP
        JMP     copy_done
        MOV     R12, TMP
        JMP     copy_done
        MOV     R13, TMP
        JMP     copy_done
        MOV     R14, TMP
        JMP     copy_done
        MOV     R15, TMP
        JMP     copy_done
        MOV     R16, TMP
        JMP     copy_done
        MOV     R17, TMP
        JMP     copy_done
        MOV     R18, TMP
        JMP     copy_done
        MOV     R19, TMP
        JMP     copy_done
        MOV     R20, TMP
        JMP     copy_done
        MOV     R21, TMP
        JMP     copy_done
        MOV     R22, TMP
        JMP     copy_done
        MOV     R23, TMP
        JMP     copy_done
        MOV     R24, TMP
        JMP     copy_done
        MOV     R25, TMP
        MOV     IPTR, IPTR0
        ; when full, copy all 8 registers into the scratchpad (takes 1 cycle)
        XOUT    10, &DATAOUT, 64
        ; notify other PRU
        LDI     GPI.b0, SYSEVT_GEN_VALID_BIT | PRU1_PRU0_INTERRUPT
        ; alternatively, write directly into a register on PRU0
        ;LDI     TMP, 1          ; TMP = R0
        ;XOUT    14, &TMP, 1     ; not verified!
        JMP     done

copy_done:
        ADD     IPTR, IPTR, 2             ; increment by 2 instructions
        NOP
        JMP     done
    .endif ; USE_SCRATCHPAD


notify_host:
        NOP
notify_host2:
        LDI     GPI.b0, SYSEVT_GEN_VALID_BIT | PRU_EVTOUT_2

done:
        ; check if it is time to stop
        QBBS    exit, GPI, 31             ; jump to exit if PRU1 status bit set

        ; add nops here to get exactly 19 cycles (1 cycle is for the main loop jump below)
        NOP

        ; stall the loop to achieve the desired sampling frequency
        DELAYI  (CPU_FREQ/SAMPLING_RATE - 20)
        JMP     main_loop

exit:

    .if !USE_SCRATCHPAD

    .if WAIT_FOR_PPS

        ; store current cycle counter before continuing to avoid an overflow in the wait_for_pps_low loop
        LSL     SCNT, SCNT, 8
        OR      PVAL, CVAL, SCNT          ; use PVAL register since it is not needed anymore at this point
        LDI     SCNT, 1                   ; reset sample counter to value 1
        SBBO    &PVAL, ADDR, OFS, 4       ; copy into RAM buffer
        ADD     OFS, OFS, 4               ; increment buffer offset
        AND     OFS, OFS, SIZE            ; keep offset in the range 0..SIZE

        ; wait for next rising edge of PPS signal
        ; note: WBC/WBS won't work here, since we need to count the number of cycles
wait_for_pps_low:
        DELAYI  (CPU_FREQ/SAMPLING_RATE - 2)
        ADD     SCNT, SCNT, 1
        QBBS    wait_for_pps_low, GPI, PPS_PIN

        LDI32   TMP2, 0xFFFFFF
wait_for_pps_high:
        DELAYI  (CPU_FREQ/SAMPLING_RATE - 6)
        QBEQ    reset_counter, SCNT, TMP2
        ADD     SCNT, SCNT, 1
        NOP
        NOP
        JMP     end_reset_counter
reset_counter:
        SBBO    &PVAL, ADDR, OFS, 4       ; copy into RAM buffer
        ADD     OFS, OFS, 4               ; increment buffer offset
        AND     OFS, OFS, SIZE            ; keep offset in the range 0..SIZE
        LDI     SCNT, 1                   ; reset sample counter to value 1
end_reset_counter:
        QBBC    wait_for_pps_high, GPI, PPS_PIN

    .endif ; WAIT_FOR_PPS

        ; actuate the target reset pin
        CLR     GPO.t7

        ; copy the final GPIO state into the RAM buffer
        CLR     CVAL.t7
        LSL     SCNT, SCNT, 8
        OR      TMP, CVAL, SCNT
        SBBO    &TMP, ADDR, OFS, 4

    .else ; USE_SCRATCHPAD

        ; keep track of the number of overflows during the following wait period
        LDI     CCNT, 0                   ; so far no overflows
        LDI32   TMP2, 0xFFFFFF            ; overflow value

    .if WAIT_FOR_PPS

        ; wait until the PPS signal goes low
wait_for_pps_low_alt:
        DELAYI  (CPU_FREQ/SAMPLING_RATE - 3)    ; one loop pass takes 3 cycles
        QBNE    skip_ovfcnt_update, SCNT, TMP2
        ADD     CCNT, CCNT, 1             ; increment overflow counter
        LDI     SCNT, 0                   ; reset sample counter to 0 (because it is incremented by 1 just below)
        ; note: no need to do balancing here, overflow occurs less than once per second; loosing 2 cycles (10ns) in 1 second is negligible
skip_ovfcnt_update:
        ADD     SCNT, SCNT, 1
        QBBS    wait_for_pps_low_alt, GPI, PPS_PIN    ; loop as long as PPS pin bit is set

        ; wait until the PPS signal goes high
wait_for_pps_high_alt:
        DELAYI  (CPU_FREQ/SAMPLING_RATE - 3)    ; one loop pass takes 3 cycles
        QBNE    skip_ovfcnt_update2, SCNT, TMP2
        ADD     CCNT, CCNT, 1             ; increment overflow counter
        LDI     SCNT, 0                   ; reset sample counter to 0 (because it is incremented by 1 just below)
        ; note: no need to do balancing here, overflow occurs less than once per second; loosing 2 cycles (10ns) in 1 second is negligible
skip_ovfcnt_update2:
        ADD     SCNT, SCNT, 1
        QBBC    wait_for_pps_high_alt, GPI, PPS_PIN   ; loop as long as PPS pin bit is cleared

    .endif ; WAIT_FOR_PPS

        ; actuate the target reset pin
        CLR     GPO.t7

        ; compose the value to write
        ; if the overflow counter is zero, then there is just one last value to write
        LDI32   TMP2, 0xFFFFFF00
        OR      TMP2, TMP2, CVAL
        QBNE    get_offset, CCNT, 0
        ; the last value to copy
        CLR     CVAL.t7
        LSL     SCNT, SCNT, 8
        OR      TMP2, CVAL, SCNT
get_offset:
        ; find out which register is the next we can write to
        SUB     TMP, IPTR, IPTR0      ; calculate the offset in #instructions
        LDI     IPTR0, jump_to_register
        LSR     IPTR0, IPTR0, 2       ; divide by 4 to get #instructions from the top
        ADD     IPTR, IPTR0, TMP
copy_values:
        JMP     IPTR
jump_to_register:
        MOV     R10, TMP2
        JMP     copy_value_done
        MOV     R11, TMP2
        JMP     copy_value_done
        MOV     R12, TMP2
        JMP     copy_value_done
        MOV     R13, TMP2
        JMP     copy_value_done
        MOV     R14, TMP2
        JMP     copy_value_done
        MOV     R15, TMP2
        JMP     copy_value_done
        MOV     R16, TMP2
        JMP     copy_value_done
        MOV     R17, TMP2
        JMP     copy_value_done
        MOV     R18, TMP2
        JMP     copy_value_done
        MOV     R19, TMP2
        JMP     copy_value_done
        MOV     R20, TMP2
        JMP     copy_value_done
        MOV     R21, TMP2
        JMP     copy_value_done
        MOV     R22, TMP2
        JMP     copy_value_done
        MOV     R23, TMP2
        JMP     copy_value_done
        MOV     R24, TMP2
        JMP     copy_value_done
        MOV     R25, TMP2
        MOV     IPTR, IPTR0
        XOUT    10, &DATAOUT, 64
        LDI     GPI.b0, SYSEVT_GEN_VALID_BIT | PRU1_PRU0_INTERRUPT    ; notify PRU0
        JMP     copy_value_done2
copy_value_done:
        ADD     IPTR, IPTR, 2         ; increment by 2 instructions
copy_value_done2:
        ; are there more values to copy? -> if not, continue by filling up the unused registers with zeros
        QBEQ    fill_empty_space, CCNT, 0
        SUB     CCNT, CCNT, 1
        ; more overflow values to copy?
        QBNE    copy_values, CCNT, 0
        ; prepare the last value
        CLR     CVAL.t7
        LSL     SCNT, SCNT, 8
        OR      TMP2, CVAL, SCNT
        JMP     copy_values
fill_empty_space:
        ; fill the unused registers with zeros
        LDI     TMP2, 0
        QBNE    copy_values, IPTR, IPTR0

    .endif ; USE_SCRATCHPAD

        ; send event to host processor to indicate successful program termination
        LDI     GPI.b0, SYSEVT_GEN_VALID_BIT | PRU_EVTOUT_2

        ; stop PRU
        HALT


; -----------------------------------------------------------------------

main_pru0:
        ; --- init ---

        ; load the config and set the initial values
        LDI     TMP, CONFIG_ADDR_PRU0
        LBBO    &ADDR, TMP, BUFFER_ADDR_OFS, 4
        LBBO    &SIZE, TMP, BUFFER_SIZE_OFS, 4
        LDI     OFS, 0
        LSR     SIZE2, SIZE, 1            ; divide by 2
        SUB     SIZE, SIZE, 1

        ; enable OCP master port
        LBCO    &TMP, PRUSS_CFG, PRUSS_SYSCFG_OFS, 4
        CLR     TMP, TMP, 4               ; clear bit 4 (STANDBY_INIT)
        SBCO    &TMP, PRUSS_CFG, PRUSS_SYSCFG_OFS, 4

        ; clear event status bit (R31.t30)
        LDI     TMP, PRU1_PRU0_INTERRUPT
        SBCO    &TMP, PRUSS_INTC, PRUSS_SICR_OFS, 4

main_loop_pru0:
        ; wait until PRU1 signals that new data is available in the scratchpad
        WBS     GPI, 30
        ;SET     GPO.t14                   ; for debugging (P8.12)
        ; clear event status bit (R31.t30)
        LDI     TMP, (PRU1_PRU0_INTERRUPT + 16)
        SBCO    &TMP, PRUSS_INTC, PRUSS_SICR_OFS, 4
        ; load 64 bytes from the scratchpad and copy the data into the buffer in memory
        XIN     10, &DATAIN, 64
        SBBO    &DATAIN, ADDR, OFS, 64        ; block transfer, takes ~100ns in the best case
        ; keep offset in the range 0..SIZE
        ADD     OFS, OFS, 64
        AND     OFS, OFS, SIZE
        ;CLR     GPO.t14                   ; for debugging (P8.12)
        ; notify host processor when buffer full
        QBEQ    notify_host_pru0, OFS, 0
        QBEQ    notify_host_pru0, OFS, SIZE2
        JMP     main_loop_pru0
notify_host_pru0:
        LDI     GPI.b0, SYSEVT_GEN_VALID_BIT | PRU_EVTOUT_2
        JMP     main_loop_pru0

        HALT


