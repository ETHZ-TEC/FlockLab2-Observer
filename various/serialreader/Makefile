
TARGET_BINARY = serialreader
INSTALL_BIN_DIR = /bin

all:
	@gcc -Wall -Werror -Wextra -o $(TARGET_BINARY) serialreader.c
	
install: all
	@cp -f $(TARGET_BINARY) $(INSTALL_BIN_DIR)
