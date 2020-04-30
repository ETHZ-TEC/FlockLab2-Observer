/*
 * PRU1 firmware config for GPIO tracing
 *
 * 2019, rdaforno
 */

#ifndef __PRU_LOGIC_CONFIG_H__
#define __PRU_LOGIC_CONFIG_H__

/* parameters */
#define SAMPLING_RATE       10000000    /* in Hz (1 - 10000000) */
#define USE_SCRATCHPAD      1           /* utilize PRU0 to transfer the samples */
#define WAIT_FOR_PPS        1           /* whether to wait for rising edge of PPS pin on startup and stop */
#define CONFIG_ADDR         0x0         /* base address where the config is stored (in local data memory) */

/* fixed values */
#define CPU_FREQ        200000000   /* in Hz (don't change!) */

#if SAMPLING_FREQ > 10000000
 #error "max sampling frequency is 10MHz"
#endif

#endif /* __PRU_LOGIC_CONFIG_H__ */
