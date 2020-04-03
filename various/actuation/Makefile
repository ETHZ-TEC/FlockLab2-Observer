obj-m:=fl_actuation.o
PWD:=$(shell pwd)
KERNELPATH:=/lib/modules/$(shell uname -r)/build
all:
	make -C $(KERNELPATH) M=$(PWD) modules
clean:
	sudo rmmod fl_actuation
	make -C $(KERNELPATH) M=$(PWD) clean
load:
	sudo insmod fl_actuation.ko
unload:
	sudo rmmod fl_actuation
