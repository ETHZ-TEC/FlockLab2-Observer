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
#include <termios.h>
#include <unistd.h>
#include <time.h>
#include <signal.h>


#define SUBTRACT_TRANSMIT_TIME      1    // subtract the estimated transfer time over uart from the receive timestamp
#define TIME_OFFSET                 100  // constant offset in us, only effective if SUBTRACT_TRANSMIT_TIME is enabled
#define RECEIVE_BUFFER_SIZE         1024


bool running = true;


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
    printf("can't register signal handler");
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
    printf("error from tcgetattr: %s\n", strerror(errno));
    return 1;
  }

  speed_t baudrate = convert_to_baudrate(speed);
  if (cfsetospeed(&tty, baudrate) != 0 ||
      cfsetispeed(&tty, baudrate) != 0) {
    return 2;
  }

  tty.c_cflag |= (CLOCAL | CREAD);    /* ignore modem controls */
  tty.c_cflag &= ~CSIZE;
  tty.c_cflag |= CS8;         /* 8-bit characters */
  tty.c_cflag &= ~PARENB;     /* no parity bit */
  tty.c_cflag &= ~CSTOPB;     /* only need 1 stop bit */
  tty.c_cflag &= ~CRTSCTS;    /* no hardware flowcontrol */

  /* see http://man7.org/linux/man-pages/man3/termios.3.html for details about the flags */
  tty.c_oflag  = 0;           /* no output processing */
  if (canonical_mode) {
    printf("using canonical mode");
    tty.c_lflag |= ICANON;    /* canonical mode */
  } else {
    tty.c_lflag &= ~ICANON;   /* clear canonical mode bit */
    cfmakeraw(&tty);
    /* note: at 1MBaud, there will be one byte every 10us (and one interrupt per byte if VMIN is set to 1) */
    tty.c_cc[VMIN]  = 64;     /* at least 64 characters */
    tty.c_cc[VTIME] = 1;      /* read timeout of 100ms */
  }
  tty.c_iflag  = 0;           /* clear input flags */
  tty.c_iflag |= IGNCR;       /* ignore carriage return */
  //tty.c_iflag |= ISTRIP;      /* strip off 8th bit (ensures character is ASCII) */
  //tty.c_iflag |= INPCK;       /* enable input paritiy checking */
  //tty.c_iflag |= IGNPAR;      /* ignore framing and parity errors */

  printf("tty config: 0x%x, 0x%x, 0x%x, 0x%x\n", tty.c_iflag, tty.c_oflag, tty.c_cflag, tty.c_lflag);

  if (tcsetattr(fd, TCSANOW, &tty) != 0) {
    printf("error from tcsetattr: %s\n", strerror(errno));
    return 3;
  }
  return 0;
}


