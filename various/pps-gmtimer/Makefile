ifneq ($(KERNELRELEASE),)
# kbuild part of makefile
obj-m  := pps-gmtimer.o

else
# normal makefile
KDIR = /lib/modules/$(shell uname -r)/build

MY_CFLAGS += -g -DDEBUG
ccflags-y += ${MY_CFLAGS}
CC += ${MY_CFLAGS}
KVERSION := $(shell uname -r)

.PHONY: default clean

default:
	$(MAKE) -C $(KDIR) M=$$PWD ARCH=arm

debug:
	$(MAKE) -C $(KDIR) M=$$PWD ARCH=arm EXTRA_CFLAGS="$(MY_CFLAGS)"

clean:
	$(MAKE) -C $(KDIR) M=$$PWD ARCH=arm clean

.PHONY: install
install: default
	install -D pps-gmtimer.ko /lib/modules/$(KVERSION)/extra/

endif
