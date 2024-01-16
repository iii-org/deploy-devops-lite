#!/usr/bin/env bash

# Set the default color variables
# https://misc.flogisoft.com/bash/tip_colors_and_formatting
# https://stackoverflow.com/questions/5947742/how-to-change-the-output-color-of-echo-in-linux
# https://stackoverflow.com/questions/4332478/read-the-current-text-color-in-a-xterm/4332530#4332530

CLEAR_LINE="\r\033[2K"
CUSOR_UP="\033[A"
HIDE_CURSOR="\033[?25l"
SHOW_CURSOR="\033[?25h"
if [[ -z "${NO_COLOR-}" ]] && [[ "${TERM-}" != "dumb" ]]; then
  NOFORMAT='\033[0m'
  RED='\033[31m'
  GREEN='\033[32m'
  ORANGE='\033[33m'
  BLUE='\033[34m'
  PURPLE='\033[35m'
  CYAN='\033[36m'
  YELLOW='\033[33m'
  WHITE='\033[97m'
else
  NOFORMAT=''
  RED=''
  GREEN=''
  ORANGE=''
  BLUE=''
  PURPLE=''
  CYAN=''
  YELLOW=''
  WHITE=''
fi

# Freeze the variable
readonly CLEAR_LINE
readonly CUSOR_UP
readonly HIDE_CURSOR
readonly SHOW_CURSOR
readonly NOFORMAT
readonly RED
readonly GREEN
readonly ORANGE
readonly BLUE
readonly PURPLE
readonly CYAN
readonly YELLOW
readonly WHITE

export CLEAR_LINE
export CUSOR_UP
export HIDE_CURSOR
export SHOW_CURSOR
export NOFORMAT
export RED
export GREEN
export ORANGE
export BLUE
export PURPLE
export CYAN
export YELLOW
export WHITE
