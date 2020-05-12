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
 * Authors: Reto Da Forno
 *          Roman Trueb
 */

/*
 * FlockLab2 logic/GPIO tracing user space program for the BeagleBone Green
 */

// INCLUDES
#include <errno.h>
#include <stdbool.h>
#include <string.h>
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdarg.h>
#include <signal.h>
#include <pruss_intc_mapping.h>
#include <prussdrv.h>
#include <time.h>
#include <sys/stat.h>
#include <sys/file.h>
#include <unistd.h>


// DEFINES

#define BUFFER_SIZE           8192                  // must be a multiple of 128
#define SAMPLING_RATE_HIGH    10000000              // must match the sampling rate of the PRU
#define SAMPLING_RATE_MEDIUM  1000000               // alternative, lower sampling rate
#define SAMPLING_RATE_LOW     100000                // alternative, lowest sampling rate
#define CYCLE_COUNTER_RES     6250000               // cycle counter resolution
#define MAX_TIME_SCALING_DEV  0.001                 // max deviation for time scaling (1 +/- x)
#define MAX_TIME_SCALE_CHANGE 0.000002              // max rate of change for the time scaling factor between two sync points (PPS pulses)
#define MAX_PRU_DELAY         10000000              // max delay for the PRU startup / stop handshake (in us)
#define PRU1_FIRMWARE         "/lib/firmware/fl_pru1_logic.bin"       // must be a binary file
#define PRU1_FIRMWARE_CCOUNT  "/lib/firmware/fl_pru1_logic_cc.bin"    // must be a binary file
#define PRU1_FIRMWARE_MEDRATE "/lib/firmware/fl_pru1_logic_1M.bin"    // must be a binary file
#define PRU1_FIRMWARE_LOWRATE "/lib/firmware/fl_pru1_logic_100k.bin"  // must be a binary file
#define PRU0_PRU1_FIRMWARE    "/lib/firmware/fl_pru1_logic_sp.bin"    // scratchpad version, utilizes both PRUs
#define PID_FILE              "/tmp/fl_logic.pid"
#define DATA_FILENAME_PREFIX  "tracing_data"
#define LOG_FILENAME          "/home/flocklab/log/fl_logic.log"
#define LOG_VERBOSITY         LOG_WARNING
#define SPRINTF_BUFFER_LENGTH 256
#define PIN_NAMES             "LED1", "LED2", "LED3", "INT1", "INT2", "SIG1", "SIG2", "nRST", "PPS"
#define PIN_NAMES_BB          "P845", "P846", "P843", "P844", "P841", "P842", "P839", "P840", "P827"
#define TG_RST_PIN            "P840"                // GPIO77
#define PPS_PIN_BITMASK       0x80

// extra options:
#define EXTRAOPT_LOG_LEVEL_DEBUG    0x00000001      // set log level to debug
#define EXTRAOPT_NO_RECONFIG_RST    0x00000002      // do not reconfigure the reset pin
#define EXTRAOPT_SIMPLE_SCALING     0x00000004      // if set, time scaling will be done based on the start and stop only instead of step-wide (only has an effect if EXTRAOPT_RELATIVE_TIME not set)
#define EXTRAOPT_SAMPLING_RATE_LOW  0x00000008      // use a low sampling rate (only has an effect if EXTRAOPT_USE_CYCLE_COUNTER and EXTRAOPT_USE_PRU0_HELPER not set)
#define EXTRAOPT_SAMPLING_RATE_MED  0x00000010      // use a medium sampling rate (only has an effect if EXTRAOPT_USE_CYCLE_COUNTER and EXTRAOPT_USE_PRU0_HELPER not set)
#define EXTRAOPT_USE_PRU_MEMORY     0x00000020      // use the PRU shared memory (12kb) instead of DDR RAM to store the samples
#define EXTRAOPT_USE_PRU0_HELPER    0x00000040      // utilize the PRU0 to transfer the samples to memory
#define EXTRAOPT_USE_CYCLE_COUNTER  0x00000080      // use the hardware cycle counter instead of delays and a loop counter (only has an effect if EXTRAOPT_USE_PRU0_HELPER not set)
#define EXTRAOPT_NO_PPS             0x00000100      // no PPS pin attached, don't wait for PPS signal to start/stop the sampling
#define EXTRAOPT_RELATIVE_TIME      0x00000200      // return results with relative timestamps only, no time scaling will be applied
#define EXTRAOPT_USE_BB_PINNAMES    0x00000400      // use BeagleBone pin names instead of FlockLab pin names (only available if option EXTRAOPT_RELATIVE_TIME is selected)
#define EXTRAOPT_PRINT_TO_STDOUT    0x00000800      // print all log messages to stdout


// PARAMETER CHECK

#if (BUFFER_SIZE & (BUFFER_SIZE - 1)) || (BUFFER_SIZE & 127 > 0)
#error "invalid BUFFER_SIZE (must be a multiple of 128)"
#endif


// MACROS

