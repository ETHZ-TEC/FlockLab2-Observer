/**
 * Copyright (c) 2020 - 2022, ETH Zurich, Computer Engineering Group
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

/**
 * FlockLab 2 actuation kernel module for the BeagleBone Green (tested on kernel 4.14).
 */

// --- INCLUDES ---

#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/hrtimer.h>
#include <linux/ktime.h>
#include <linux/fs.h>
#include <linux/uaccess.h>
#include <linux/device.h>
#include <linux/semaphore.h>
#include <linux/delay.h>
#include <asm/io.h>


// --- CONFIG ---

#define MODULE_NAME         "FlockLab act: "    // prefix for log printing
#define DEVICE_NAME         "flocklab_act"      // name of the device in '/dev/'
#define TIMER_MODE          HRTIMER_MODE_ABS    // absolute or relative
#define TIMER_ID            CLOCK_REALTIME      // realtime or monotonic
#define TIMER_OFS_US        -90                 // timer offset compensation in microseconds, applies to the start marker only
#define MIN_PERIOD          10                  // minimum time between two consecutive actuation events, in microseconds
#define DEVICE_BUFFER_SIZE  65536               // max. buffer size for character device
#define EVENT_QUEUE_SIZE    8192                // limits the max. number of actuations that can be registered at a time; must be a power of 2
#define FLOCKLAB_SIG1_PIN   89                  // P8.30 -> must be configured as GPIO output
#define FLOCKLAB_SIG2_PIN   88                  // P8.28 -> must be configured as GPIO output
#define FLOCKLAB_nRST_PIN   77                  // P8.40 -> must be configured as GPIO output
#define FLOCKLAB_PPS_PIN    66                  // P8.07 -> must be configured as GPIO output
#define FLOCKLAB_ACTnEN_PIN 65                  //
#define PPS_MAX_WAITTIME_NS 220000              // max. time to wait before actuating the PPS pin, in ns (set to 0 to disable this feature)
#define PPS_SHIFT_NS        8000                // shift the PPS generation by x ns (positiv values will lead to an earlier actuation)
#define DEBUG               0


// --- MACROS / DEFINES ---

#define GPIO0_START_ADDR    0x44E07000          // see am335x RM p.180
#define GPIO1_START_ADDR    0x4804C000
#define GPIO2_START_ADDR    0x481AC000
#define GPIO3_START_ADDR    0x481AE000
#define GPIO_MEM_SIZE       0x2000
#define GPIO_DO_OFS         0x13C               // data output register
#define GPIO_CLR_OFS        0x190               // set data output low
#define GPIO_SET_OFS        0x194               // set data output high
#define PIN_TO_BITMASK(p)   (1 << ((p) & 31))
#define INVALID_OFS         0xffffffff

#if FLOCKLAB_SIG1_PIN < 32
  #define GPIO_ADDR         GPIO0_START_ADDR
#elif FLOCKLAB_SIG1_PIN < 64
  #define GPIO_ADDR         GPIO1_START_ADDR
#elif FLOCKLAB_SIG1_PIN < 96
  #define GPIO_ADDR         GPIO2_START_ADDR
#else
  #define GPIO_ADDR         GPIO3_START_ADDR
#endif

#define LOG(...)            printk(MODULE_NAME __VA_ARGS__)
#if DEBUG
  #define LOG_DEBUG(...)    printk(MODULE_NAME __VA_ARGS__)
#else
  #define LOG_DEBUG(...)
#endif /* DEBUG */

// error checking
#if (FLOCKLAB_SIG1_PIN / 32 != FLOCKLAB_SIG2_PIN / 32) || (FLOCKLAB_SIG1_PIN / 32 != FLOCKLAB_nRST_PIN / 32) || (FLOCKLAB_SIG1_PIN / 32 != FLOCKLAB_PPS_PIN / 32)
  #error "SIG1, SIG2 and nRST must be on the same GPIO port"
