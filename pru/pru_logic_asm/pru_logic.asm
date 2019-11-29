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
        .asg C0,         PRUSS_INTC
        .asg C4,         PRUSS_CFG
        .asg 0x00024000, PRU1_CTRL
        .asg 0x4,        PRUSS_SYSCFG_OFS
        .asg 0xC,        PRUSS_CYCLECNT_OFS
        .asg 0x10,       PRUSS_STALLCNT_OFS
        .asg 7,          DBG_GPIO1              ; 0x80     (P8.40)
        .asg 10,         DBG_GPIO2              ; 0x400    (P8.28)
        .asg 0x20,       SYSEVT_GEN_VALID_BIT
        .asg 0x04,       PRU_EVTOUT_2
        .asg 0x0,        BUFFER_ADDR_OFS
        .asg 0x4,        BUFFER_SIZE_OFS
        .asg 0x8,        SAMPLING_RATE_OFS
        .asg 0x0B,       PRU_CRTL_CTR_ON
        .asg 0x03,       PRU_CRTL_CTR_OFF



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
IBUF    .set R10    ; intermediate buffer (R10 - R17, 32 bytes)
IBUF2   .set R18    ; intermediate buffer 2 (R18 - R25, 32 bytes)
IPTR    .set R26    ; instruction pointer for jump to the correct buffer
IPTR0   .set R27    ; initial value for IPTR
CCNT    .set R28    ; cycle counter 1
CCNT2   .set R29    ; cycle counter 2
GPO     .set R30    ; GPIO output pin register
GPI     .set R31    ; GPIO input pin register


; Macros
DELAYU .macro us        ; delay microseconds (pass immediate value)
        LDI32   TMP, 100*us
$M?:    SUB     TMP, TMP, 1
        QBNE    $M?, TMP, 0
        .endm
DELAYI  .macro cycles   ; delay cycles (pass immediate value)
        LDI32   TMP, cycles/2
$M?:    SUB     TMP, TMP, 1
        QBNE    $M?, TMP, 0
        .endm
DELAY   .macro Rx       ; delay cycles (pass register)
$M?:    SUB Rx, Rx, 1
        QBNE    $M?, Rx, 0
        .endm
ASSERT  .macro exp      ; if argument is zero, then stall indefinitely
$M?:    NOP
        QBEQ    $M?, exp, 0
        .endm
CNTR_ON .macro          ; enable cycle counter
        LDI     TMP, PRU_CRTL_CTR_ON
        SBBO    &TMP, CTRL, 0, 1
        .endm
CNTR_OFF    .macro      ; disable cycle counter
        LDI     TMP, PRU_CRTL_CTR_OFF
        SBBO    &TMP, CTRL, 0, 1
        .endm
START_CCNT  .macro      ; start cycle count (capture the current value)
        .if DEBUG
        LBBO    &CCNT, CTRL, PRUSS_CYCLECNT_OFS, 4
        .endif
        .endm
STOP_CCNT   .macro      ; stop cycle count (capture the current value)
        .if DEBUG
        LBBO    &CCNT2, CTRL, PRUSS_CYCLECNT_OFS, 4
        .endif
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
        LDI     PVAL, 0xFF                ; choose a value that is unlikely to be the initial GPIO state
        LDI     SCNT, 0
        LDI     OFS, 0
        LDI32   CTRL, PRU1_CTRL           ; address of CFG register
        LDI     IPTR0, copy_val_alt + 84
        LSR     IPTR0, IPTR0, 2           ; divide by 4 to get #instr instead of address
        MOV     IPTR, IPTR0

        ; load the config
        LDI     TMP, CONFIG_ADDR
        LBBO    &ADDR, TMP, BUFFER_ADDR_OFS, 4
        LBBO    &SIZE, TMP, BUFFER_SIZE_OFS, 4
        ;LBBO    SPS, TMP, SAMPLING_RATE_OFS, 4
        LSR     SIZE2, SIZE, 1
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

    .if DEBUG
        CNTR_ON                           ; enable cycle counter
    .endif

        ; wait for status bit (host event), then signal to host processor that PRU is ready by generating an event
        WBS     GPI, 31                   ; wait until bit set
        LDI32   GPI, 0                    ; clear events
        LDI     GPI.b0, SYSEVT_GEN_VALID_BIT | PRU_EVTOUT_2

    .if USE_32B_BUFFER
        JMP     main_loop_alt
    .endif

        ; sampling loop
