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
PRUSYNC_PIN             .set    9              ;          (P8.29)
SYSEVT_GEN_VALID_BIT    .set    0x20
PRU_EVTOUT_2            .set    0x04
PRU_CRTL_CTR_ON         .set    0x0B
PRU_CRTL_CTR_OFF        .set    0x03
BUFFER_ADDR_OFS         .set    0x0            ; buffer address offset in config structure
BUFFER_SIZE_OFS         .set    0x4            ; buffer size offset in config structure
PIN_MASK_OFS            .set    0x8            ; pin mask offset in config structure (defines which pins are sampled)


; Register mapping
TMP     .set R0     ; temporary storage
TMP2    .set R1     ; temporary storage
CTRL    .set R2     ; PRU control register address
CVAL    .set R3     ; current value
PVAL    .set R4     ; previous value
SCNT    .set R5     ; sample counter
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
        ; init
        LDI     CVAL, 0
        LDI     PVAL, 0x0                 ; choose a value that is unlikely to be the initial GPIO state
        LDI     SCNT, 1
        LDI     OFS, 0
        LDI32   CTRL, PRU1_CTRL           ; address of CFG register
        LDI     IPTR0, copy_val_alt
        LSR     IPTR0, IPTR0, 2           ; divide by 4 to get #instr instead of address
        MOV     IPTR, IPTR0

        ; load the config
        LDI     TMP, CONFIG_ADDR
        LBBO    &ADDR, TMP, BUFFER_ADDR_OFS, 4
        LBBO    &SIZE, TMP, BUFFER_SIZE_OFS, 4
        LBBO    &PINMASK, TMP, PIN_MASK_OFS, 1      ; apply a custom pin mask if given

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

        ; wait for status bit (host event), then signal to host processor that PRU is ready by generating an event
        WBS     GPI, 31                   ; wait until bit set
        LDI     GPI.b0, SYSEVT_GEN_VALID_BIT | PRU_EVTOUT_2

        ; clear event status bit (R31.t31)
        LDI     TMP, 22
        SBCO    &TMP, PRUSS_INTC, PRUSS_SICR_OFS, 4

        ; wait for the next rising edge of the PPS signal
        WBC     GPI, PPS_PIN
        WBS     GPI, PPS_PIN

        ; release target reset (P8.40)
        SET     GPO.t7

    .if USE_32B_BUFFER
        JMP     main_loop_alt
    .endif

        ; sampling loop
main_loop:

        ; sample pins
        AND     CVAL, GPI, PINMASK        ; sample tracing and actuation pins

        QBBS    set_pps_bit, GPI, PPS_PIN
        JMP     set_pps_bit_end
set_pps_bit:
        SET     CVAL.t7
set_pps_bit_end:

        ; value changed?
        QBNE    update_val, CVAL, PVAL    ; 4
        LDI32   TMP, 0xFFFFFF             ; pseudo instruction, takes 2 cycles
        QBEQ    update_val2, SCNT, TMP    ; 7
        ADD     SCNT, SCNT, 1
        NOP
        NOP
        NOP
        NOP
        NOP
        NOP
        NOP
        NOP
        JMP     done                      ; 17

update_val:
        NOP
        NOP
        NOP                               ; 7
update_val2:
        ; processing and state update (4 cycles)
        LSL     SCNT, SCNT, 8
        OR      TMP, CVAL, SCNT
        MOV     PVAL, CVAL                ; previous = current
        LDI     SCNT, 1                   ; reset sample counter to value 1
        ; copy into the large RAM buffer, takes 1 cycle for 4 bytes in the best/average case
        SBBO    &TMP, ADDR, OFS, 4
        ; update offset (2 cycles)
        ADD     OFS, OFS, 4
        AND     OFS, OFS, SIZE            ; keep offset in the range 0..SIZE
        ; notify host processor when buffer full
        QBEQ    notify_host, OFS, 0       ; 15
        QBEQ    notify_host2, OFS, SIZE2  ; 16
        JMP     done                      ; 17
notify_host:
        NOP
notify_host2:
        LDI     GPI.b0, SYSEVT_GEN_VALID_BIT | PRU_EVTOUT_2
done:
        ; check if it is time to stop
        QBBS    exit, GPI, 31             ; jump to exit if PRU1 status bit set

        ; add nops here to get exactly 19 cycles (1 cycle is for the jump below)
        NOP

        ; stall the loop to achieve the desired sampling frequency
        DELAYI  (200000000/SAMPLING_FREQ - 20)      ; one loop pass takes ~20 cycles
        JMP     main_loop

exit:
        ; store current cycle counter before continuing to avoid an overflow
        LSL     SCNT, SCNT, 8
        OR      TMP, CVAL, SCNT
        LDI     SCNT, 1                   ; reset sample counter to value 1
        SBBO    &TMP, ADDR, OFS, 4        ; copy into RAM buffer
        ADD     OFS, OFS, 4               ; increment buffer offset
        AND     OFS, OFS, SIZE            ; keep offset in the range 0..SIZE

        ; wait for next rising edge of PPS signal
        ; note: WBC/WBS won't work here, since we need to count the number of cycles