#endif
#if (EVENT_QUEUE_SIZE & (EVENT_QUEUE_SIZE - 1))
  #error "EVENT_QUEUE_SIZE must be a power of 2"
#endif


// --- TYPEDEFS ---

typedef struct {
  uint32_t ofs;     // offset relative to the start time
  uint8_t  pin;     // pin number
  uint8_t  lvl;     // logic level (0 or 1)
} act_event_t;



// --- GLOBAL VARIABLES ---

static struct hrtimer     timer;                          // the timer handle
static struct semaphore   queue_sem;                      // protects access to the event queue
static act_event_t        event_queue[EVENT_QUEUE_SIZE];  // array to hold all events
static unsigned int       read_idx  = 0;                  // read index for the event queue
static unsigned int       write_idx = 0;                  // write index for the event queue
static unsigned int       skipped_events = 0;
static const act_event_t* next_evt = NULL;
static bool               timer_running = false;

static struct class* timer_dev_class;
static int           timer_dev_major;
static char          timer_dev_data_in[DEVICE_BUFFER_SIZE];
static char          timer_dev_data_out[32];              // buffer to hold the last response to a command

static volatile unsigned int* gpio_set_addr = NULL;
static volatile unsigned int* gpio_clr_addr = NULL;


// --- FUNCTIONS ---

static inline void gpio_set(uint32_t pin)
{
  if (gpio_set_addr && pin) {
    *gpio_set_addr = PIN_TO_BITMASK(pin);
  }
}

static inline void gpio_clr(uint32_t pin)
{
  if (gpio_clr_addr && pin) {
    *gpio_clr_addr = PIN_TO_BITMASK(pin);
  }
}

static inline void gpio_toggle(uint32_t pin)
{
  // note: reading the GPIO_SETDATAOUT or CLEARDATAOUT returns the value of the data output register (GPIO_DATAOUT)
  uint32_t pinmask;
  if (gpio_set_addr && pin) {
    pinmask = PIN_TO_BITMASK(pin);
    if (*gpio_set_addr & pinmask) {
      *gpio_clr_addr = pinmask;
    } else {
      *gpio_set_addr = pinmask;
    }
  }
}

static void gpio_update(uint32_t pin, uint32_t level)
{
  if (level == 1) {
    gpio_set(pin);
  } else if (level == 0) {
    gpio_clr(pin);
  } else if (level == 2) {
    gpio_toggle(pin);
  }
}

static void map_gpio(void)
{
  volatile void* gpio_addr_mapped;
  gpio_addr_mapped = ioremap(GPIO_ADDR, GPIO_MEM_SIZE);
  if (gpio_addr_mapped == 0) {
    LOG("ERROR unable to map GPIO\n");
    return;
  }
  gpio_set_addr = gpio_addr_mapped + GPIO_SET_OFS;
  gpio_clr_addr = gpio_addr_mapped + GPIO_CLR_OFS;
  LOG_DEBUG("GPIO peripheral address mapped to 0x%p\n", gpio_addr_mapped);
}

// ------------------------------------------

static inline uint32_t queue_size(void)
{
  return (read_idx > write_idx) ? (EVENT_QUEUE_SIZE - read_idx + write_idx) : (write_idx - read_idx);
}

static inline bool queue_empty(void)
{
  return (write_idx == read_idx);
}

static inline bool queue_full(void)
{
  return ((write_idx + 1) & (EVENT_QUEUE_SIZE - 1)) == read_idx;
}

