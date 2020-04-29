PRU_FW_INFILE=pru_logic.out
PRU_FW_INFILE2=pru_logic_1M.out
PRU_FW_INFILE3=pru_logic_100k.out
PRU_FW_OUTFILE=fl_pru1_logic.bin
PRU_FW_OUTFILE2=fl_pru1_logic_1M.bin
PRU_FW_OUTFILE3=fl_pru1_logic_100k.bin
PRU_FW_OUTFILE4=fl_pru0_logic_helper.bin

TARGET_BINARY=fl_logic

INSTALL_BIN_DIR = /bin
INSTALL_FIRMWARE_DIR = /lib/firmware


all: pru
	@gcc -Werror -Wall -Wextra -lprussdrv -o $(TARGET_BINARY) fl_logic.c
#@gcc -Werror -Wall -Wextra -lprussdrv -o $(TARGET_BINARY)_interactive -DINTERACTIVE_MODE fl_logic.c

pru:
	@hexpru $(PRU_FW_INFILE) -b -o $(PRU_FW_OUTFILE) > /dev/null
	@hexpru $(PRU_FW_INFILE2) -b -o $(PRU_FW_OUTFILE2) > /dev/null
	@hexpru $(PRU_FW_INFILE3) -b -o $(PRU_FW_OUTFILE3) > /dev/null

install: all
	@cp -f $(PRU_FW_OUTFILE) $(INSTALL_FIRMWARE_DIR)
	@cp -f $(PRU_FW_OUTFILE2) $(INSTALL_FIRMWARE_DIR)
	@cp -f $(PRU_FW_OUTFILE3) $(INSTALL_FIRMWARE_DIR)
	@cp -f $(TARGET_BINARY) $(INSTALL_BIN_DIR)
