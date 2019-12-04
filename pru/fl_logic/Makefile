PRU_FW_FILE=pru_logic.out

ALL:
	gcc -Werror -Wall -Wextra -lprussdrv -o fl_logic fl_logic.c

PRU:
	hexpru $(PRU_FW_FILE) -b -o pru_logic.bin
	rm pru_logic.b10