// adds a GPIO actuation event to the queue
static bool add_event(uint32_t ofs_us, uint32_t pin, uint32_t level)
{
  // timer must be stopped
  if (timer_running) {
    LOG("WARNING cannot add events while timer is running");
    return false;
  }
  // check if there is still space in the queue
  if (queue_full()) {
    LOG("ERROR queue is full, event dropped\n");
    return false;
  }
  // offset must be at least MIN_PERIOD (or zero)
  if (ofs_us > 0 && ofs_us < MIN_PERIOD) {
    // set offset to 0, i.e. execute it together with the previous event
    ofs_us = 0;
    LOG("WARNING offset too small\n");
  }
  // acquire queue access
  if (down_interruptible(&queue_sem) == 0) {
    event_queue[write_idx].ofs = ofs_us;
    event_queue[write_idx].pin = pin;
    event_queue[write_idx].lvl = level;
    write_idx = (write_idx + 1) & (EVENT_QUEUE_SIZE - 1);
    // release semaphore
    up(&queue_sem);
    LOG_DEBUG("event added (%u, %u, %u), new queue size is %u\n", ofs_us, pin, level, queue_size());

  } else {
    LOG("ERROR failed to get semaphore\n");
    return false;
  }
  return true;
}

static inline const act_event_t* get_next_event(void)
{
  const act_event_t* ev = NULL;
  if (!queue_empty()) {
    ev = &event_queue[read_idx];
    read_idx++;
    if (read_idx >= EVENT_QUEUE_SIZE) {
      read_idx = 0;
    }
  }
  return ev;
}

static inline uint32_t get_next_event_offset(void)
{
  if (queue_empty()) {
    return INVALID_OFS;
  }
  return event_queue[read_idx].ofs;
}

static void clear_queue(void)
{
  if (down_interruptible(&queue_sem) == 0) {
    read_idx = write_idx = 0;
    memset(event_queue, 0, sizeof(event_queue));
    up(&queue_sem);
  } else {
    LOG("ERROR failed to clear queue\n");
  }
}

// ------------------------------------------

static void timer_reset(struct hrtimer* tim, uint32_t period_us)
{
  hrtimer_forward(tim, tim->_softexpires, (uint64_t)(period_us) * 1000);
}

// timer callback function
static enum hrtimer_restart timer_expired(struct hrtimer* tim)
{
  uint32_t extra_ofs_us = 0;

  do {
    // note: on the first call of this function, next_evt will be NULL
    if (next_evt) {

#if PPS_MAX_WAITTIME_NS

      // is it the PPS pin? (rising edge only)
      if ((next_evt->pin == FLOCKLAB_PPS_PIN) && (next_evt->lvl > 0)) {
        struct   timespec ts_now;
        uint32_t delta_ns;
        bool     pps_lvl = next_evt->lvl;
        // get current UNIX timestamp in nanoseconds
        ktime_get_real_ts(&ts_now);    // same as getnstimeofday()
        // calculate time delta to the next full second
        delta_ns = 1000000000 - (uint32_t)ts_now.tv_nsec - PPS_SHIFT_NS;
        if (delta_ns < PPS_MAX_WAITTIME_NS) {
          // check if the next event is within this time frame
          while (1) {
            uint64_t next_ofs = get_next_event_offset();
            if (next_ofs == INVALID_OFS) {  // no more events pending
              break;
            }
            next_ofs *= 1000;               // convert from us to ns
            if (next_ofs >= delta_ns) {     // too far in the future
              break;
            }
            next_evt = get_next_event();
            ndelay(next_ofs);               // busy wait
            // actuate pin
            gpio_update(next_evt->pin, next_evt->lvl);
            // update delta / offset
            delta_ns     -= next_ofs;
            extra_ofs_us += next_evt->ofs;
          }
          // busy wait for the remaining time
          ndelay(delta_ns);
          gpio_update(FLOCKLAB_PPS_PIN, pps_lvl);
        } else {
          // else: too late or too early -> skip this event
          skipped_events++;
        }
      } else {
        // regular pin or falling edge of PPS
        gpio_update(next_evt->pin, next_evt->lvl);
      }
#else /* PPS_MAX_WAITTIME_NS */

      gpio_update(next_evt->pin, next_evt->lvl);

#endif /* PPS_MAX_WAITTIME_NS */

      LOG_DEBUG("GPIO level set\n");
    }
    // check if there are more actuation events that should happen now
    next_evt = get_next_event();
  } while (next_evt && next_evt->ofs == 0);

