#!/usr/bin/env bash

trap_exit() {
  local return_value=$?

  # If spinner is running, kill it
  if [[ "${SPINNING:-}" = true ]]; then
    tput cnorm # cursor visible
    if kill -0 "$SPIN_CURRENT" 2>/dev/null; then
      kill "$SPIN_CURRENT" >/dev/null 2>&1
    fi
  fi

  if [[ "$return_value" -eq 0 ]]; then
    DEBUG "Stopping script...[${ORANGE}$$${NOFORMAT}]"

    if [[ -n "${PARENT_PID:-}" ]]; then
      DEBUG " -> Parent PID: ${ORANGE}${PARENT_PID}${NOFORMAT}"
    fi

    if [[ "${PARENT_PID:-}" -eq "$$" ]]; then
      INFO "Script executed successfully"
    fi
  fi

  exit "$return_value"
}

trap_traceback() {
  local return_value=$?

  # If the script is not running with -e, then do not print the traceback
  if [[ ! $- =~ "e" ]]; then
    return
  fi

  collect_device_info ${LOG_DEVICE_INFO}

  # Check if .git exists
  if [ -d "${PROJECT_DIR:?}"/.git ]; then
    ERROR "Git commit hash: ${WHITE}$(git describe --always --dirty)${NOFORMAT}"
  fi

  # Modified from https://gist.github.com/Asher256/4c68119705ffa11adb7446f297a7beae
  set +o xtrace
  local bash_command=${BASH_COMMAND}
  ERROR "In ${BASH_SOURCE[1]}:${BASH_LINENO[0]}"
  ERROR "\\t${WHITE}${bash_command}${NOFORMAT} exited with status $return_value"

  if [ ${#FUNCNAME[@]} -gt 2 ]; then
    # Print out the stack trace described by $function_stack
    ERROR "Traceback of ${BASH_SOURCE[1]} (most recent call last):"
    for ((i = 0; i < ${#FUNCNAME[@]} - 1; i++)); do
      local funcname="${FUNCNAME[$i]}"
      [ "$i" -eq "0" ] && funcname=$bash_command
      ERROR "  ${BASH_SOURCE[$i + 1]}:${BASH_LINENO[$i]}\\t$funcname"
    done
  fi

  ERROR "======================================================"
  ERROR "Logging files is located at: ${ORANGE}${LOG_FOLDER}${NOFORMAT}"
  ERROR "System info collected in: ${ORANGE}${LOG_DEVICE_INFO}${NOFORMAT}"
  ERROR "Please attach the log file(s) when reporting the issue."
}

trap_ctrlc() {
  if [[ "$$" -ne "$PARENT_PID" ]]; then
    DEBUG "Ctrl+C detected, but ignored in subshell."
    exit 130
  fi

  echo
  WARN "Script interrupted by Ctrl+C (SIGINT)"
  exit 130
}

set -E
trap '{ trap_ctrlc; } 2>/dev/null' INT
trap '{ trap_traceback; }' ERR
trap '{ trap_exit; } 2>/dev/null' EXIT
