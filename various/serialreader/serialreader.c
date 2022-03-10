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

/**
 * reads from a serial port and logs the data to a file
 */

#include <errno.h>
#include <fcntl.h> 
#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>
#include <string.h>
#include <stdarg.h>
#include <termios.h>
#include <unistd.h>
#include <time.h>
#include <signal.h>


#define RAW_MODE                    0
#define SUBTRACT_TRANSMIT_TIME      RAW_MODE  // subtract the estimated transfer time over uart from the receive timestamp (only makes sense in raw mode since the delays are too unpredictable in canonical mode)
#define TIME_OFFSET_NS              100000    // constant offset in us, only effective if SUBTRACT_TRANSMIT_TIME is enabled
#define START_OFFSET_MS             1000      // offset of the start time (positive value means the read loop will be entered earlier than the scheduled start time)
#define CHECK_FOR_TIME_JUMPS        1
#define RECEIVE_BUFFER_SIZE         4096
#define PRINT_BUFFER_SIZE           128
#define LOG_VERBOSITY               LOG_DEBUG
#define LOG_FILENAME                "/home/flocklab/log/serialreader.log"


enum log_level {
  LOG_ERROR = 0,
  LOG_WARNING = 1,
  LOG_INFO = 2,
  LOG_DEBUG = 3,
};
typedef enum log_level log_level_t;


bool running = true;


void fl_log(log_level_t log_level, char const *const format, ...)
{
  static const char* levelstr[] = { "ERROR\t", "WARN\t", "INFO\t", "DEBUG\t" };

  // get arguments
  va_list args;
  va_start(args, format);

  // get current time
  time_t time_raw;
  char   time_str[24];

  time(&time_raw);
  strftime(time_str, sizeof(time_str), "%F %T\t", gmtime(&time_raw));

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
      fflush(log_fp);
      fclose(log_fp);
    }
  }

  va_end(args);
}


static void sig_handler(int sig_num)
{
  if (sig_num == SIGTERM || sig_num == SIGINT) {
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
      sigaction(SIGINT, &signal_action, NULL)  < 0) {
    fl_log(LOG_ERROR, "can't register signal handler");
    return 1;
  }
  return 0;
}

int convert_to_baudrate(unsigned long speed)
{
  switch (speed) {
    case 9600:    return B9600;
    case 19200:   return B19200;
    case 38400:   return B38400;
    case 57600:   return B57600;
    case 115200:  return B115200;
    case 230400:  return B230400;
    case 460800:  return B460800;
    case 500000:  return B500000;
    case 576000:  return B576000;
    case 921600:  return B921600;
    case 1000000: return B1000000;
    case 1152000: return B1152000;
    case 1500000: return B1500000;
    case 2000000: return B2000000;
    case 2500000: return B2500000;
    case 3000000: return B3000000;
    case 3500000: return B3500000;
    case 4000000: return B4000000;
    default:      return B115200;
  }
}