main_loop:
        START_CCNT
        PIN_XOR DBG_GPIO1

        ; sample pins (3 cycles)
        AND     CVAL, GPI, 0x1F           ; tracing pins
        AND     TMP, GPO, 0x60            ; actuation pins (TODO include pin 0x80 when debug pin not used!)
        OR      CVAL, TMP, CVAL

        ; value changed?
        QBNE    update_val, CVAL, PVAL
        LDI32   TMP, 0xFFFFFF
        QBEQ    update_val2, SCNT, TMP
        ADD     SCNT, SCNT, 0x01
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
update_val2:
        ; processing and state update (4 cycles)
        LSL     SCNT, SCNT, 8
        OR      TMP2, CVAL, SCNT
        MOV     PVAL, CVAL                ; previous = current
        LDI     SCNT, 0                   ; reset sample counter
        ; 11
        ; copy into the large RAM buffer, takes 1 cycle for 4 bytes in the best/average case
        SBBO    &TMP2, ADDR, OFS, 4
        ; update offset (2 cycles)
        ADD     OFS, OFS, 4
        AND     OFS, OFS, SIZE            ; keep offset in the range 0..SIZE
        ; notify host processor when buffer full
        QBEQ    notify_host, OFS, 0       ; 15
        QBEQ    notify_host2, OFS, SIZE2
        JMP     done
notify_host:
        NOP
notify_host2:
        LDI     GPI.b0, SYSEVT_GEN_VALID_BIT | PRU_EVTOUT_2
done:
        ; 17 cycles
        NOP
        NOP                             ; make it 19 cycles (+1 cycle for jump below)

        STOP_CCNT

    .if DEBUG
        ; read cycle counter
        SUB     TMP, CCNT2, CCNT
        SUB     TMP, TMP, 4               ; subtract 4 cycles
        LDI32   TMP2, 1<<DBG_GPIO2
        JMP     dbg_loop_end
dbg_loop_begin:
        XOR     GPO, GPO, TMP2
        XOR     GPO, GPO, TMP2
        SUB     TMP, TMP, 0x01
dbg_loop_end:
        QBNE    dbg_loop_begin, TMP, 0x00
        XOR     GPO, GPO, TMP2
        ; clear counter value (also clear STALL counter)
        CNTR_OFF
        LDI     TMP, 0
        SBBO    &TMP, CTRL, PRUSS_CYCLECNT_OFS, 4
        CNTR_ON
    .endif

        ; stall the loop to achieve the desired sampling frequency
    .if SAMPLING_FREQ < 10000000                    ; max is ~10MHz
        DELAYI  (200000000/SAMPLING_FREQ - 20)      ; one loop pass takes ~20 cycles
    .endif
        JMP     main_loop




; -----------------------------------------------------------------------

        ; alternative sampling loop, writes 32 bytes at once into the RAM
main_loop_alt:
        PIN_XOR DBG_GPIO1

        ; sample pins (3 cycles)
        AND     CVAL, GPI, 0x1F           ; tracing pins
        AND     TMP, GPO, 0xE0            ; actuation pins
        OR      CVAL, TMP, CVAL

        ; value changed?
        QBNE    update_val_alt, CVAL, PVAL
        LDI32   TMP, 0xFFFFFF
        QBEQ    update_val2_alt, SCNT, TMP
        ADD     SCNT, SCNT, 0x01
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
        MOV     IPTR, IPTR0

        ; when full, copy registers (takes 2 cycles)
        XOUT    10, &IBUF, 32
        XIN     10, &IBUF2, 32

        ; notify other PRU
        SET     GPI.t30

        JMP     done_alt2

done_alt:
        NOP
        NOP
        NOP
done_alt2:
        ; 18 cycles -> make it 19 cycles
        NOP

    .if SAMPLING_FREQ < 10000000
        DELAYI  (200000000/SAMPLING_FREQ - 20)      ; one loop pass takes 20 cycles
    .endif
        JMP     main_loop_alt


; -----------------------------------------------------------------------

; Resource table
        .global pru_remoteproc_ResourceTable
        .sect   ".resource_table:retain", RW
        .retain
        .align  1
        .elfsym pru_remoteproc_ResourceTable,SYM_SIZE(20)
pru_remoteproc_ResourceTable:
        .bits       0x1,32
            ; pru_remoteproc_ResourceTable.base.ver @ 0
        .bits       0,32
            ; pru_remoteproc_ResourceTable.base.num @ 32
        .bits       0,32
            ; pru_remoteproc_ResourceTable.base.reserved[0] @ 64
        .bits       0,32
            ; pru_remoteproc_ResourceTable.base.reserved[1] @ 96
        .bits       0,32
            ; pru_remoteproc_ResourceTable.offset[0] @ 128