  // if there are more events in the queue, then restart the timer
  if (next_evt) {
    timer_reset(tim, next_evt->ofs + extra_ofs_us);
    return HRTIMER_RESTART;

  } else {
    LOG("timer stopped (%u events skipped)\n", skipped_events);
    skipped_events = 0;
    timer_running  = false;
    return HRTIMER_NORESTART;
  }
}

// set one shot timer
static void timer_set(ktime_t t_exp)
{
  // make sure the timer is not running anymore
  hrtimer_cancel(&timer);
  timer.function = timer_expired;
  timer_running  = true;
  skipped_events = 0;
  next_evt       = NULL;
  hrtimer_start(&timer, t_exp, TIMER_MODE);
}

// ------------------------------------------

static uint32_t parse_uint32(const char* str)
{
  uint32_t res = 0;
  if (!str) return 0;
  // skip whitespaces at the beginning
  while (*str && *str == ' ') str++;
  while (*str) {
    if (*str < '0' || *str > '9') {
      break;
    }
    res = res * 10 + (*str - '0');
    str++;
  }
  return res;
}

static void parse_argument(const char* arg)
{
  static uint32_t errcnt = 0;
  struct timespec now;
  uint32_t val;

  if (!arg) return;

  while (*arg) {

    if (*arg == 'S' || *arg == 's') {
      // start command
      if (queue_size() == 0) {
        LOG("WARNING start command ignored, queue is empty\n");
        errcnt++;
      } else {
        LOG_DEBUG("start command received\n");
        // get the start time (UNIX timestamp, in seconds)
        val = parse_uint32(arg + 1);
        // is start time in the future?
        getnstimeofday(&now);
        if (val > 0) {
          if (val < 1000) {
            // treat as relative start time
            val += now.tv_sec;
          }
          if (val > now.tv_sec) {
            ktime_t t_start_ns;
            t_start_ns = ktime_set(val, 0) + (TIMER_OFS_US * 1000);
            timer_set(t_start_ns);
            LOG("start time set to %u, queue size is %u\n", val, queue_size());
          }
        } else {
          LOG("WARNING start time must be in the future\n");
        }
      }
    } else if (*arg == 'C' || *arg == 'c') {
      // cancel / clear command
      LOG("cancel command received\n");
      hrtimer_cancel(&timer);
      clear_queue();
      // set SIG pins back to default state
      gpio_clr(FLOCKLAB_SIG1_PIN);
      gpio_clr(FLOCKLAB_SIG2_PIN);
      timer_running  = false;
      skipped_events = 0;
      errcnt         = 0;

    } else if (*arg == 'L' || *arg == 'l') {
      // set pin low
      // an offset in microseconds is expected (max offset: ~4200s)
      val = parse_uint32(arg + 1);
      if (!add_event((uint32_t)val, (*arg == 'L') ? FLOCKLAB_SIG1_PIN : FLOCKLAB_SIG2_PIN, 0)) {
        errcnt++;
      }
    } else if (*arg == 'H' || *arg == 'h') {
      // set pin high
      // an offset in microseconds is expected (max offset: ~4200s)
      val = parse_uint32(arg + 1);
      if (!add_event((uint32_t)val, (*arg == 'H') ? FLOCKLAB_SIG1_PIN : FLOCKLAB_SIG2_PIN, 1)) {
        errcnt++;
      }
    } else if (*arg == 'T' || *arg == 't') {
      // toggle pin
      // an offset in microseconds is expected (max offset: ~4200s)
      val = parse_uint32(arg + 1);
      if (!add_event((uint32_t)val, (*arg == 'T') ? FLOCKLAB_SIG1_PIN : FLOCKLAB_SIG2_PIN, 2)) {
        errcnt++;
      }
    } else if (*arg == 'R' || *arg == 'r') {
      // reset pin actuation
      // an offset in microseconds is expected (max offset: ~4200s)
      val = parse_uint32(arg + 1);
      if (!add_event((uint32_t)val, FLOCKLAB_nRST_PIN, (*arg == 'R'))) {
        errcnt++;
      }
    } else if (*arg == 'P' || *arg == 'p') {
      // PPS pin actuation
      // an offset in microseconds is expected (max offset: ~4200s)
      val = parse_uint32(arg + 1);
      if (!add_event((uint32_t)val, FLOCKLAB_PPS_PIN, (*arg == 'P'))) {
        errcnt++;
      }
    } else if (*arg == 'A' || *arg == 'a') {
      // actuation enable pin
      // an offset in microseconds is expected (max offset: ~4200s)
      val = parse_uint32(arg + 1);
      if (!add_event((uint32_t)val, FLOCKLAB_ACTnEN_PIN, (*arg == 'A'))) {
        errcnt++;
      }
    }
    arg++;
  }

  // write response into output buffer
  if (errcnt) {
    snprintf(timer_dev_data_out, sizeof(timer_dev_data_out), "ERROR count: %u", errcnt);
  } else {
    snprintf(timer_dev_data_out, sizeof(timer_dev_data_out), "OK %u", queue_size());
  }
}

