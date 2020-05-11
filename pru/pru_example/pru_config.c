/**
 * Copyright (c) 2020, ETH Zurich, Computer Engineering Group
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are met:
 *
 * * Redistributions of source code must retain the above copyright notice, this
 *   list of conditions and the following disclaimer.
 *
 * * Redistributions in binary form must reproduce the above copyright notice,
 *   this list of conditions and the following disclaimer in the documentation
 *   and/or other materials provided with the distribution.
 *
 * * Neither the name of the copyright holder nor the names of its
 *   contributors may be used to endorse or promote products derived from
 *   this software without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
 * AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
 * IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
 * ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
 * LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
 * CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
 * SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
 * INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
 * CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
 * ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
 * POSSIBILITY OF SUCH DAMAGE.
 *
 * Author: Reto Da Forno
 */


#include <stdint.h>
#include <pru_cfg.h>
#include <pru_intc.h>
#include <pru_ctrl.h>
#include "resource_table_empty.h"


/*
 * General notes:
 * - both PRU cores runs at 200MHz
 * - 4-bus Harvard architecture, no pipelining or cache
 * - registers and busses are 32 bits wide
 * - ALU only supports unsigned integer operations
 * - there is one interrupt controller (INTC)
 * - consult chapter 4 in the am335x reference manual for more details (ti.com/lit/spruh73p)
 * - check the PRU assembly instruction user guide (ti.com/lit/SPRUIJ2)
 * - a resource table is required, but can be empty (use the template in 'resource_table_empty.h')
 *
 * Cycle count:
 * - all register operations take 1 cycle to complete
 * - write instructions are "fire-and-forget" and take ~1 cycle for 4 bytes (writing more bytes will stall the ALU)
 * - 32-bit access to RAM takes ~4 cycles
 * - other read instructions are non-deterministic due to latencies introduced by the interconnect layers
 * - memory accesses are faster when using local addresses
 * - there is a 32-bit hardware counter in the PRU that can be utilized to count execution cycles
 *   (note: once the counter overflows, it stops and must be manually reset)
 *
 * Memory map:
 * - PRU local address space: 0x00000000 - 0x0007FFFF
 *   0x00000000  PRU0 RAM0 / data memory (8kB)
 *   0x00000000  PRU1 RAM1 / data memory (8kB)
 *   0x00002000  PRU0 RAM1 / extra memory for PRU0 (if PRU1 not used, or to share information)
 *   0x00002000  PRU1 RAM0 / extra memory for PRU1 (if PRU0 not used, or to share information)
 *   0x00010000  RAM2 / shared data (12kB)
 * - Global memory map:
 *   0x00000000  RAM0 (8kB)
 *   0x00002000  RAM1 (8kB)
 *   0x00010000  RAM2 (12kB)
 *   0x00022000  PRU0 CTRL
 *   0x00024000  PRU1 CTRL
 *   0x00026000  CFG
 * - Note: use local addresses whenever possible (faster access).
 * - Instruction memory / IRAM (8kB per PRU) is initialized by the host processor and
 *   cannot be directly accessed/modified with PRU instructions.
 *
 * Each PRU has 32 registers, two of which are for direct GPIO access:
 * - bits 0 - 15 in R30 are for the output pins (write access)
 * - bits 0 - 16 in R31 are for the input pins (read access)
 * - bits 30 and 31 in R31 are system event status bits (R31.t30 is connected to host interrupt 0, R31.t31 to host int 1)
 * - R31 has a double function: by setting certain bits in the register (write access), system events can be generated
 *
 * Constant table: often used addresses are stored in a constant table and can be accessed via the variables C0 - C31.
 * Note that the LBCO and SBCO instructions need to be used to read the value from Cn since it is not a direct register access.
 *
 * BeagleBone pin mapping:
 *   P8.28  pru1_r30/r31_10
 *   P8.29  pru1_r30/r31_9
 *   P8.39  pru1_r30/r31_6
 *   P8.40  pru1_r30/r31_7
 *   P8.41  pru1_r30/r31_4
 *   P8.42  pru1_r30/r31_5
 *   P8.43  pru1_r30/r31_2
 *   P8.44  pru1_r30/r31_3
 *   P8.45  pru1_r30/r31_0
 *   P8.46  pru1_r30/r31_1
 *
 * Configuring and enabling system events and interrupts in the INTC:
 * - if needed, set polarity and type of system event through the System Event Polarity Registers (SIPR1 and SPIR2)
 * - map system event to one of the 10 INTC channels by writing to the 16 channel map registers (CHANMAP), 0 has highest priority, 9 has lowest
 * - map each of the INTC channels to one of the 10 host interrupt channels by writing to the 3 host map registers (HOSTMAP)
 *   (note: it is recommended to map INTC channel n to host channel n)
 * - clear system event by writing 1s to the SECR registers
 * - enable system events by writing to IDX field in the system event enable indexed set register (EISR)
 *   (note: event 0 has the highest priority, event 63 the lowest)
 * - enable host interrupt by writing to IDX field in the host interrupt enable indexed set register (HIEISR / HIER)
 * - set global interrupt enable bit (EN bit in GER register)
 *
 * Event interface mapping:
 * - write e.g. 0x100000 to R31 to generate a pulse on pr1_pru_mst_intr[0]_intr_req (system event 16) or
 *   write 0x101111 to generate a pulse on pr1_pru_mst_intr[15]_intr_req (system event 31)
 * - write to R31.t31 to generate PRU host interrupt 1 from local INTC (pru_intr_in[1]) or R31.t30 for host interrupt 0 (pru_intr_in[0])
 * - one can e.g. use host interrupt 0 (R31.t30) for PRU0 and host interrupt 1 (R31.t31) for PRU1
 * - write 0 into R31 to clear pending PRU generated events
 *
 * ------------------------
 *
 * Misc hints and examples:
 *
 * - if only 8 bits, then 4x 8 bits can be squeezed into a register:
 *   MOV R16.b0, R31.b0
​ *   MOV R16.b1​, R31.b0
 *   ...
 *
 * - on PRU0, check if the other PRU is running:
 *   if (PRU1_CTRL.CTRL_bit.RUNSTATE) { ... }
 *
 * - on PRU0, resume the other (halted) PRU:
 *   __halt()                   ; on PRU1
 *   PRU1_CTRL.CTRL_bit.EN = 1  ; on PRU0
 *
 * - read the program counter:
 *   program_counter = PRU1_CTRL.STS_bit.PCTR
 *
 * - enable the clock cycle counter and read the counter value:
 *   PRU1_CTRL.CTRL_bit.CTR_EN = 1
 *   couter_value = PRU1_CTRL.CYCLE
 *
 * - reset the clock cycle counter:
 *   PRU1_CTRL.CTRL_bit.CTR_EN = 0
 *   PRU1_CTRL.CYCLE = 0
 *   PRU1_CTRL.CTRL_bit.CTR_EN = 1
 *
 * - generate pr1_pru_mst_intr[3]_intr_req system event (e.g. to notify a program running on the ARM host processor):
 *   LDI R31.b0, 0x23    ; valid bit = 32, event ID = 3
 *
 * - poll a status bit / wait until status bit is set:
 *   WBS R31, 30
 *
 * - jump to exit if status bit is set (used as a kill signal in this case):
 *   run:
 *     QBBS exit, R31, 31
 *     ...
 *   exit:
 *     HALT
 *
 * - an example on how to configure the INTC:
 *   CT_INTC.CMR4_bit.CH_MAP_19 = 2;   // map system event 19 to INTC channel 2
 *   CT_INTC.HMR0_bit.HINT_MAP_2 = 2;  // map INTC channel 2 to host channel 2
 *   CT_INTC.SECR0 = 0xFFFFFFFF;       // clear all system events
 *   CT_INTC.SECR1 = 0xFFFFFFFF;
 *   __R31 = 0x00000000;               // clear any pending PRU generated events
 *   CT_INTC.EISR = 19;                // enable system event 19
 *   CT_INTC.HIER |= 2;                // enable the host interrupt 2 (same as CT_INTC.HIEISR = 2)
 *   CT_INTC.GER = 0x1;                // set global interrupt enable bit
 *   ...
 *   CT_INTC.SICR = 19;                // later in the code: clear event status after event occurred
 */


/* FlockLab tracing / actuation GPIOs (applies to FlockLab2 rev1.1) */

#define LED1_bits   0x01  // bit0
#define LED2_bits   0x02  // bit1
#define LED3_bits   0x04  // bit2
#define INT1_bits   0x08  // bit3
#define INT2_bits   0x10  // bit4
#define SIG1_bits   0x20  // bit5
#define SIG2_bits   0x40  // bit6
#define nRST_bits   0x80  // bit7


volatile register uint32_t __R30;   // GPO
volatile register uint32_t __R31;   // GPI

void main(void)
{
  /* clear SYSCFG[STANDBY_INIT] to enable OCP master port */
  CT_CFG.SYSCFG_bit.STANDBY_INIT = 0;

  while (1) {
    /* toggle SIG1 (P8.42) and SIG2 (P8.39) pins */
    __R30 ^= SIG1_bits;                     /* in C */
    __asm("    XOR  R30, R30, 0x40");       /* in assembly */

    __delay_cycles(200000000/2);            /* wait 0.5s */
  }

  //__halt();     /* halt the PRU */
}