#ifndef MAX
#define MAX(x, y)     ((x) > (y) ? (x) : (y))
#endif /* MAX */


// TYPEDEFS

typedef struct {
  uint32_t buffer_addr;
  uint32_t buffer_size;
  uint32_t offset;
  uint8_t  pin_mask;
} pru1_config_t;

enum log_level {
  LOG_ERROR = 0,
  LOG_WARNING = 1,
  LOG_INFO = 2,
  LOG_DEBUG = 3,
};
typedef enum log_level log_level_t;


// GLOBALS

static const char* pin_mapping[] = { PIN_NAMES, PIN_NAMES_BB };
static uint32_t    sampling_rate = SAMPLING_RATE_HIGH;
static uint32_t    extra_options = 0;
static bool        running = true;
static bool        abort_conversion = false;


// FUNCTIONS

void print_usage(void)
{
  printf("No arguments supplied.\n"
           "\nUsage:\n"
           "\t./fl_logic [filename] ([starttime]) ([stoptime/duration]) ([pinmask]) ([offset]) ([extra options])\n"
           "\n"
           "\t1. filename           output filename\n"
           "\t2. starttime          UNIX timestamp of the sampling start in seconds. If the value is < 1000, it is treated\n"
           "\t                      as an offset, i.e. current time will be added)\n"
           "\t3. stoptime/duration  UNIX timestamp of the sampling stop in seconds. If the value is smaller than the current\n"
           "\t                      timestamp, it is treated as the sampling duration. Pass zero to sample indefinitely.\n"
           "\t4. pinmask            pins to trace, in hex (e.g. 0xff to trace all 8 pins, 0x0 to use the default mask)\n"
           "\t5. offset             time between release of the reset pin and sampling start, in seconds (default: 0)\n"
           "\t6. extra options      additional parameters encoded as single bits (32-bit hex value, see fl_logic.c for details)\n"
           "\n"
           "Note: All arguments but the first are optional. Arguments must be provided in-order and mustn't be skipped (i.e.\n"
           "      all previous arguments must be specified as well).\n");
}


void fl_log(log_level_t log_level, char const *const format, ...)
{
  static const char* levelstr[] = { "ERROR\t", "WARN\t", "INFO\t", "DEBUG\t" };

  // get arguments
  va_list args;
  va_start(args, format);

  // get current time
  time_t time_raw;
  struct tm *time_info;
  char time_str[24];

  time(&time_raw);
  time_info = gmtime(&time_raw);
  strftime(time_str, sizeof(time_str), "%F %T\t", time_info);

  if ((log_level <= LOG_VERBOSITY) || (extra_options & EXTRAOPT_LOG_LEVEL_DEBUG)) {
    // open log file
    FILE *log_fp = fopen(LOG_FILENAME, "a");
    if (log_fp == NULL) {
      printf("Error: failed to open log file %s\n", LOG_FILENAME);
    } else {
      // write time, log level, and message to log file
      fprintf(log_fp, time_str);
      fprintf(log_fp, levelstr[log_level]);
      vfprintf(log_fp, format, args);
      fprintf(log_fp, "\n");
      fclose(log_fp);
    }

    if (extra_options & EXTRAOPT_PRINT_TO_STDOUT) {
      // also print to stdout
      struct timespec ts;
      clock_gettime(CLOCK_REALTIME, &ts);
      printf("[%ld.%03ld] ", ts.tv_sec, ts.tv_nsec / 1000000);
      printf(levelstr[log_level]);
      vprintf(format, args);
      printf("\n");
      fflush(stdout);
    }
  }

  va_end(args);
}


static void sig_handler(int sig_num)
{
  // signal generated by stop function
  if (sig_num == SIGTERM) {
    fl_log(LOG_DEBUG, "abort signal received");
    running = false;
    abort_conversion = true;
  }

  // signal generated by interactive user (ctrl+C)
  if (sig_num == SIGINT) {
    if (extra_options & EXTRAOPT_PRINT_TO_STDOUT) {
      printf("\b\b");
      fl_log(LOG_DEBUG, "aborting...");
    }
    running = false;
  }
}


int register_sighandler(void)
{
  struct sigaction signal_action;
  signal_action.sa_handler = sig_handler;
  sigemptyset(&signal_action.sa_mask);
  signal_action.sa_flags = 0;
  if (sigaction(SIGTERM, &signal_action, NULL) < 0 ||
      sigaction(SIGINT, &signal_action, NULL) < 0) {
    fl_log(LOG_ERROR, "can't register signal handler");
    return 1;
  }
  return 0;
}


void wait_for_start(unsigned long starttime)
{
  struct timespec currtime;

  if (starttime == 0) {
    return;
  }
  starttime--;  // start 1s earlier

  clock_gettime(CLOCK_REALTIME, &currtime);
  uint32_t diff_sec  = (starttime - currtime.tv_sec);
  uint32_t diff_usec = (1000000 - (currtime.tv_nsec / 1000));

  if ((unsigned long)currtime.tv_sec < starttime) {
    fl_log(LOG_DEBUG, "waiting for start time... (%us, %uus)", (diff_sec - 1), diff_usec);
    sleep(diff_sec - 1);
    usleep(diff_usec + 100000);
  }
}