wait_for_pps_low:
        DELAYI  (200000000/SAMPLING_FREQ - 2)       ; one loop pass takes 2 cycles
        ADD     SCNT, SCNT, 1
        QBBS    wait_for_pps_low, GPI, PPS_PIN
wait_for_pps_high:
        DELAYI  (200000000/SAMPLING_FREQ - 2)
        ADD     SCNT, SCNT, 1
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


; -----------------------------------------------------------------------

        ; alternative sampling loop, writes 32 bytes at once into the RAM
main_loop_alt:
        ;PIN_XOR DBG_GPIO
        NOP

        ; sample pins (3 cycles)
        AND     CVAL, GPI, PINMASK

        ; value changed?
        QBNE    update_val_alt, CVAL, PVAL
        LDI32   TMP, 0xFFFFFF             ; pseudo instruction, takes 2 cycles
        QBEQ    update_val2_alt, SCNT, TMP
        ADD     SCNT, SCNT, 1
        NOP
        NOP
        NOP
        NOP
        NOP
        NOP
        JMP     done_alt

update_val_alt:
        NOP
        NOP
        NOP
update_val2_alt:
        ; 7
        ; value processing and state update (4 cycles)
        LSL     SCNT, SCNT, 8
        OR      TMP2, CVAL, SCNT
        MOV     PVAL, CVAL                ; previous = current
        LDI     SCNT, 0                   ; reset sample counter
        ; write into intermediate buffer (4 cycles or 17 cycles)
        JMP     IPTR                      ; jump must be in # instructions from the start
copy_val_alt:
        ; 12
        MOV     R10, TMP2
        ADD     IPTR, IPTR, 3             ; increment by 3 instructions
        JMP     done_alt
        MOV     R11, TMP2
        ADD     IPTR, IPTR, 3
        JMP     done_alt
        MOV     R12, TMP2
        ADD     IPTR, IPTR, 3
        JMP     done_alt
        MOV     R13, TMP2
        ADD     IPTR, IPTR, 3
        JMP     done_alt
        MOV     R14, TMP2
        ADD     IPTR, IPTR, 3
        JMP     done_alt
        MOV     R15, TMP2
        ADD     IPTR, IPTR, 3
        JMP     done_alt
        MOV     R16, TMP2
        ADD     IPTR, IPTR, 3
        JMP     done_alt
        MOV     R17, TMP2
        ADD     IPTR, IPTR, 3
        JMP     done_alt
        MOV     R18, TMP2
        ADD     IPTR, IPTR, 3
        JMP     done_alt
        MOV     R19, TMP2
        ADD     IPTR, IPTR, 3
        JMP     done_alt
        MOV     R20, TMP2
        ADD     IPTR, IPTR, 3
        JMP     done_alt
        MOV     R21, TMP2
        ADD     IPTR, IPTR, 3
        JMP     done_alt
        MOV     R22, TMP2
        ADD     IPTR, IPTR, 3
        JMP     done_alt
        MOV     R23, TMP2
        ADD     IPTR, IPTR, 3
        JMP     done_alt
        MOV     R24, TMP2
        ADD     IPTR, IPTR, 3
        JMP     done_alt
        MOV     R25, TMP2
        MOV     IPTR, IPTR0

        ; when full, copy all registers into the scratchpad (takes 1 cycle)
        XOUT    10, &IBUF, 64       ; 64 bytes

        ; notify other PRU
        SET     GPI.t30

        ; alternatively, write directly into a register on PRU0
        ;LDI     TMP, 1          ; TMP = R0
        ;XOUT    14, &TMP, 1     ; not verified!

        JMP     done_alt2

done_alt:
        NOP
        NOP
        NOP
done_alt2:
        QBBS    exit_alt, GPI, 31       ; jump to exit if PRU1 status bit set

        ; add NOPs here to make one loop pass 19 cycles long
        NOP
        NOP

        DELAYI  (200000000/SAMPLING_FREQ - 20)  ; one loop pass takes 20 cycles
        JMP     main_loop_alt

exit_alt:
        ; find out how many bytes have not yet been transferred
        QBEQ    exit_halt, IPTR, IPTR0          ; no bytes to transfer?
        LDI     TMP, 0
regcnt_loop:
        ADD     TMP, TMP, 1
        SUB     IPTR, IPTR, 3
        QBNE    regcnt_loop, IPTR, IPTR0
        ; at this point, TMP2 still contains the last stored value
        MOV     PVAL, TMP2
        ; fill up the empty space with the last captured value
        LDI     TMP2, duplicate_last
        ADD     TMP2, TMP2, TMP
        JMP     TMP2
duplicate_last:
        MOV     R10, PVAL
        MOV     R11, PVAL
        MOV     R12, PVAL
        MOV     R13, PVAL
        MOV     R14, PVAL
        MOV     R15, PVAL
        MOV     R16, PVAL
        MOV     R17, PVAL
        MOV     R18, PVAL
        MOV     R19, PVAL
        MOV     R20, PVAL
        MOV     R21, PVAL
        MOV     R22, PVAL
        MOV     R23, PVAL
        MOV     R24, PVAL
        MOV     R25, PVAL

        ; copy remaining data into scratchpad and signal PRU0
        XOUT    10, &IBUF, 64       ; 64 bytes
        SET     GPI.t30

exit_halt:
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
