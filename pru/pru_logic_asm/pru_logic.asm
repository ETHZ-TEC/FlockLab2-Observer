;-----------------------------------------------------------------
; PRU1 firmware for GPIO tracing
;
; Notes:
; - a core frequency of 200MHz is required (= 5ns per instruction)
; - cycle counter overflows every ~20s and must be reset manually
; - the latency for write operations into the DDR memory are probably non-deterministic (needs investigation)
;
; Inspired by BeagleLogic (https://github.com/abhishek-kakkar/BeagleLogic/tree/master/firmware).
;
; 2019, rdaforno
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
PRU_EVTOUT_2            .set    0x04
PRU_CRTL_CTR_ON         .set    0x0B
PRU_CRTL_CTR_OFF        .set    0x03
BUFFER_ADDR_OFS         .set    0              ; buffer address offset in config structure
BUFFER_SIZE_OFS         .set    4              ; buffer size offset in config structure
START_DELAY_OFS         .set    8              ; delay for the sampling start after releasing the reset pin
PIN_MASK_OFS            .set    12             ; pin mask offset in config structure (defines which pins are sampled)


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
IBUF    .set R10    ; intermediate buffer (R10 - R25, 64 bytes)
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
$M?:    SUB Rx, Rx, 1
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


; -----------------------------------------------------------------------

; Code
        .sect ".text:main"
        .global main

main:
        ; --- init ---
        LDI     CVAL, 0
        LDI     PVAL, 0x0                 ; GPIO initial state
        LDI     SCNT, 1
        LDI     OFS, 0
        LDI32   CTRL, PRU1_CTRL           ; address of CFG register

    .if USE_SCRATCHPAD
        LDI     IPTR0, copy_sample
        LSR     IPTR0, IPTR0, 2           ; divide by 4 to get #instr instead of address
        MOV     IPTR, IPTR0
    .endif ; USE_SCRATCHPAD

        ; load the config
        LDI     TMP, CONFIG_ADDR
        LBBO    &ADDR, TMP, BUFFER_ADDR_OFS, 4
        LBBO    &SIZE, TMP, BUFFER_SIZE_OFS, 4
        LBBO    &PINMASK, TMP, PIN_MASK_OFS, 1      ; apply a custom pin mask if given
        LBBO    &TMP2, TMP, START_DELAY_OFS, 4

        ; if tracing pin mask is invalid (0x0), use the default mask
        QBEQ    use_default_mask, PINMASK, 0
        JMP     skip_use_default_mask
use_default_mask:
        LDI     PINMASK, TRACING_PINS
skip_use_default_mask:
        AND     PINMASK, PINMASK, TRACING_PINS      ; make sure the upper bits are cleared

        LSR     SIZE2, SIZE, 1            ; divide by 2
        SUB     SIZE, SIZE, 1
    .if BUFFER_SIZE
        LDI32   ADDR, BUFFER_ADDR
        LDI32   SIZE, BUFFER_SIZE - 1
        LDI32   SIZE2, BUFFER_SIZE/2
    .endif

        ; parameter check
        ASSERT  SIZE2                     ; make sure size/2 is not 0!

        ; enable OCP master port
        LBCO    &TMP, PRUSS_CFG, PRUSS_SYSCFG_OFS, 4
        CLR     TMP, TMP, 4               ; clear bit 4 (STANDBY_INIT)
        SBCO    &TMP, PRUSS_CFG, PRUSS_SYSCFG_OFS, 4

        ; --- handshake ---
        ; wait for status bit (host event)
        WBS     GPI, 31

        ; clear event status bit (R31.t31)
        LDI     TMP, 22
        SBCO    &TMP, PRUSS_INTC, PRUSS_SICR_OFS, 4

        ; wait for the next rising edge of the PPS signal
        WBC     GPI, PPS_PIN
        WBS     GPI, PPS_PIN

        ; signal to host processor that PRU is ready by generating an event
        LDI     GPI.b0, SYSEVT_GEN_VALID_BIT | PRU_EVTOUT_2

        ; release target reset (P8.40)
        SET     GPO.t7

        ; delay (time offset to sampling start, in seconds)
        ; note: assume at this point that the buffer is large enough to hold all samples during this delay period!
        QBEQ    main_loop, TMP2, 0
        LDI     TMP, 0x0180               ; all pins low, reset high
        SBBO    &TMP, ADDR, OFS, 4        ; copy into RAM buffer
        ADD     OFS, OFS, 4               ; increment buffer offset
        LDI32   CCNT, ((SAMPLING_FREQ << 8) | 0x80)    ; all pins low, reset high (use CCNT register here to temporarily hold the value)
wait_start:
        DELAYI  (CPU_FREQ - 5)            ; wait 1s
        SUB     TMP2, TMP2, 1
        SBBO    &CCNT, ADDR, OFS, 4       ; copy into RAM buffer
        ADD     OFS, OFS, 4               ; increment buffer offset
        AND     OFS, OFS, SIZE            ; keep offset in the range 0..SIZE
        QBNE    wait_start, TMP2, 0


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
        MOV     R10, TMP2
        JMP     copy_done
        MOV     R11, TMP2
        JMP     copy_done
        MOV     R12, TMP2
        JMP     copy_done
        MOV     R13, TMP2
        JMP     copy_done
        MOV     R14, TMP2
        JMP     copy_done
        MOV     R15, TMP2
        JMP     copy_done
        MOV     R16, TMP2
        JMP     copy_done
        MOV     R17, TMP2
        JMP     copy_done
        MOV     R18, TMP2
        JMP     copy_done
        MOV     R19, TMP2
        JMP     copy_done
        MOV     R20, TMP2
        JMP     copy_done
        MOV     R21, TMP2
        JMP     copy_done
        MOV     R22, TMP2
        JMP     copy_done
        MOV     R23, TMP2
        JMP     copy_done
        MOV     R24, TMP2
        JMP     copy_done
        MOV     R25, TMP2
        MOV     IPTR, IPTR0

        ; when full, copy all 8 registers into the scratchpad (takes 1 cycle)
        XOUT    10, &IBUF, 64
        ; notify other PRU
        SET     GPI.t30
        ; alternatively, write directly into a register on PRU0
        ;LDI     TMP, 1          ; TMP = R0
        ;XOUT    14, &TMP, 1     ; not verified!
        JMP     copy_done2

copy_done:
        ADD     IPTR, IPTR, 2             ; increment by 2 instructions
        NOP
        NOP
copy_done2:
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
        DELAYI  (CPU_FREQ/SAMPLING_FREQ - 20)
        JMP     main_loop

exit:

    .if USE_SCRATCHPAD
        JMP     exit_alt                  ; exit method is different if scratchpad is used
    .endif ; USE_SCRATCHPAD

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
        DELAYI  (CPU_FREQ/SAMPLING_FREQ - 2)
        ADD     SCNT, SCNT, 1
        QBBS    wait_for_pps_low, GPI, PPS_PIN

        LDI32   TMP2, 0xFFFFFF
wait_for_pps_high:
        DELAYI  (CPU_FREQ/SAMPLING_FREQ - 6)
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

        ; actuate the target reset pin
        CLR     GPO.t7

        ; copy the final GPIO state into the RAM buffer
        CLR     CVAL.t7
        LSL     SCNT, SCNT, 8
        OR      TMP, CVAL, SCNT
        SBBO    &TMP, ADDR, OFS, 4

        ; send event to host processor to indicate successful program termination
        LDI     GPI.b0, SYSEVT_GEN_VALID_BIT | PRU_EVTOUT_2

        ; halt the PRU
        HALT


exit_alt:

        ; keep track of the number of overflows during the following wait period
        LDI     CCNT, 0                   ; so far no overflows
        LDI32   TMP2, 0xFFFFFF            ; overflow value
        ; wait until the PPS signal goes low
wait_for_pps_low_alt:
        DELAYI  (CPU_FREQ/SAMPLING_FREQ - 3)    ; one loop pass takes 3 cycles
        QBNE    skip_ovfcnt_update, SCNT, TMP2
        ADD     CCNT, CCNT, 1             ; increment overflow counter
        LDI     SCNT, 0                   ; reset sample counter to 0 (because it is incremented by 1 just below)
        ; note: no need to do balancing here, overflow occurs less than once per second; loosing 2 cycles (10ns) in 1 second is negligible
skip_ovfcnt_update:
        ADD     SCNT, SCNT, 1
        QBBS    wait_for_pps_low_alt, GPI, PPS_PIN    ; loop as long as PPS pin bit is set

        ; wait until the PPS signal goes high
wait_for_pps_high_alt:
        DELAYI  (CPU_FREQ/SAMPLING_FREQ - 3)    ; one loop pass takes 3 cycles
        QBNE    skip_ovfcnt_update2, SCNT, TMP2
        ADD     CCNT, CCNT, 1             ; increment overflow counter
        LDI     SCNT, 0                   ; reset sample counter to 0 (because it is incremented by 1 just below)
        ; note: no need to do balancing here, overflow occurs less than once per second; loosing 2 cycles (10ns) in 1 second is negligible
skip_ovfcnt_update2:
        ADD     SCNT, SCNT, 1
        QBBC    wait_for_pps_high_alt, GPI, PPS_PIN   ; loop as long as PPS pin bit is cleared

        ; actuate the target reset pin
        CLR     GPO.t7

        ; compose the value to write
        ; if the overflow counter is zero, then there is just one last value to write
        LDI32   TMP2, 0xFFFFFF00
        OR      TMP2, PVAL, CVAL
        QBNE    get_offset, CCNT, 0
        ; the last value to copy
        CLR     CVAL.t7
        LSL     SCNT, SCNT, 8
        OR      TMP2, CVAL, SCNT
get_offset:
        ; find out which register is the next we can write to
        SUB     TMP, IPTR, IPTR0      ; calculate the offset in #instructions
        LDI     IPTR0, copy_values
        LSR     IPTR0, IPTR0, 2       ; divide by 4 to get #instructions from the top
        ADD     IPTR, IPTR0, TMP
        JMP     IPTR
copy_values:
        MOV     R10, TMP2
        ADD     IPTR, IPTR, 3         ; increment by 3 instructions
        JMP     copy_value_done
        MOV     R11, TMP2
        ADD     IPTR, IPTR, 3
        JMP     copy_value_done
        MOV     R12, TMP2
        ADD     IPTR, IPTR, 3
        JMP     copy_value_done
        MOV     R13, TMP2
        ADD     IPTR, IPTR, 3
        JMP     copy_value_done
        MOV     R14, TMP2
        ADD     IPTR, IPTR, 3
        JMP     copy_value_done
        MOV     R15, TMP2
        ADD     IPTR, IPTR, 3
        JMP     copy_value_done
        MOV     R16, TMP2
        ADD     IPTR, IPTR, 3
        JMP     copy_value_done
        MOV     R17, TMP2
        ADD     IPTR, IPTR, 3
        JMP     copy_value_done
        MOV     R18, TMP2
        ADD     IPTR, IPTR, 3
        JMP     copy_value_done
        MOV     R19, TMP2
        ADD     IPTR, IPTR, 3
        JMP     copy_value_done
        MOV     R20, TMP2
        ADD     IPTR, IPTR, 3
        JMP     copy_value_done
        MOV     R21, TMP2
        ADD     IPTR, IPTR, 3
        JMP     copy_value_done
        MOV     R22, TMP2
        ADD     IPTR, IPTR, 3
        JMP     copy_value_done
        MOV     R23, TMP2
        ADD     IPTR, IPTR, 3
        JMP     copy_value_done
        MOV     R24, TMP2
        ADD     IPTR, IPTR, 3
        JMP     copy_value_done
        MOV     R25, TMP2
        MOV     IPTR, IPTR0
        XOUT    10, &IBUF, 64
        SET     GPI.t30           ; notify other PRU

copy_value_done:
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

exit_done:

        ; send event to host processor to indicate successful program termination
        LDI     GPI.b0, SYSEVT_GEN_VALID_BIT | PRU_EVTOUT_2

        HALT


; -----------------------------------------------------------------------

; PRU0 code for alternative main loop:

;        JMP     check_pru1_data_ready
;copy_pru1_data:
;        LDI     GPI, 0                          ; clear events
;        XIN     10, DI_REG, 64                  ; load 64 bytes
;        SBBO    &DI_REG, ?, 0, 64               ; single block transfer
        ; TODO: increase memory pointer and handle rollover
;check_pru1_data_ready:
;        QBBS    copy_pru1_data, R31, 30