int config_pins(bool start)
{
  if (start) {
    int status = system("config-pin -a " TG_RST_PIN " pruout");
    if (status != 0) {
      fl_log(LOG_ERROR, "failed to reconfigure reset pin");
      return 1;
    }
  } else {
    // restore the regular config (MODE GPIO, output direction)
    system("config-pin -a " TG_RST_PIN " out");
  }
  return 0;
}


int pru1_init(uint8_t** out_buffer_addr, uint8_t pinmask, uint32_t offset)
{
  static pru1_config_t prucfg;

  // initialize and open PRU device
  prussdrv_init();
  // note: for some reason, EVTOUT_1 corresponds to event 4 (should be event 3 according to manual)
  if (prussdrv_open(PRU_EVTOUT_1) != 0) {
    fl_log(LOG_ERROR, "failed to open PRUSS driver");
    return 1;
  }
  // setup PRU interrupt mapping
  tpruss_intc_initdata pruss_intc_initdata = PRUSS_INTC_INITDATA;
  prussdrv_pruintc_init(&pruss_intc_initdata);

  if (extra_options & EXTRAOPT_NO_PPS) {
    pinmask |= PPS_PIN_BITMASK;
  }
  // prepare config
  prucfg.buffer_size = BUFFER_SIZE;
  prucfg.pin_mask    = pinmask;
  prucfg.offset      = offset;

  // get sample buffer
  if (extra_options & EXTRAOPT_USE_PRU_MEMORY) {
    // use a buffer in the PRU data memory
    prucfg.buffer_addr = 0x00010000;
    if (out_buffer_addr) {
      prussdrv_map_prumem(PRUSS0_SHARED_DATARAM, (void**)out_buffer_addr);
      // clear buffer
      memset(*out_buffer_addr, 0, BUFFER_SIZE);
    }

  } else {
    // use a buffer in the DDR RAM
    void* pru_extmem_base;
    prussdrv_map_extmem(&pru_extmem_base);
    uint32_t pru_extmem_size = (uint32_t)prussdrv_extmem_size();
    // place the buffer at the end of the mapped memory
    pru_extmem_base = (void*)((uint32_t)pru_extmem_base + pru_extmem_size - BUFFER_SIZE);
    prucfg.buffer_addr = (uint32_t)prussdrv_get_phys_addr(pru_extmem_base);

    // check max PRU buffer size
    if (BUFFER_SIZE > pru_extmem_size) {
      fl_log(LOG_ERROR, "insufficient PRU memory available");
      return 2;
    }
    fl_log(LOG_DEBUG, "%d / %d bytes allocated in mapped PRU memory (physical address 0x%x)", BUFFER_SIZE, pru_extmem_size, prucfg.buffer_addr);

    // get user space mapped PRU memory addresses
    if (out_buffer_addr) {
      *out_buffer_addr = prussdrv_get_virt_addr(prucfg.buffer_addr);
      if (!*out_buffer_addr) {
        fl_log(LOG_ERROR, "failed to get virtual address");
        return 3;
      }
      // clear buffer
      memset(*out_buffer_addr, 0, BUFFER_SIZE);
    }
  }

  // write configuration to PRU1 data memory
  prussdrv_pru_write_memory(PRUSS0_PRU1_DATARAM, 0x0, (unsigned int *)&prucfg, sizeof(prucfg));

  // PRU memory write fence
  __sync_synchronize();

  // load the PRU firmware (requires a binary file)
  // determine which sampling rate is to be used and choose the corresponding PRU firmware accordingly
  const char* pru_fw = PRU1_FIRMWARE;
  if (extra_options & EXTRAOPT_USE_PRU0_HELPER) {
    pru_fw        = PRU0_PRU1_FIRMWARE;
    sampling_rate = SAMPLING_RATE_HIGH;

  } else if (extra_options & EXTRAOPT_USE_CYCLE_COUNTER) {
    pru_fw        = PRU1_FIRMWARE_CCOUNT;
    sampling_rate = CYCLE_COUNTER_RES;

  } else if ((extra_options & EXTRAOPT_SAMPLING_RATE_LOW) && access(PRU1_FIRMWARE_LOWRATE, F_OK) != -1) {
    pru_fw        = PRU1_FIRMWARE_LOWRATE;
    sampling_rate = SAMPLING_RATE_LOW;

  } else if ((extra_options & EXTRAOPT_SAMPLING_RATE_MED) && access(PRU1_FIRMWARE_MEDRATE, F_OK) != -1) {
    pru_fw        = PRU1_FIRMWARE_MEDRATE;
    sampling_rate = SAMPLING_RATE_MEDIUM;
  }
  if (prussdrv_exec_program(PRU1, pru_fw) < 0) {
    fl_log(LOG_ERROR,"failed to start PRU (invalid or inexisting firmware file '%s')", PRU1_FIRMWARE);
    return 4;
  }
  fl_log(LOG_INFO, "PRU firmware '%s' for PRU1 loaded", pru_fw);

  if (extra_options & EXTRAOPT_USE_PRU0_HELPER) {
    /* make sure the data memory of PRU0 is empty! */
    memset(&prucfg, 0, sizeof(prucfg));
    prussdrv_pru_write_memory(PRUSS0_PRU0_DATARAM, 0x0, (unsigned int *)&prucfg, sizeof(prucfg));

    // load the PRU firmware (the same firmware as for PRU1 can be used)
    if (prussdrv_exec_program(PRU0, PRU0_PRU1_FIRMWARE) < 0) {
      fl_log(LOG_ERROR,"failed to start PRU0");
      return 5;
    }
    fl_log(LOG_INFO, "PRU firmware '%s' for PRU0 loaded", PRU0_PRU1_FIRMWARE);
  }

  return 0;
}