int main(int argc, char** argv)
{
  unsigned char   rcvbuf[RECEIVE_BUFFER_SIZE];
  char            printbuf[RECEIVE_BUFFER_SIZE + 128];
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

  if (argc > 1) {
    // first parameter is the port
    portname = argv[1];
  }
  if (argc > 2) {
    // 2nd argument is the baudrate
    baudrate = strtol(argv[2], NULL, 10);
  }
  if (argc > 3) {
    // 3rd argument is the output filename
    outfilename = argv[3];
  }
  if (argc > 4) {
    // 4th argument is the start time
    starttime = strtol(argv[4], NULL, 10);
    if (starttime > 0 && starttime < 1000) {
      // treat as an offset
      starttime = time(NULL) + starttime;
    }
  }
  if (argc > 5) {
    // 5th argument is the duration
    duration = strtol(argv[5], NULL, 10);
  }

  // open the serial device
  fd = open(portname, O_RDWR | O_NOCTTY | O_SYNC);
  if (fd < 0) {
    printf("error opening %s: %s\n", portname, strerror(errno));
    return 1;
  }
  if (set_interface_attributes(fd, baudrate, baudrate <= 500000) != 0) {
    printf("failed to set attributes for device\n");
    close(fd);
    return 2;
  }
  tcflush(fd, TCIFLUSH);

  printf("connected to port %s (baudrate: %lu)\n", portname, baudrate);

  if (outfilename) {
    logfile = fopen(outfilename, "w");
    if (!logfile) {
      printf("failed to open log file %s\n", outfilename);
      close(fd);
      return 3;
    }
    printf("logging output to file %s\n", outfilename);
  }

  if (register_sighandler() != 0) {
    return 4;
  }

  // wait for start time
  if (starttime) {
    struct timespec currtime;
    clock_gettime(CLOCK_REALTIME, &currtime);
    unsigned int diff_sec  = (starttime - currtime.tv_sec);
    unsigned int diff_usec = (1000000 - (currtime.tv_nsec / 1000));
    if ((unsigned long)currtime.tv_sec < starttime) {
      printf("waiting for start time... (%u.%06uus)", (diff_sec - 1), diff_usec);
      fflush(stdout);
      sleep(diff_sec - 1);
      usleep(diff_usec);
    }
    tcflush(fd, TCIFLUSH);
  }

  // use RAW mode for high baudrates (otherwise data loss will occur)
  if (baudrate > 500000) {

    while (running && (duration == 0 || (unsigned int)time(NULL) < (starttime + duration))) {
      int len = read(fd, rcvbuf + bufofs, sizeof(rcvbuf) - 1 - bufofs);
      if (len > 0) {
        // take a timestamp
        clock_gettime(CLOCK_REALTIME, &currtime);
        currtime.tv_nsec = currtime.tv_nsec / 1000;   // convert to us
    #if SUBTRACT_TRANSMIT_TIME
        int transmit_time = (10000000 / baudrate) * len + TIME_OFFSET;   // 10 clock cycles per symbol (byte), plus const offset
        if (currtime.tv_nsec < transmit_time) {
          currtime.tv_sec--;
          currtime.tv_nsec = 1000000 - (transmit_time - currtime.tv_nsec);
        } else {
          currtime.tv_nsec -= transmit_time;
        }
    #endif /* SUBTRACT_TRANSMIT_TIME */
        if (bufofs == 0) {
          // start of a string -> store the timestamp
          prevtime = currtime;
        }
        bufofs += len;
        rcvbuf[bufofs] = 0;  // terminate the string
        do {
          // look for a newline character
          char* nlpos = strchr((char*)rcvbuf, '\n');
          if (nlpos) {
            *nlpos = 0;      // terminate the string
            nlpos++;
          } else if (bufofs < (sizeof(rcvbuf) - 1)) {
            // no newline found and buffer not yet full -> abort
            break;
          }
          if (logfile) {
            int prlen = sprintf(printbuf, "%ld.%06ld,%s\n", prevtime.tv_sec, prevtime.tv_nsec, rcvbuf);
            fwrite(printbuf, prlen, 1, logfile);
            //fflush(logfile);
          } else {
            printf("[%ld.%06ld] %s\n", prevtime.tv_sec, prevtime.tv_nsec, rcvbuf);
            fflush(stdout);
          }
          // copy the remainder of the input string to the beginning of the buffer
          if (nlpos) {
            bufofs = 0;
            while (*nlpos) {
              rcvbuf[bufofs++] = *nlpos;
              nlpos++;
            }
            prevtime = currtime;   // update the timestamp
            rcvbuf[bufofs] = 0;
          } else {
            // there is no remainder -> clear the receive buffer
            bufofs = 0;
            rcvbuf[0] = 0;
            break;
          }
        } while (1);

      } else if (len < 0) {
        printf("read error: %s\n", strerror(errno));
        break;
      }
    }

  } else {

    // CANONICAL mode

    while (running && (duration == 0 || (unsigned int)time(NULL) < (starttime + duration))) {
      //memset(rcvbuf, 0, sizeof(rcvbuf));
      int len = read(fd, rcvbuf, sizeof(rcvbuf) - 1);
      if (len > 0) {
        clock_gettime(CLOCK_REALTIME, &currtime);
        currtime.tv_nsec = currtime.tv_nsec / 1000;   // convert to us
    #if SUBTRACT_TRANSMIT_TIME
        int transmit_time = (10000000 / baudrate) * len + TIME_OFFSET;   // 10 clock cycles per symbol (byte), plus const offset
        if (currtime.tv_nsec < transmit_time) {
          currtime.tv_sec--;
          currtime.tv_nsec = 1000000 - (transmit_time - currtime.tv_nsec);
        } else {
          currtime.tv_nsec -= transmit_time;
        }
    #endif /* SUBTRACT_TRANSMIT_TIME */
        rcvbuf[len] = 0;  /* just to be sure, but should already be terminated by zero character in canonical mode */
        if (logfile) {
          int prlen = sprintf(printbuf, "%ld.%06ld,%s", currtime.tv_sec, currtime.tv_nsec, rcvbuf);
          if (printbuf[prlen - 1] != '\n') {
            printbuf[prlen++] = '\n';
            printbuf[prlen] = 0;
          }
          fwrite(printbuf, prlen, 1, logfile);
          //fflush(logfile);
        } else {
          printf("[%ld.%06ld] %s", currtime.tv_sec, currtime.tv_nsec, rcvbuf);
          fflush(stdout);
        }
      } else if (len < 0) {
        printf("read error: %s\n", strerror(errno));
        break;
      } else {  /* len == 0 */
        printf("read timeout\n");
      }
    }
  }

  if (logfile) {
    fclose(logfile);
  }
  close(fd);
  printf("\b\bterminated\n");

  return 0;
}
