obj-m:=hrtimer.o
PWD:=$(shell pwd)
KERNELPATH:=/lib/modules/$(shell uname -r)/build
all:
	make -C $(KERNELPATH) M=$(PWD) modules
clean:
	sudo rmmod hrtimer
	make -C $(KERNELPATH) M=$(PWD) clean
load:
	sudo insmod hrtimer.ko
unload:
	sudo rmmod hrtimer