void pru1_deinit(void)
{
  // deinit
  prussdrv_pru_disable(PRU1);
  if (extra_options & EXTRAOPT_USE_PRU0_HELPER) {
    prussdrv_pru_disable(PRU0);
  }
  prussdrv_exit();
}


int pru1_handshake(void)
{
  // make sure event is cleared before doing the handshake
  prussdrv_pru_clear_event(PRU_EVTOUT_1, PRU1_ARM_INTERRUPT);

  // signal PRU to start by setting the status bit (R31.t31)
  prussdrv_pru_send_event(ARM_PRU1_INTERRUPT);   // event #22

  // wait for PRU event (returns 0 on timeout, -1 on error with errno)
  int res = prussdrv_pru_wait_event_timeout(PRU_EVTOUT_1, MAX_PRU_DELAY); // needs to be > 1s
  if (res < 0) {
    // error checking interrupt occurred
    fl_log(LOG_ERROR, "an error occurred while waiting for the PRU event");
    return 1;
  } else if (res == 0) {
    fl_log(LOG_ERROR, "failed to synchronize with PRU (timeout)");
    return 2;
  }

  // clear system (event #20)
  prussdrv_pru_clear_event(PRU_EVTOUT_1, PRU1_ARM_INTERRUPT);

  return 0;
}


int pru1_run(uint8_t* pru_buffer, FILE* data_file, time_t* starttime, time_t* stoptime)
{
  uint32_t readout_count = 0;
  time_t currtime = 0;

  // check arguments
  if (!pru_buffer || !data_file || !running || !starttime || !stoptime) {
    return 1;
  }

  // wait for the start timestamp
  wait_for_start(*starttime);

  // do the handshake with the PRU
  if (pru1_handshake() != 0) {
    return 2;
  }
  // adjust the start time if necessary
  currtime = time(NULL);
  if (currtime > *starttime) {
    fl_log(LOG_WARNING, "start time adjusted to %lu", currtime);
    *starttime = currtime;
  }

  // start sampling
  fl_log(LOG_INFO, "starting sampling loop...");

  // continuous sampling loop
  while (running) {
    // check whether it is time to stop
    if (*stoptime) {
      if (time(NULL) >= *stoptime) {
        break;
      }
    }
    // wait for PRU event (returns 0 on timeout, -1 on error with errno)
    int res = prussdrv_pru_wait_event_timeout(PRU_EVTOUT_1, 100000); // needs to be < ~0.5s
    if (res < 0) {
      // error checking interrupt occurred
      if (!running)
        break;
      return 3;   // only return error code if still running
    } else if (res == 0) {
      // timeout -> just continue
      continue;
    }
    // clear event
    prussdrv_pru_clear_event(PRU_EVTOUT_1, PRU1_ARM_INTERRUPT);
    // PRU memory sync before accessing data
    __sync_synchronize();

    uint8_t* curr_buffer = (uint8_t*)pru_buffer;
    if (readout_count & 1) {
      // odd numbers
      curr_buffer = (uint8_t*)&pru_buffer[BUFFER_SIZE / 2];
    }
    // write to file
    fwrite(curr_buffer, (BUFFER_SIZE / 2), 1, data_file);
    // clear buffer
    memset(curr_buffer, 0, (BUFFER_SIZE / 2));
    readout_count++;

    // check for overrun
    res = prussdrv_pru_wait_event_timeout(PRU_EVTOUT_1, 10);  // wait for 10us only
    if (res != 0) {
      fl_log(LOG_ERROR, "buffer overrun detected!");
      break;
    }
  }
  running = false;
  if (pru1_handshake() != 0) {
    return 4;
  }
  // adjust the stop time if necessary
  currtime = time(NULL) - 1;
  if (currtime > *stoptime) {
    if (*stoptime) {
      fl_log(LOG_WARNING, "stop time adjusted to %lu", currtime);
    }
    *stoptime = currtime;
  }
  __sync_synchronize();

  // copy the remaining data (add a few more bytes in case there is a buffer wrap around on the PRU)
  if (readout_count & 1) {
    fwrite(&pru_buffer[BUFFER_SIZE / 2], (BUFFER_SIZE / 2), 1, data_file);
    fwrite(pru_buffer, 32, 1, data_file);
  } else {
    fwrite(pru_buffer, (BUFFER_SIZE / 2) + 32, 1, data_file);
  }
  readout_count++;

  fl_log(LOG_DEBUG, "collected %u samples", readout_count * BUFFER_SIZE / 8);

  return 0;
}


