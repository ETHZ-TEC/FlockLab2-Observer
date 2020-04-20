/**
 * PPS generator for the BeagleBone Green
 * Outputs a pulse per second on a GPIO.
 * tested with kernel 4.14
 *
 * The selected pin must be set as GPIO output:
 *   echo out > /sys/class/gpio/gpio60/direction
 *
 * 2020, rdaforno
 */

// --- INCLUDES ---

#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/hrtimer.h>
#include <linux/ktime.h>
#include <linux/fs.h>
#include <linux/uaccess.h>
#include <linux/device.h>
#include <linux/delay.h>
#include <asm/io.h>


// --- CONFIG / DEFINES ---

#define PRINT_PREFIX        "PPS generator: " // prefix for log printing
#define PIN_NUMBER          60                // pin to toggle, 60 = P9.12
#define DUTY_CYCLE          10                // in percent
#define MAX_WAIT            220000            // max. time to wait for the full second, in nanoseconds
#define TIME_OFFSET         -(120000 + MAX_WAIT / 2)  // offset in nanoseconds (average offset is ~120us)


// --- MACROS ---

#define TIMER_NOW_NS()      ktime_get_ns()        // ktime_to_ns(ktime_get())
#define TIMER_NOW_NS_REAL() ktime_get_real_ns()   // ktime_to_ns(ktime_get_real())

#define GPIO0_START_ADDR    0x44E07000            // see am335x RM p.180
#define GPIO1_START_ADDR    0x4804C000
#define GPIO2_START_ADDR    0x481AC000
#define GPIO3_START_ADDR    0x481AE000
#define GPIO_MEM_SIZE       0x2000
#define GPIO_OE_OFS         0x134
#define GPIO_SET_OFS        0x194
#define GPIO_CLR_OFS        0x190
#define PIN_MASK            (1 << (PIN_NUMBER & 31))
#if PIN_NUMBER < 32
  #define GPIO_ADDR         GPIO0_START_ADDR
#elif PIN_NUMBER < 64
  #define GPIO_ADDR         GPIO1_START_ADDR
#elif PIN_NUMBER < 96
  #define GPIO_ADDR         GPIO2_START_ADDR
#else
  #define GPIO_ADDR         GPIO3_START_ADDR
#endif

// error check
#if DUTY_CYCLE == 0 || DUTY_CYCLE >= 100
#error "Invalid DUTY_CYCLE"
#endif


// --- GLOBAL VARIABLES ---

static struct hrtimer timer;      // realtime timer
static ktime_t        t_period;   // timer period, only used for the monotonic timer
static ktime_t        t_prev;

static volatile unsigned int* gpio_set_addr = NULL;
static volatile unsigned int* gpio_clr_addr = NULL;


// --- FUNCTIONS ---

static void gpio_set(void)
{
  if (gpio_set_addr) {
    *gpio_set_addr = PIN_MASK;
  }
}

static void gpio_clr(void)
{
  if (gpio_clr_addr) {
    *gpio_clr_addr = PIN_MASK;
  }
}

static void map_gpio(void)
{
  volatile void* gpio_addr_mapped;
  gpio_addr_mapped = ioremap(GPIO_ADDR, GPIO_MEM_SIZE);

  if (gpio_addr_mapped == 0) {
    printk(PRINT_PREFIX "Unable to map GPIO\n");
    return;
  }
  gpio_set_addr = gpio_addr_mapped + GPIO_SET_OFS;
  gpio_clr_addr = gpio_addr_mapped + GPIO_CLR_OFS;
  printk(PRINT_PREFIX "GPIO peripheral address mapped to %p\n", gpio_addr_mapped);
}

// ------------------------------------------

// timer callback function
static enum hrtimer_restart timer_expired(struct hrtimer *tim)
{
  static bool prev_state = false;
  struct   timespec ts_now;
  ktime_t  t_next;
  uint32_t delta;

  ktime_get_real_ts(&ts_now);
  if (!prev_state) {
    delta = 1000000000 - (uint32_t)ts_now.tv_nsec;
    if (delta > MAX_WAIT) {
      delta = MAX_WAIT;
    }
    ndelay(delta);  /* busy wait */
  }

  /* change the GPIO state */
  prev_state = !prev_state;
  if (prev_state) {
    gpio_set();   /* rising edge */
  } else {
    gpio_clr();   /* falling edge */
  }

  /* calculate next wakeup and print some stats */
  if (prev_state) {
    /* calc deviation compared to last interrupt */
    int32_t deviation;
    ktime_t t_now;
    t_now = ktime_set(ts_now.tv_sec, ts_now.tv_nsec);
    deviation = (int32_t)(t_now - t_prev - t_period) / 1000;  /* convert to us */
    /* calc diff to next full second */
    printk(PRINT_PREFIX "%dus deviation, wait time: %uns\n", deviation, delta);
    t_prev = t_now;
    t_next = (DUTY_CYCLE * 10000000);   /* convert to ns */
  } else {
    t_next = t_period - (DUTY_CYCLE * 10000000);
  }
  // set next expiration time
  hrtimer_forward(tim, tim->_softexpires, t_next);
  return HRTIMER_RESTART;
}

// set one shot timer (absolute mode, uses realtime timer)
static void timer_start(void)
{
  struct timespec t_start;
  // make sure the timer is not running anymore
  hrtimer_cancel(&timer);
  timer.function = timer_expired;
  getnstimeofday(&t_start);
  t_prev = ktime_set(t_start.tv_sec, 0) + TIME_OFFSET;
  t_period = ktime_set(1, 0);
  hrtimer_start(&timer, t_prev, HRTIMER_MODE_ABS);
}

// ------------------------------------------

// kernel module initialization function
static int __init mod_init(void)
{
  // map GPIO address region
  map_gpio();
  // create and start the timer
  hrtimer_init(&timer, CLOCK_REALTIME, HRTIMER_MODE_ABS);
  timer_start();
  printk(PRINT_PREFIX "module loaded\n");
  return 0;
}

// kernel module exit function
static void __exit mod_exit(void)
{
  hrtimer_cancel(&timer);
  printk(PRINT_PREFIX "module removed\n");
}

module_init(mod_init);
module_exit(mod_exit);
MODULE_LICENSE("GPL");
