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
 */

/*
 * initiates GPIO sampling with PRU1
 *
 * usage:
 *          ./fl_logic [filename] [starttime] [stoptime/duration] [pinmask]
 *
 * filename           output filename
 * starttime          UNIX timestamp of the sampling start
 * stoptime/duration  UNIX timestamp of the sampling stop, or sampling duration in seconds
 * pinmask            pins to trace, in hex (e.g. 0xff to trace all 8 pins)
 *
 * Note: all arguments are optional, but must be used in-order (i.e. argument starttime must always be the 2nd one, etc.)
 *
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
#include <unistd.h>


// DEFINES

#ifndef INTERACTIVE_MODE
 #define INTERACTIVE_MODE     0
#endif /* INTERACTIVE_MODE */
#define RECONFIG_TG_RST       1                     // reconfigure target reset pin such that PRU1 can control it
#if INTERACTIVE_MODE
 #define BUFFER_SIZE          8                     // in bytes (must be a power of 2, minimum is 8 bytes)
#else
 #define BUFFER_SIZE          16384
#endif
#define SAMPLING_RATE         10000000              // must match the sampling rate of the PRU
#define MAX_TIME_SCALING_DEV  0.01                  // max deviation for time scaling (1 +/- x)
#define MAX_PRU_DELAY         10000000              // max delay for the PRU startup / stop handshake (in us)
#define PRU1_FIRMWARE         "/lib/firmware/fl_pru1_logic.bin"     // must be a binary file
#define DATA_FILENAME_PREFIX  "tracing_data"
#define OUTPUT_DIR            "/home/flocklab/data/"                // with last slash
#define LOG_FILENAME          "/home/flocklab/log/fl_logic.log"
#define LOG_VERBOSITY         LOG_WARNING
#define SPRINTF_BUFFER_LENGTH 256
#define PIN_NAMES             "LED1", "LED2", "LED3", "INT1", "INT2", "SIG1", "SIG2", "nRST", "PPS"
#define TG_RST_PIN            "P840"                // GPIO77


// PARAMETER CHECK

#if (BUFFER_SIZE & (BUFFER_SIZE - 1)) || (BUFFER_SIZE < 8)
#error "invalid BUFFER_SIZE"
#endif


// MACROS

#define BYTE_TO_BIN_PATTERN "%c%c%c%c%c%c%c%c"
#define BYTE_TO_BIN(byte)   (byte & 0x80 ? '1' : '0'), \
                            (byte & 0x40 ? '1' : '0'), \
                            (byte & 0x20 ? '1' : '0'), \
                            (byte & 0x10 ? '1' : '0'), \
                            (byte & 0x08 ? '1' : '0'), \
                            (byte & 0x04 ? '1' : '0'), \
                            (byte & 0x02 ? '1' : '0'), \
                            (byte & 0x01 ? '1' : '0')


// TYPEDEFS

typedef struct {
  uint32_t buffer_addr;
  uint32_t buffer_size;
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

static const char* pin_mapping[] = { PIN_NAMES };
static bool  running = true;


// FUNCTIONS

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

  if (log_level <= LOG_VERBOSITY) {
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
  }

#if INTERACTIVE_MODE
  // also print to stdout
  //printf(levelstr[log_level]);
  vprintf(format, args);
  printf("\n");
  fflush(stdout);
#endif /* INTERACTIVE_MODE */

  va_end(args);
}


static void sig_handler(int sig_num)
{
  // signal generated by stop function
  if (sig_num == SIGTERM) {
    fl_log(LOG_DEBUG, "abort signal received");
    running = false;
  }

  // signal generated by interactive user (ctrl+C)
  if (sig_num == SIGINT) {
#if INTERACTIVE_MODE
    printf("\b\b  \naborting...\n");
#endif /* INTERACTIVE_MODE */
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
  //struct timespec currtime;
  unsigned long currtime = time(NULL);

  if (!starttime) {
    return;
  }

  fl_log(LOG_DEBUG, "waiting for start time... (%lus)", (starttime - time(NULL)));
  starttime--;

  while (currtime && (currtime < starttime) && running) {
    // alternatively, use clock_gettime(CLOCK_REALTIME, &currtime)
    currtime = time(NULL);
    usleep(100000);         // must be < ~0.5s
  }
}


int config_pins(bool start)
{
#if RECONFIG_TG_RST
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
#endif /* RECONFIG_TG_RST */
  return 0;
}


int pru1_init(uint8_t** out_buffer_addr, uint8_t pinmask)
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

  // PRU SETUP
  prucfg.buffer_size = BUFFER_SIZE;
  prucfg.pin_mask = pinmask;

  // get buffers
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

  // write configuration to PRU1 data memory
  prussdrv_pru_write_memory(PRUSS0_PRU1_DATARAM, 0x0, (unsigned int *)&prucfg, sizeof(prucfg));

  // PRU memory write fence
  __sync_synchronize();

  // load the PRU firmware (requires a binary file)
  if (prussdrv_exec_program(1, PRU1_FIRMWARE) < 0) {
    fl_log(LOG_ERROR,"failed to start PRU (invalid or inexisting firmware file '%s')", PRU1_FIRMWARE);
    return 4;
  }

  fl_log(LOG_INFO, "PRU firmware loaded");

  return 0;
}