// convert binary tracing data to a csv file (simple parsing without time scaling, returns relative timestamps only)
void parse_tracing_data_noscaling(const char* filename)
{
  char     buffer[SPRINTF_BUFFER_LENGTH];
  FILE*    data_file                = NULL;
  FILE*    csv_file                 = NULL;
  uint32_t sample                   = 0;
  uint32_t prev_sample              = 0;
  uint32_t line_cnt                 = 0;
  uint32_t sample_cnt               = 0;
  uint64_t timestamp_ticks          = 0;
  uint32_t pinnames_idx_offset      = (extra_options & EXTRAOPT_USE_BB_PINNAMES) ? 9 : 0;

  data_file = fopen(filename, "rb");
  sprintf(buffer, "%s.csv", filename);
  csv_file = fopen(buffer, "w");
  if (NULL == data_file || NULL == csv_file) {
    fl_log(LOG_ERROR, "failed to open files (%s and/or %s)", filename, csv_file);
    return;
  }
  fread(&sample, 4, 1, data_file);
  prev_sample = ~sample & 0xff;
  do {
    // data valid? -> at least the cycle counter must be > 0
    if (sample == 0) {
      break;
    }
    // update the timestamp
    timestamp_ticks += (sample >> 8);
    double monotonic_time = (double)timestamp_ticks / sampling_rate;
    // go through all pins and check whether there has been a change
    uint32_t i = 0;
    while (i < 8) {
      uint32_t bitmask = (1 << i);
      if ((prev_sample & bitmask) != (sample & bitmask)) {
        uint32_t pin_state = (sample & bitmask) > 0;
        // format: timestamp,pin,state(0/1)
        sprintf(buffer, "%.7f,%s,%u\n", monotonic_time, pin_mapping[i + pinnames_idx_offset], pin_state);
        fwrite(buffer, strlen(buffer), 1, csv_file);
        line_cnt++;
      }
      i++;
    }
    prev_sample = sample;
    sample_cnt++;
  } while (fread(&sample, 4, 1, data_file) && !abort_conversion);

  long int parsed_size = ftell(data_file) - 4;
  fseek(data_file, 0, SEEK_END);
  long int file_size = ftell(data_file);
  fclose(data_file);
  fclose(csv_file);
  fl_log(LOG_DEBUG, "%ld of %ld bytes parsed", parsed_size, file_size);
  fl_log(LOG_INFO, "tracing data parsed and stored in %s.csv (%u samples, %u lines)", filename, sample_cnt, line_cnt);
}


