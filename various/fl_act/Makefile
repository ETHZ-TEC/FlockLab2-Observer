TARGET_BINARY   = fl_act
INSTALL_BIN_DIR = /bin


all:
	@gcc -Werror -Wall -Wextra -lprussdrv -o $(TARGET_BINARY) fl_act.c

install: all
	@cp -f $(TARGET_BINARY) $(INSTALL_BIN_DIR)