void pru1_deinit(void)
{
  // deinit
  prussdrv_pru_disable(1);    // PRU1 only
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
    fl_log(LOG_INFO, "start time adjusted to %lu", currtime);
    *starttime = currtime;
  }

  // start sampling
  fl_log(LOG_INFO, "starting sampling loop...");

  // continuous sampling loop
  while (running) {
    // check whether it is time to stop
    if (stoptime) {
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
#if INTERACTIVE_MODE
    // display latest value
    unsigned char curr_value = *(uint8_t*)(curr_buffer + (BUFFER_SIZE / 2) - 4);
    printf("\b\b\b\b\b\b\b\b" BYTE_TO_BIN_PATTERN, BYTE_TO_BIN(curr_value));
    fflush(stdout);
#endif /* INTERACTIVE_MODE */

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
    fl_log(LOG_INFO, "stop time adjusted to %lu", currtime);
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

  fl_log(LOG_DEBUG, "collected %u samples", readout_count * BUFFER_SIZE / 8);

  return 0;
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
  prev_sample = ~sample & 0xff;
  do {
    // data valid? -> at least the cycle counter must be > 0 (first sample after end of trace)
    if (sample == 0) {
      break;
    }
    // update the timestamp
    timestamp_ticks += (sample >> 8);
    // look for changed nRST values
    if ( (prev_sample & 0x80) != (sample & 0x80) ) {
      if ((sample & 0x80) > 0) {
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
    }
    prev_sample = sample;
    sample_cnt++;
  } while (fread(&sample, 4, 1, data_file));

  fl_log(LOG_DEBUG, "sample_cnt: %lu", sample_cnt);
  fl_log(LOG_DEBUG, "timestamp_start_ticks: %llu, timestamp_end_ticks: %llu", (long long unsigned)timestamp_start_ticks, (long long unsigned)timestamp_end_ticks);
  fl_log(LOG_DEBUG, "starttime_s: %lu, stoptime_s: %lu", starttime_s, stoptime_s);
  // calculate correction factor for time scaling timestamps
  corr_factor = ( (stoptime_s - starttime_s) + 1.0 ) / ( (double)(timestamp_end_ticks - timestamp_start_ticks)/SAMPLING_RATE );
  fl_log(LOG_INFO, "corr_factor: %f", corr_factor);
  if (corr_factor < (1.0 - MAX_TIME_SCALING_DEV) || (corr_factor > (1.0 + MAX_TIME_SCALING_DEV))) {
    fl_log(LOG_ERROR, "timestamp scaling failed, correction factor %f is out of valid range (timestamps are returned unscaled)", corr_factor);
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
    double realtime_time = (double)starttime_s + (double)timestamp_ticks / SAMPLING_RATE * corr_factor;
    double monotonic_time = (double)timestamp_ticks / SAMPLING_RATE;
    // go through all pins and check whether there has been a change
    uint32_t i = 0;
    while (i < 8) {
      if ((prev_sample & (1 << i)) != (sample & (1 << i))) {
        uint32_t pin_state = (sample & (1 << i)) > 0;
        // format: timestamp,ticks,obs_id,node_id,pin,state(0/1)
        if (i == 7 && sample_cnt > 0 && sample_cnt < ((uint32_t)parsed_size / 4 - 1)) {
          i = 8;
        }
        sprintf(buffer, "%.7f,%.7f,%s,%u\r", realtime_time, monotonic_time, pin_mapping[i], pin_state);
        fwrite(buffer, strlen(buffer), 1, csv_file);
        line_cnt++;
      }
      i++;
    }
    prev_sample = sample;
    sample_cnt++;
  } while (fread(&sample, 4, 1, data_file));

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

  // --- remove old log file ---
  remove(LOG_FILENAME);

  // --- check arguments ---
  if (argc > 1) {
    // 1st argument if given is the filename
    strncpy(filename, argv[1], SPRINTF_BUFFER_LENGTH);
    char* tmp = strrchr(argv[1], '/');
    if (tmp) tmp[0] = 0;
    if (mkdir(argv[1], 0777) == 0) {
      fl_log(LOG_INFO, "output directory %s created", argv[1]);
    }
  } else {
    if (mkdir(OUTPUT_DIR, 0777) == 0) {
      fl_log(LOG_INFO, "output directory %s created", OUTPUT_DIR);
    }
    sprintf(filename, OUTPUT_DIR "%s_%lu.dat", DATA_FILENAME_PREFIX, time(NULL));
  }
  if (argc > 2) {
    // 2nd argument if given is the start timestamp
    starttime = strtol(argv[2], NULL, 10);
    if (starttime < time(NULL)) {
      starttime = time(NULL) + 2;    // invalid start time -> start in 2 seconds
    }
  }
  if (argc > 3) {
    // 3rd argument if given is the test duration in seconds or stop timestamp
    stoptime = strtol(argv[3], NULL, 10);
    if (stoptime < time(NULL)) {
      // appears to be an offset rather than a UNIX timestamp
      stoptime += starttime;
    }
  }
  if (argc > 4) {
    // 4th argument if given is the pin mask
    pinmask = (uint8_t)strtol(argv[4], NULL, 0);
    fl_log(LOG_DEBUG, "using pin mask 0x%x", pinmask);
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
  if (pru1_init(&prubuffer, pinmask) != 0) {
    fclose(datafile);
    return 3;
  }

  // --- configure used pins ---
  config_pins(true);

  // --- start sampling ---
  int rs = pru1_run(prubuffer, datafile, &starttime, &stoptime);
  if (rs != 0) {
    fl_log(LOG_ERROR, "pru1_run() returned with error code %d", rs);
  }

  // --- cleanup ---
  config_pins(false);
  pru1_deinit();
  fflush(datafile);
  fclose(datafile);
  fl_log(LOG_INFO, "samples stored in %s", filename);

  // --- parse data ---
  parse_tracing_data(filename, starttime, stoptime);

  fl_log(LOG_DEBUG, "terminated");

  return rs;
}