// convert binary tracing data to a csv file
void parse_tracing_data(const char* filename, unsigned long starttime_s, unsigned long stoptime_s)
{
  char     buffer[SPRINTF_BUFFER_LENGTH];
  FILE*    data_file                = NULL;
  FILE*    csv_file                 = NULL;
  uint32_t sample                   = 0;
  uint32_t prev_sample              = 0;
  uint32_t line_cnt                 = 0;
  uint32_t sample_cnt               = 0;
  uint64_t timestamp_ticks          = 0;
  uint64_t timestamp_start_ticks    = 0; // timestamp of start of test (nRST=0)
  uint64_t timestamp_end_ticks      = 0; // timestamp of end of sampling (nRST=1) (not equal to timestamp of stoptest!)
  long int file_size                = 0;
  long int parsed_size              = 0;
  double   corr_factor              = 0; // time correction factor
  bool     timestamp_start_obtained = false; // flag for to ensure first occurence of nRST=0 is obtained

  // open files
  data_file = fopen(filename, "rb");      // binary mode
  sprintf(buffer, "%s.csv", filename);
  csv_file = fopen(buffer, "w");          // text mode
  if (NULL == data_file || NULL == csv_file) {
    fl_log(LOG_ERROR, "failed to open files (%s and/or %s)", filename, csv_file);
    return;
  }
  // go through entire file to read timestamps of starting and ending nRST events (used for correction of timestamps)
  fread(&sample, 4, 1, data_file);
  do {
    // data valid? -> at least the cycle counter must be > 0 (first sample after end of trace)
    if (sample == 0) {
      break;
    }
    //fl_log(LOG_DEBUG, "sample: 0x%x, counter: %u", sample & 0xff, sample >> 8);
    // update the timestamp
    timestamp_ticks += (sample >> 8);
    // find first high value of nRST pin and last low value
    if ((sample & PPS_PIN_BITMASK) > 0) {
      // nRST=1
      if (!timestamp_start_obtained) {
        // only store the first occurence
        timestamp_start_ticks = timestamp_ticks;
        timestamp_start_obtained = true;
      }
    } else {
      // nRST=0
      // store last occurence
      timestamp_end_ticks = timestamp_ticks;
    }
    sample_cnt++;
  } while (fread(&sample, 4, 1, data_file) && !abort_conversion);

  fl_log(LOG_DEBUG, "sample_cnt: %lu", sample_cnt);
  fl_log(LOG_DEBUG, "timestamp_start_ticks: %llu, timestamp_end_ticks: %llu", (long long unsigned)timestamp_start_ticks, (long long unsigned)timestamp_end_ticks);
  fl_log(LOG_DEBUG, "starttime_s: %lu, stoptime_s: %lu", starttime_s, stoptime_s);
  // calculate correction factor for time scaling timestamps
  corr_factor = ( (stoptime_s - starttime_s) + 1.0 ) / MAX(0.000001, ( (double)(timestamp_end_ticks - timestamp_start_ticks)/sampling_rate ));
  fl_log(LOG_INFO, "corr_factor: %.7f", corr_factor);
  if (corr_factor < (1.0 - MAX_TIME_SCALING_DEV) || (corr_factor > (1.0 + MAX_TIME_SCALING_DEV))) {
    fl_log(LOG_ERROR, "timestamp scaling failed, correction factor %.7f is out of valid range (timestamps are returned unscaled)", corr_factor);
    corr_factor = 1.0;
  }
  // reset file pointer and variables
  parsed_size = ftell(data_file) - 4;
  fseek(data_file, 0, SEEK_END);
  file_size = ftell(data_file);
  fseek(data_file, 0, SEEK_SET);
  timestamp_ticks = 0;
  sample_cnt = 0;

  // go through the whole file again, this time parse and write the data into the csv file
  // read the first sample
  fread(&sample, 4, 1, data_file);
  prev_sample = ~sample & 0xff;
  do {
    // data valid? -> at least the cycle counter must be > 0
    if (sample == 0) {
      break;
    }
    // update the timestamp
    timestamp_ticks += (sample >> 8);
    double realtime_time = (double)starttime_s + (double)timestamp_ticks / sampling_rate * corr_factor;
    double monotonic_time = (double)timestamp_ticks / sampling_rate;
    // go through all pins and check whether there has been a change
    bool first_or_last_sample = (sample_cnt == 0) || (sample_cnt == ((uint32_t)parsed_size / 4 - 1));
    uint32_t i = 0;
    while (i < 8) {
      uint32_t bitmask = (1 << i);
      if ((prev_sample & bitmask) != (sample & bitmask)) {
        uint32_t pin_state = (sample & bitmask) > 0;
        // format: timestamp,ticks,pin,state(0/1)
        if (i == 7 && !first_or_last_sample) {
          i = 8;
        }
        sprintf(buffer, "%.7f,%.7f,%s,%u\n", realtime_time, monotonic_time, pin_mapping[i], pin_state);
        fwrite(buffer, strlen(buffer), 1, csv_file);
        line_cnt++;
      }
      i++;
    }
    prev_sample = sample;
    if (sample_cnt == 0) {
      // clear the nRST bit after the first sample to avoid an issue where the first PPS pulse would not appear in the processed data
      prev_sample &= ~0x80;
    }
    sample_cnt++;
  } while (fread(&sample, 4, 1, data_file) && !abort_conversion);

  fclose(data_file);
  fclose(csv_file);
  fl_log(LOG_DEBUG, "%ld of %ld bytes parsed", parsed_size, file_size);
  fl_log(LOG_INFO, "tracing data parsed and stored in %s.csv (%u samples, %u lines)", filename, sample_cnt, line_cnt);
}


