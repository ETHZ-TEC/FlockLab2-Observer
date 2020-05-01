/*
 * Beaglebone PRU1 firmware config for FlockLab2 GPIO tracing
 *
 * 2020, rdaforno
 */

#ifndef __PRU_LOGIC_CONFIG_H__
#define __PRU_LOGIC_CONFIG_H__

/* parameters */
#define USE_SCRATCHPAD      0           /* utilize PRU0 to transfer the samples */
#define USE_CYCLE_COUNTER   0           /* use hardware cycle counter for timestamping instead of counting loop passes (max. sampling rate will be reduced) */
#define WAIT_FOR_PPS        1           /* whether to wait for rising edge of PPS pin on startup and stop */
#define CONFIG_ADDR         0x0         /* base address where the config is stored (in local data memory) */
#if USE_CYCLE_COUNTER
 #define SAMPLING_RATE      6250000     /* in Hz (do not change) */
#else /* USE_CYCLE_COUNTER */
 #define SAMPLING_RATE      10000000    /* in Hz (1 - 10000000) */
#endif /* USE_CYCLE_COUNTER */

/* fixed values */
#define PRU_FREQ            200000000   /* in Hz (don't change!) */

/* parameter checks */
#if SAMPLING_FREQ > 10000000
 #error "max sampling frequency is 10MHz"
#endif

#if USE_SCRATCHPAD && USE_CYCLE_COUNTER
 #error "cannot use scratchpad and cycle counter at the same time"
#endif

#if USE_CYCLE_COUNTER && (SAMPLING_RATE != (PRU_FREQ >> 5))
 #error "invalid sampling rate"
#endif

#endif /* __PRU_LOGIC_CONFIG_H__ */
