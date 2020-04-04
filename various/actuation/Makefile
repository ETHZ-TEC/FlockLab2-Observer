
obj-m := fl_actuation.o
MODNAME = fl_actuation
PWD := $(shell pwd)
KDIR := /lib/modules/$(shell uname -r)/build
KVER := $(shell uname -r)

.PHONY: all
all:
	make -C $(KDIR) M=$(PWD) modules
clean:
	make -C $(KDIR) M=$(PWD) clean

.PHONY: install
install: all
	install -D $(MODNAME).ko /lib/modules/$(KVER)/extra/
