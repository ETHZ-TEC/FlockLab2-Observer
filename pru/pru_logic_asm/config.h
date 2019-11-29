/*
 * PRU1 firmware config for GPIO tracing
 *
 * 2019, rdaforno
 */

#ifndef __PRU_LOGIC_CONFIG_H__
#define __PRU_LOGIC_CONFIG_H__

/* parameters */
#define DEBUG           0
#define USE_32B_BUFFER  0           /* use alternative main loop with 32 byte register buffer (5MHz max. sampling freq.) */
#define CONFIG_ADDR     0x0         /* base address where the config is stored (in local data memory) */
#ifndef CONFIG_ADDR
 #define BUFFER_SIZE    8          /* must be a power of 2 */
 #define BUFFER_ADDR    0x1000
#else
 #define BUFFER_SIZE    0
#endif
#define SAMPLING_FREQ   1000        /* in Hz (1 - 10000000) */

/* parameter check */
#ifndef CONFIG_ADDR
 #if defined() && ((BUFFER_SIZE & (BUFFER_SIZE - 1)) || (BUFFER_SIZE < (8 + USE_32B_BUFFER * 56)))
  #error "invalid BUFFER_SIZE"
 #endif
#endif /* CONFIG_ADDR */

#if SAMPLING_FREQ > 10000000
 #error "max sampling frequency is 10MHz"
#endif

#endif /* __PRU_LOGIC_CONFIG_H__ */
