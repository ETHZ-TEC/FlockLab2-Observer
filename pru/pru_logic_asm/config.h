/*
 * PRU1 firmware config for GPIO tracing
 *
 * 2019, rdaforno
 */

#ifndef __PRU_LOGIC_CONFIG_H__
#define __PRU_LOGIC_CONFIG_H__

/* parameters */
#define SAMPLING_FREQ   10000000    /* in Hz (1 - 10000000) */
#define USE_SCRATCHPAD  0           /* utilize PRU0 to transfer the samples */
#define CONFIG_ADDR     0x0         /* base address where the config is stored (in local data memory) */
#ifndef CONFIG_ADDR
 #define BUFFER_SIZE    8           /* must be a power of 2 */
 #define BUFFER_ADDR    0x1000
#else
 #define BUFFER_SIZE    0
#endif

/* fixed values */
#define CPU_FREQ        200000000   /* in Hz (don't change!) */

/* parameter check */
#ifndef CONFIG_ADDR
 #if defined() && ((BUFFER_SIZE & (BUFFER_SIZE - 1)) || (BUFFER_SIZE < (8 + USE_SCRATCHPAD * 120)))
  #error "invalid BUFFER_SIZE"
 #endif
#endif /* CONFIG_ADDR */

#if SAMPLING_FREQ > 10000000
 #error "max sampling frequency is 10MHz"
#endif

#endif /* __PRU_LOGIC_CONFIG_H__ */
