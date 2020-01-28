PRU_FW_INFILE=pru_logic.out
PRU_FW_OUTFILE=fl_pru1_logic.bin

TARGET_BINARY=fl_logic

INSTALL_BIN_DIR = /bin
INSTALL_FIRMWARE_DIR = /lib/firmware


all: pru
	@gcc -Werror -Wall -Wextra -lprussdrv -o $(TARGET_BINARY) fl_logic.c
	@gcc -Werror -Wall -Wextra -lprussdrv -o $(TARGET_BINARY)_interactive -DINTERACTIVE_MODE fl_logic.c

pru:
	@hexpru $(PRU_FW_INFILE) -b -o $(PRU_FW_OUTFILE) > /dev/null

install: all
	@cp -f $(PRU_FW_OUTFILE) $(INSTALL_FIRMWARE_DIR)
	@cp -f $(TARGET_BINARY) $(INSTALL_BIN_DIR)