// ------------------------------------------

static int timer_dev_open(struct inode *inode, struct file *filp)
{
  return 0;
}

static int timer_dev_release(struct inode *inode, struct file *filp)
{
  return 0;
}

static ssize_t timer_dev_read(struct file *filp, char *buf, size_t count, loff_t *f_pos)
{
  if (strnlen(timer_dev_data_out, sizeof(timer_dev_data_out)) < count) {
    count = strnlen(timer_dev_data_out, sizeof(timer_dev_data_out));
  }
  // copy data from kernel space to user space
  __copy_to_user(buf, timer_dev_data_out, count);
  timer_dev_data_out[0] = 0;
  return count;
}

static ssize_t timer_dev_write(struct file *filp, const char *buf, size_t count, loff_t *f_pos)
{
  if (sizeof(timer_dev_data_in) < count) {
    count = sizeof(timer_dev_data_in) - 1;
    LOG("ERROR input data dropped\n");
  }
  // copy user data into kernel space
  __copy_from_user(timer_dev_data_in, buf, count);
  timer_dev_data_in[count] = 0;
  parse_argument(timer_dev_data_in);
  return count;
}

static void regist_char_device(void)
{
  // define file operations
  static struct file_operations timer_dev_fops = {
    .owner   = THIS_MODULE,
    .read    = timer_dev_read,
    .write   = timer_dev_write,
    .open    = timer_dev_open,
    .release = timer_dev_release,
  };
  // dynamically allocate a major
  timer_dev_major = register_chrdev(0, DEVICE_NAME, &timer_dev_fops);
  if (timer_dev_major < 0) {
    LOG("ERROR cannot register the character device\n");
  } else {
    timer_dev_class = class_create(THIS_MODULE, DEVICE_NAME);
    device_create(timer_dev_class, NULL, MKDEV(timer_dev_major, 0), NULL, DEVICE_NAME);
  }
}

static void unregister_char_device(void)
{
  unregister_chrdev(timer_dev_major, DEVICE_NAME);
  device_destroy(timer_dev_class, MKDEV(timer_dev_major,0));
  class_unregister(timer_dev_class);
  class_destroy(timer_dev_class);
}

// ------------------------------------------

// kernel module initialization function
static int __init mod_init(void)
{
  regist_char_device();

  // create the timer
  hrtimer_init(&timer, TIMER_ID, TIMER_MODE);
  timer_running = false;
  // get memory-mapped access to the actuation GPIOs
  map_gpio();
  // create semaphore for the queue
  sema_init(&queue_sem, 1);
  // clear the queue
  clear_queue();

  LOG("init\n");

  return 0;
}

// kernel module exit function
static void __exit mod_exit(void)
{
  unregister_char_device();
  hrtimer_cancel(&timer);
  LOG("deinit\n");
}

module_init(mod_init);
module_exit(mod_exit);
MODULE_LICENSE("GPL");