// convert binary tracing data to a csv file (does stepwise scaling)
void parse_tracing_data_stepwise(const char* filename, unsigned long starttime_s, unsigned long stoptime_s, unsigned long offset)
{
  char     buffer[SPRINTF_BUFFER_LENGTH];
  FILE*    data_file            = NULL;
  FILE*    csv_file             = NULL;
  uint32_t sample               = 0;
  uint32_t prev_sample          = 0xffffffff;
  uint32_t line_cnt             = 0;
  uint32_t sample_cnt           = 0;
  uint64_t timestamp_ticks      = 0;
  uint32_t elapsed_ticks        = 0;
  uint32_t last_sync_filepos    = 0;
  uint32_t last_sync_seconds    = starttime_s;
  uint32_t samples_to_read      = 0;
  double   prev_corr_factor     = 0.0;
  bool     wait_for_rising_edge = false;
  bool     end_of_file_found    = false;

  // open files
  data_file = fopen(filename, "rb");      // binary mode
  sprintf(buffer, "%s.csv", filename);
  csv_file = fopen(buffer, "w");          // text mode
  if (NULL == data_file || NULL == csv_file) {
    fl_log(LOG_ERROR, "failed to open files (%s and/or %s)", filename, csv_file);
    return;
  }

  // go through entire file to read timestamps of starting and ending nRST events (used for correction of timestamps)
  while (!end_of_file_found && fread(&sample, 4, 1, data_file) && !abort_conversion) {
    // data valid? -> at least the cycle counter must be > 0 (except for first sample)
    if (sample != 0) {
      elapsed_ticks += (sample >> 8);
      samples_to_read++;
    } else {
      end_of_file_found = true;
    }
    if (wait_for_rising_edge) {
      if ((sample & PPS_PIN_BITMASK) != 0 || end_of_file_found) {
        // --- rising edge found ---
        if (samples_to_read == 0) {
          fl_log(LOG_WARNING, "no samples to read!");
          break;
        }
        // calculate the time in seconds
        uint32_t sec_elapsed = (elapsed_ticks + sampling_rate / 2) / sampling_rate;
        // only continue if the elapsed time is at least one second
        uint32_t sec_now = last_sync_seconds + sec_elapsed;
        // skip the first rising edge (may be shifter slightly due to the offset applied by the PRU)
        if (starttime_s + offset >= sec_now) {
          wait_for_rising_edge = false;
          continue;
        }
        // calculate the correction factor
        double div         = ((double)elapsed_ticks / sampling_rate);
        double corr_factor = 1.0;
        if (div > 0) {
          corr_factor = ((double)sec_elapsed / div);
        }
        // print info
        fl_log(LOG_DEBUG, "correction factor from %u to %u is %.7f", last_sync_seconds, sec_now, corr_factor);
        if (corr_factor < (1.0 - MAX_TIME_SCALING_DEV) || (corr_factor > (1.0 + MAX_TIME_SCALING_DEV))) {
          fl_log(LOG_ERROR, "timestamp scaling failed, correction factor %.7f is out of valid range (timestamps are returned unscaled)", corr_factor);
          corr_factor = 1.0;
        }
        // check for deviations in the correction factor
        double corr_factor_change = corr_factor - prev_corr_factor;
        if (prev_corr_factor > 0.0 && (corr_factor_change > MAX_TIME_SCALE_CHANGE || corr_factor_change < -MAX_TIME_SCALE_CHANGE)) {
          fl_log(LOG_WARNING, "correction factor changed from %.7f to %.7f between %u and %u (lost samples?)", prev_corr_factor, corr_factor, last_sync_seconds, sec_now);
        }
        prev_corr_factor = corr_factor;
        // go back in the file to the last sync point and read all samples again
        fseek(data_file, last_sync_filepos, SEEK_SET);
        elapsed_ticks = 0;
        // first loop iteration?
        if (prev_sample == 0xffffffff) {
          prev_sample = ~sample & 0xff;
        }
        while (samples_to_read && fread(&sample, 4, 1, data_file) && !abort_conversion) {
          // update the timestamp
          elapsed_ticks   += (sample >> 8);     // ticks since last sync point
          timestamp_ticks += (sample >> 8);     // total ticks since test start
          double realtime_time  = (double)last_sync_seconds + (double)elapsed_ticks / sampling_rate * corr_factor;
          double monotonic_time = (double)timestamp_ticks / sampling_rate;
          // go through all pins and check whether there has been a change
          sample = sample & 0xff;               // remove upper bits (timestamp)
          uint32_t diff = sample ^ prev_sample; // get changed pins
          uint32_t idx = 0;
          bool     first_or_last_sample = (sample_cnt == 0) || (end_of_file_found && samples_to_read == 1);
          while (diff) {
            if (diff & 1) {
              uint32_t pin_state = (sample >> idx) & 1;
              if (idx == 7 && !first_or_last_sample) {
                idx++;
              }
              // format: timestamp,ticks,pin,state(0/1)
              sprintf(buffer, "%.7f,%.7f,%s,%u\n", realtime_time, monotonic_time, pin_mapping[idx], pin_state);
              fwrite(buffer, strlen(buffer), 1, csv_file);
              line_cnt++;   // # lines written
            }
            idx++;
            diff >>= 1;
          }
          prev_sample = sample;
          if (sample_cnt == 0) {
            // clear the nRST bit after the first sample to avoid an issue where the first PPS pulse would not appear in the processed data
            prev_sample &= ~0x80;
          }
          sample_cnt++;         // total sample count
          samples_to_read--;
        }
        // update / reset state
        last_sync_seconds = sec_now;
        last_sync_filepos = ftell(data_file);
        samples_to_read   = 0;
        elapsed_ticks     = 0;
        wait_for_rising_edge = false;   // wait for falling edge
      }

    } else {
      // wait for falling edge
      if ((sample & PPS_PIN_BITMASK) == 0) {
        // falling edge found
        wait_for_rising_edge = true;
      }
    }
  }

  if ((stoptime_s + 1) != last_sync_seconds) {
    fl_log(LOG_WARNING, "calculated stop time (%lu) is != real stop time (%lu)", last_sync_seconds, stoptime_s + 1);
  }

  // close files
  long int parsed_size = ftell(data_file) - 4;
  fseek(data_file, 0, SEEK_END);
  long int file_size = ftell(data_file);
  fclose(data_file);
  fclose(csv_file);
  fl_log(LOG_DEBUG, "%ld of %ld bytes parsed", parsed_size, file_size);
  fl_log(LOG_INFO, "tracing data parsed and stored in %s.csv (%u samples, %u lines)", filename, sample_cnt, line_cnt);
}