int set_interface_attributes(int fd, int speed, bool canonical_mode)
{
  struct termios tty;

  if (tcgetattr(fd, &tty) < 0) {
    fl_log(LOG_ERROR, "error from tcgetattr: %s", strerror(errno));
    return 1;
  }

  speed_t baudrate = convert_to_baudrate(speed);
  if (cfsetispeed(&tty, baudrate) != 0) {     // cfsetospeed(&tty, baudrate) not needed
    return 2;
  }

  tty.c_cflag |= (CLOCAL | CREAD);    // ignore modem controls
  tty.c_cflag &= ~CSIZE;
  tty.c_cflag |= CS8;         // 8-bit characters
  tty.c_cflag &= ~PARENB;     // no parity bit
  tty.c_cflag &= ~CSTOPB;     // only need 1 stop bit
  tty.c_cflag &= ~CRTSCTS;    // no hardware flowcontrol

  // see http://man7.org/linux/man-pages/man3/termios.3.html for details about the flags
  tty.c_oflag  = 0;           // no output processing
  tty.c_lflag  = 0;           // clear local flags

  if (canonical_mode) {
    fl_log(LOG_DEBUG, "using canonical mode");
    tty.c_lflag |= ICANON;    // canonical mode
  } else {
    tty.c_lflag &= ~ICANON;   // clear canonical mode bit
    cfmakeraw(&tty);
    memset(tty.c_cc, 0, sizeof(tty.c_cc));
    // note: at 1MBaud, there will be one byte every 10us (and one interrupt per byte if VMIN is set to 1)
    tty.c_cc[VMIN]  = 32;     // at least 32 characters
    tty.c_cc[VTIME] = 1;      // read timeout of 100ms
  }
  tty.c_iflag  = 0;           // clear input flags
  tty.c_iflag |= IGNCR;       // ignore carriage return
  tty.c_iflag |= IGNBRK;      // ignore break
  tty.c_iflag |= ISTRIP;      // strip off 8th bit (ensures character is ASCII)
  //tty.c_iflag |= IGNPAR;    // ignore framing and parity errors

  fl_log(LOG_DEBUG, "tty config: 0x%x, 0x%x, 0x%x, 0x%x", tty.c_iflag, tty.c_oflag, tty.c_cflag, tty.c_lflag);

  if (tcsetattr(fd, TCSAFLUSH, &tty) != 0) {
    fl_log(LOG_ERROR, "error from tcsetattr: %s", strerror(errno));
    return 3;
  }
  return 0;
}


// returns the transmission time over the serial port in ns
unsigned int get_tx_time_ns(unsigned long baudrate, unsigned long num_chars)
{
  // 10 clock cycles per symbol
  return num_chars * 10 * (1e9 / baudrate);
}


