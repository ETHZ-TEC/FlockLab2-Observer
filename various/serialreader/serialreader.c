/**
 * reads from a serial port and logs the data to a file
 *
 * 2020, rdaforno
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


#define SUBTRACT_TRANSMIT_TIME      1       // subtract the estimated transfer time over uart from the receive timestamp
#define TIME_OFFSET                 1000    // constant offset in us, only effective if SUBTRACT_TRANSMIT_TIME is enabled


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
    case 2000000: return B2000000;
    case 2500000: return B2500000;
    case 3000000: return B3000000;
    default:      return B115200;
  }
}

int set_interface_attributes(int fd, int speed)
{
  struct termios tty;

  if (tcgetattr(fd, &tty) < 0) {
    printf("error from tcgetattr: %s\n", strerror(errno));
    return 1;
  }

  /* canonical input processing mode (line by line) */
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
  tty.c_lflag |= ICANON;      /* canonical mode */
  tty.c_iflag  = 0;           /* clear input flags */
  tty.c_iflag |= IGNCR;       /* ignore carriages return */
  tty.c_iflag |= ISTRIP;      /* strip off 8th bit (ensures character is ASCII) */

  printf("tty config: 0x%x, 0x%x, 0x%x, 0x%x\n", tty.c_iflag, tty.c_oflag, tty.c_cflag, tty.c_lflag);

  if (tcsetattr(fd, TCSANOW, &tty) != 0) {
    printf("error from tcsetattr: %s\n", strerror(errno));
    return 3;
  }
  return 0;
}


int main(int argc, char** argv)
{
  unsigned char   rcvbuf[512];
  char            printbuf[4096];
  const char*     portname    = "/dev/ttyS5";
  const char*     outfilename = NULL;
  FILE*           logfile     = NULL;
  int             fd          = 0;
  unsigned long   baudrate    = 115200;
  struct timespec currtime;

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

  // open the serial device
  fd = open(portname, O_RDWR | O_NOCTTY | O_SYNC);
  if (fd < 0) {
    printf("error opening %s: %s\n", portname, strerror(errno));
    return 1;
  }
  if (set_interface_attributes(fd, baudrate) != 0) {
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

  while (running) {
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
      rcvbuf[len] = 0;
      if (logfile) {
        int prlen = sprintf(printbuf, "%ld.%06ld,%s", currtime.tv_sec, currtime.tv_nsec, rcvbuf);
        fwrite(printbuf, prlen, 1, logfile);
        //fflush(logfile);
      } else {
        printf("[%ld.%ld] %s", currtime.tv_sec, currtime.tv_nsec, rcvbuf);
      }
    } else if (len < 0) {
      printf("read error: %s\n", strerror(errno));
      break;
    } else {  /* len == 0 */
      printf("read timeout\n");
    }
  }

  if (logfile) {
    fclose(logfile);
  }
  close(fd);
  printf("\b\bterminated\n");

  return 0;
}
