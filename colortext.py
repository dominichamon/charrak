#!/usr/bin/env python
import sys

WARNING = '\033[93m'
FAIL = '\033[91m'
ENDC = '\033[0m'

PLAIN = "\033[0m"
BOLD  = "\033[1m"
UNDERLINED = "\033[4m"
INVERSE = "\033[7m"
DRED = "\033[31m"
DGREEN = "\033[32m"
ORANGE = "\033[33m"
DBLUE = "\033[34m"
DPURPLE = "\033[35m"
DCYAN = "\033[36m"
BG_DGRAY = "\033[37m" # light gray background
BG_OLIVE = "\033[40m"
BG_RED = "\033[41m"
BG_GREEN = "\033[42m"
BG_ORANGE = "\033[43m"
BG_BLUE = "\033[44m"
BG_PURPLE = "\033[45m"
BG_TURQUOISE = "\033[46m"
BG_GRAY = "\033[47m"
GRAY = "\033[90m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
PURPLE = "\033[95m"
CYAN = "\033[96m"
BG_GRAY = "\033[100m"
BG_RED = "\033[101m"
BG_LGREEN = "\033[102m"
BG_YELLOW = "\033[103m"
BG_LBLUE = "\033[104m"
BG_PURPLE = "\033[105m"
BG_CYAN = "\033[106m"
BG_LGRAY = "\033[107m"

def cprint(color, text):
    sys.stdout.write(color + text + ENDC)
    sys.stdout.flush()