// MAIN
int main(int argc, char** argv)
{
  char     filename[SPRINTF_BUFFER_LENGTH];
  FILE*    datafile  = NULL;
  uint8_t* prubuffer = NULL;
  long int starttime = 0;
  long int stoptime  = 0;
  uint8_t  pinmask   = 0x0;
  uint32_t offset    = 0;

  // --- make sure only one instance of this program is running ---
  int pidfd = open(PID_FILE, O_CREAT | O_RDWR, 0666);
  if (flock(pidfd, LOCK_EX | LOCK_NB) && (EWOULDBLOCK == errno)) {
    printf("another instance of fl_logic is running, terminating...\n");
    return -1;
  }

  // --- remove old log file ---
  remove(LOG_FILENAME);

  // --- check arguments ---
  if (argc == 1) {
    print_usage();
    return 1;
  }
  // read extra options first!
  if (argc > 6) {
    // 6th argument if given are the extra option bits
    extra_options = (uint32_t)strtol(argv[6], NULL, 0);
    fl_log(LOG_DEBUG, "using extra option 0x%x", extra_options);
  }
  if (argc > 1) {
    // 1st argument if given is the filename
    strncpy(filename, argv[1], SPRINTF_BUFFER_LENGTH);
    char* tmp = strrchr(argv[1], '/');
    if (tmp) tmp[0] = 0;
    if (mkdir(argv[1], 0777) == 0) {
      fl_log(LOG_INFO, "output directory %s created", argv[1]);
    }
  }
  if (argc > 2) {
    // 2nd argument if given is the start timestamp
    starttime = strtol(argv[2], NULL, 10);
    if (starttime < time(NULL)) {
      if (starttime < 1000) {         // allow offsets of less than 1000s
        starttime = time(NULL) + 2;   // invalid start time -> start in 2 seconds
      } else {
        fl_log(LOG_ERROR, "start time is in the past", argv[1]);
        return 1;
      }
    }
  }
  if (argc > 3) {
    // 3rd argument if given is the test duration in seconds or stop timestamp
    stoptime = strtol(argv[3], NULL, 10);
    if (stoptime > 0 && stoptime < time(NULL)) {
      // appears to be an offset rather than a UNIX timestamp
      stoptime += starttime;
    }
  }
  if (argc > 4) {
    // 4th argument if given is the pin mask
    pinmask = (uint8_t)strtol(argv[4], NULL, 0);
    fl_log(LOG_DEBUG, "using pin mask 0x%x", pinmask);
  }
  if (argc > 5) {
    // 5th argument if given is the time offset
    offset = (uint32_t)strtol(argv[5], NULL, 0);
    if (starttime + (long int)offset >= stoptime) {
      offset = 0; // invalid offset
    } else {
      fl_log(LOG_DEBUG, "using offset of %us", offset);
    }
  }

  // --- register signal handler ---
  if (register_sighandler() != 0) {
    return 1;
  }

  // --- open output file ---
  datafile = fopen(filename, "wb");
  if (NULL == datafile) {
    fl_log(LOG_ERROR, "failed to open file %s", filename);
    pru1_deinit();
    return 2;
  }

  // --- configure PRU ---
  if (pru1_init(&prubuffer, pinmask, offset) != 0) {
    fclose(datafile);
    return 3;
  }

  // --- configure used pins ---
  if (!(extra_options & EXTRAOPT_NO_RECONFIG_RST)) {
    config_pins(true);
  }

  // --- start sampling ---
  int rs = pru1_run(prubuffer, datafile, &starttime, &stoptime);
  if (rs != 0) {
    fl_log(LOG_ERROR, "pru1_run() returned with error code %d", rs);
  }

  // --- cleanup ---
  if (!(extra_options & EXTRAOPT_NO_RECONFIG_RST)) {
    config_pins(false);
  }
  pru1_deinit();
  fflush(datafile);
  fclose(datafile);
  fl_log(LOG_INFO, "samples stored in %s", filename);

  // --- parse data ---
  if (extra_options & EXTRAOPT_RELATIVE_TIME) {
    parse_tracing_data_noscaling(filename);
  } else if (extra_options & EXTRAOPT_SIMPLE_SCALING) {
    parse_tracing_data(filename, starttime, stoptime);
  } else {
    parse_tracing_data_stepwise(filename, starttime, stoptime, offset);
  }

  fl_log(LOG_DEBUG, "terminated");

  return rs;
}