int main(int argc, char** argv)
{
  unsigned char   rcvbuf[RECEIVE_BUFFER_SIZE];
  char            printbuf[PRINT_BUFFER_SIZE];
  const char*     portname    = "/dev/ttyS5";
  const char*     outfilename = NULL;
  FILE*           logfile     = NULL;
  int             fd          = 0;
  unsigned long   baudrate    = 115200;
  unsigned int    starttime   = 0;
  unsigned int    duration    = 0;
  struct timespec currtime;
  struct timespec prevtime;
  unsigned long   bufofs      = 0;

  // parse arguments

  if (argc < 3) {
    // print usage
    printf("usage:   serialreader [port] [baudrate] ([output_file] [start_time] [duration])\n");
    return 1;
  }

  // 1st parameter is the port (mandatory)
  portname = argv[1];
  // 2nd argument is the baudrate (mandatory)
  baudrate = strtol(argv[2], NULL, 10);

  if (argc > 3) {
    // 3rd argument is the output filename (optional)
    outfilename = argv[3];
  }
  if (argc > 4) {
    // 4th argument is the start time (optional)
    starttime = strtol(argv[4], NULL, 10);
    if (starttime > 0 && starttime < 1000) {
      // treat as an offset
      starttime = time(NULL) + starttime;
    }
  }
  if (argc > 5) {
    // 5th argument is the duration (optional)
    duration = strtol(argv[5], NULL, 10);
    fl_log(LOG_INFO, "logging duration: %us", duration);
  }

  // open the serial device
  fd = open(portname, O_RDONLY | O_NOCTTY);
  if (fd < 0) {
    fl_log(LOG_ERROR, "error opening %s: %s", portname, strerror(errno));
    return 1;
  }
  if (set_interface_attributes(fd, baudrate, !RAW_MODE) != 0) {
    fl_log(LOG_ERROR, "failed to set attributes for device");
    close(fd);
    return 2;
  }

  fl_log(LOG_INFO, "connected to port %s (baudrate: %lu)", portname, baudrate);

  if (outfilename) {
    logfile = fopen(outfilename, "w");
    if (!logfile) {
      fl_log(LOG_ERROR, "failed to open log file %s", outfilename);
      close(fd);
      return 3;
    }
    fl_log(LOG_INFO, "logging output to file %s", outfilename);
  }

  if (register_sighandler() != 0) {
    return 4;
  }

  // wait for start time
  if (starttime) {
    struct timespec currtime;
    clock_gettime(CLOCK_REALTIME, &currtime);
    // append the start offset
    currtime.tv_sec  += (START_OFFSET_MS / 1000);
    currtime.tv_nsec += (START_OFFSET_MS % 1000) * 1000000;
    if (currtime.tv_nsec >= 1e9) {
      currtime.tv_sec++;
      currtime.tv_nsec -= 1e9;
    }
    int diff_sec  = (starttime - currtime.tv_sec);
    int diff_usec = (1e6 - (currtime.tv_nsec / 1000));
    if (diff_sec > 0) {
      fl_log(LOG_DEBUG, "waiting for start time... (%u.%06us)", (diff_sec - 1), diff_usec);
      fflush(stdout);
      sleep(diff_sec - 1);
      usleep(diff_usec);
    }
  }
  // flush input queue
  tcflush(fd, TCIOFLUSH);
  usleep(10000);

  if (RAW_MODE) {

    while (running && (duration == 0 || (unsigned int)time(NULL) < (starttime + duration))) {

      int len = read(fd, rcvbuf + bufofs, sizeof(rcvbuf) - 1 - bufofs);
      if (len > 0) {
        // take a timestamp
        clock_gettime(CLOCK_REALTIME, &currtime);
    #if SUBTRACT_TRANSMIT_TIME
        int transmit_time_ns = get_tx_time_ns(baudrate, len) + TIME_OFFSET_NS;
        if (currtime.tv_nsec < transmit_time_ns) {
          currtime.tv_sec--;
          currtime.tv_nsec = 1e9 - (transmit_time_ns - currtime.tv_nsec);
        } else {
          currtime.tv_nsec -= transmit_time_ns;
        }
    #endif
        // start time after test end?
        if (duration > 0 && currtime.tv_sec >= (int)(starttime + duration)) {
          break;
        }
        if (bufofs == 0) {
          // start of a line -> store the timestamp
          prevtime = currtime;
        }
        bufofs += len;
        do {
          // look for a newline character
          unsigned int remaining = 0;
          int newlinepos         = -1;
          for (unsigned int i = 0; i < bufofs; i++) {
            if (rcvbuf[i] == '\n') {
              newlinepos = i;
              break;
            }
          }
          if (newlinepos >= 0) {
            // newline found
            newlinepos++;
            len       = newlinepos;
            remaining = bufofs - len;
          } else if (bufofs >= (sizeof(rcvbuf) - 1)) {
            // no newline, but buffer is full -> append newline
            len = sizeof(rcvbuf);
            rcvbuf[len - 1] = '\n';
          } else {
            // no newline found and buffer not yet full -> abort
            break;
          }
          // write to file
          if (logfile) {
            // only write to file if the timestamp is after the test start
            if (((unsigned int)prevtime.tv_sec + 1) >= starttime) {
              int prlen = snprintf(printbuf, PRINT_BUFFER_SIZE, "%ld.%06ld,", prevtime.tv_sec, prevtime.tv_nsec / 1000);
              if (prlen) {
                fwrite(printbuf, prlen, 1, logfile);
                fwrite(rcvbuf, len, 1, logfile);
              }
            }
          // write to stdout
          } else {
            rcvbuf[len - 1] = 0;  // make sure the line is a valid string (zero terminated)
            printf("[%ld.%06ld] %s\n", prevtime.tv_sec, prevtime.tv_nsec / 1000, rcvbuf);
            fflush(stdout);
          }
          // copy the remainder of the input data to the beginning of the buffer
          if (remaining) {
    #if SUBTRACT_TRANSMIT_TIME
            // increment the timestamp by the transmit time
            currtime.tv_nsec += get_tx_time_ns(baudrate, len);
            if (currtime.tv_nsec >= 1e9) {
              currtime.tv_sec++;
              currtime.tv_nsec -= 1e9;
            }
    #endif
            memcpy(rcvbuf, &rcvbuf[bufofs - remaining], remaining);
            bufofs = remaining;
            prevtime = currtime;   // update the timestamp
          } else {
            // there is no remainder
            bufofs = 0;
            break;
          }
        } while (1);

      } else if (len < 0) {
        if (logfile) {
          fflush(logfile);
        }
        if (errno == EINTR) {
          fl_log(LOG_DEBUG, "sigterm received");
        } else {
          fl_log(LOG_WARNING, "read error: %s", strerror(errno));
        }
        break;
      }
      // else: read timeout
    }

  } else {

    // CANONICAL mode

    while (running && (duration == 0 || (unsigned int)time(NULL) < (starttime + duration))) {

      int len = read(fd, rcvbuf, sizeof(rcvbuf) - 1);
      if (len > 0) {
        clock_gettime(CLOCK_REALTIME, &currtime);
    #if SUBTRACT_TRANSMIT_TIME
        int transmit_time_ns = get_tx_time_ns(baudrate, len) + TIME_OFFSET_NS;
        if (currtime.tv_nsec < transmit_time_ns) {
          currtime.tv_sec--;
          currtime.tv_nsec = 1e9 - (transmit_time_ns - currtime.tv_nsec);
        } else {
          currtime.tv_nsec -= transmit_time_ns;
        }
    #endif
    #if CHECK_FOR_TIME_JUMPS
        // detect jumps in time
        if ((prevtime.tv_sec >= currtime.tv_sec) && (prevtime.tv_nsec > currtime.tv_nsec)) {
          fl_log(LOG_WARNING, "timestamp jump detected (current: %ld.%09ld, previous: %ld.%09ld)", currtime.tv_sec, currtime.tv_nsec, prevtime.tv_sec, prevtime.tv_nsec);
          currtime          = prevtime;
          currtime.tv_nsec += 1000; // add 1us to have a strictly monotonic timestamp in the log
          if (currtime.tv_nsec >= 1e9) {
            currtime.tv_sec++;
            currtime.tv_nsec -= 1e9;
          }
        }
    #endif
        // start time after test end?
        if ((duration > 0) && (currtime.tv_sec >= (int)(starttime + duration))) {
          break;
        }
        // make sure a newline character is included at the end
        if (rcvbuf[len - 1] != '\n') {
          rcvbuf[len++] = '\n';
        }
        // write to file
        if (logfile) {
          // only write to file if the timestamp is after the test start (+1 slack to account for timing errors)
          if (((unsigned int)currtime.tv_sec + 1) >= starttime) {
            int prlen = snprintf(printbuf, PRINT_BUFFER_SIZE, "%ld.%06ld,", currtime.tv_sec, currtime.tv_nsec / 1000);
            if (prlen) {
              fwrite(printbuf, prlen, 1, logfile);
              fwrite(rcvbuf, len, 1, logfile);
            }
          }
        // write to stdout
        } else {
          rcvbuf[len - 1] = 0;    // make sure the line is a valid string (zero terminated)
          printf("[%ld.%06ld] %s\n", currtime.tv_sec, currtime.tv_nsec / 1000, rcvbuf);
          fflush(stdout);
        }

      } else if (len < 0) {
        if (logfile) {
          fflush(logfile);
        }
        if (errno == EINTR) {
          fl_log(LOG_DEBUG, "sigterm received");
        } else {
          fl_log(LOG_WARNING, "read error: %s", strerror(errno));
        }
        break;

      } else {  // len == 0
        fl_log(LOG_WARNING, "read timeout");
      }
      prevtime = currtime;
    }
  }

  if (logfile) {
    fclose(logfile);
  }
  close(fd);
  fl_log(LOG_DEBUG, "terminated");

  return 0;
}
