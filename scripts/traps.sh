#!/usr/bin/env bash

trap_exit() {
  local return_value=$?

  { debug_disable; } 2>/dev/null

  # If spinner is running, kill it
  if [[ "${SPINNING:-}" = true ]]; then
    tput cnorm # cursor visible
    if kill -0 "$SPIN_CURRENT" 2>/dev/null; then
      kill "$SPIN_CURRENT" >/dev/null 2>&1
    fi
  fi

  if [[ "$return_value" -eq 130 ]]; then
    # Catch SIGINT (Ctrl+C) by trap_ctrlc
    exit 130
  elif [[ "$return_value" -eq 21 ]]; then
    # Catch exit 21 by usage
    exit 21
  elif [[ "$return_value" -eq 0 ]]; then
    NOTICE "Script executed successfully"
  else
    exit "$return_value"
  fi
}

trap_traceback() {
  local return_value=$?

  { debug_disable; } 2>/dev/null

  __collect_system_info() {
    local log_file="${1:?}"

    echo "================= System Information =================" >>"$log_file"
    echo "Date: $(date -u +"%Y-%m-%d %H:%M:%S") (UTC)" >>"$log_file"
    echo "Hostname: $(hostname)" >>"$log_file"
    echo "Kernel: $(uname -a)" >>"$log_file"
    echo "Current user: $(whoami)" >>"$log_file"
    echo "PWD: $PWD" >>"$log_file"
    echo "Shell: $SHELL" >>"$log_file"

    echo "=== Docker info ===" >>"$log_file"
    if command -v docker >/dev/null 2>&1; then
      echo "Docker version: $(docker version -f '{{.Server.Version}}')" >>"$log_file"

      echo "Docker security options:" >>"$log_file"
      docker info -f '{{.SecurityOptions}}' >>"$log_file"

      if docker compose version &>/dev/null; then
        echo "Docker compose command: docker compose" >>"$log_file"
        echo "Docker compose version: $(docker compose version | grep -oP '(?<=version )[^,]+')" >>"$log_file"
      elif docker-compose --version &>/dev/null; then
        echo "Docker compose command: docker-compose" >>"$log_file"
        echo "Docker compose version: $(docker-compose --version | grep -oP '(?<=version )[^,]+')" >>"$log_file"
      else
        echo "Docker compose command: NOT FOUND" >>"$log_file"
      fi
    else
      echo "Docker: NOT FOUND" >>"$log_file"
      echo "Docker compose command: NOT FOUND" >>"$log_file"
    fi

    echo "======================================================" >>"$log_file"
    echo "" >>"$log_file"
    echo "================== /etc/os-release ===================" >>"$log_file"
    cat /etc/os-release >>"$log_file"
    echo "======================================================" >>"$log_file"
    echo "" >>"$log_file"
    echo "====================== Variables =====================" >>"$log_file"
    ulimit -a >>"$log_file"
    echo "======================================================" >>"$log_file"
    env | sort >>"$log_file"
    echo "======================================================" >>"$log_file"
    (
      set -o posix
      set
    ) >>"$log_file"
    echo "======================================================" >>"$log_file"
    echo "" >>"$log_file"
    echo "============= System memory and CPU info =============" >>"$log_file"
    echo "Architecture: $(uname -m)" >>"$log_file"
    echo "Bits: $(getconf LONG_BIT)" >>"$log_file"
    echo "CPU(s): $(nproc)" >>"$log_file"
    echo "Model name: $(cat /proc/cpuinfo | grep "model name" | head -n1 | cut -d ":" -f2 | xargs)" >>"$log_file"
    free -h >>"$log_file"
    echo "======================================================" >>"$log_file"
  }

  __logging() {
    local message="${1:-}"
    local log_file="${2:?}"

    echo -e "$message" >>"$log_file"
  }

  # If the script is not running with -e, then do not print the traceback
  if [[ ! $- =~ "e" ]]; then
    return
  fi

  local log_file
  log_file="$(mktemp -t Devops-Lite-Error-XXXXXXXXXX.log)"

  __collect_system_info "$log_file"
  __logging "" "$log_file"
  __logging "=================== Error message ====================" "$log_file"

  # Check if .git exists
  if [ -d "${PROJECT_DIR:?}"/.git ]; then
    __logging "Git commit hash: $(git describe --always --dirty)" "$log_file"
    ERROR "Git commit ID: ${WHITE}$(git describe --always --dirty)${NOFORMAT}"
  fi

  # Modified from https://gist.github.com/Asher256/4c68119705ffa11adb7446f297a7beae
  set +o xtrace
  local bash_command=${BASH_COMMAND}
  ERROR "In ${BASH_SOURCE[1]}:${BASH_LINENO[0]}"
  ERROR "\\t${WHITE}${bash_command}${NOFORMAT} exited with status $return_value"
  __logging "In ${BASH_SOURCE[1]}:${BASH_LINENO[0]}" "$log_file"
  __logging "   Command: ${bash_command}" "$log_file"
  __logging "   Exit code: ${return_value}" "$log_file"
  __logging "" "$log_file"

  if [ ${#FUNCNAME[@]} -gt 2 ]; then
    # Print out the stack trace described by $function_stack
    ERROR "Traceback of ${BASH_SOURCE[1]} (most recent call last):"
    __logging "Traceback of ${BASH_SOURCE[1]} (most recent call last):" "$log_file"
    for ((i = 0; i < ${#FUNCNAME[@]} - 1; i++)); do
      local funcname="${FUNCNAME[$i]}"
      [ "$i" -eq "0" ] && funcname=$bash_command
      ERROR "  ${BASH_SOURCE[$i + 1]}:${BASH_LINENO[$i]}\\t$funcname"
      __logging "  ${BASH_SOURCE[$i + 1]}:${BASH_LINENO[$i]}\t$funcname" "$log_file"
    done
    __logging "" "$log_file"
  fi

  ERROR "======================================================"
  ERROR "System information has been written to: ${ORANGE}${log_file}${NOFORMAT}"
  ERROR "Please attach the log file(s) when reporting the issue."
}

trap_ctrlc() {
  { debug_disable; } 2>/dev/null

  NOTICE "Script interrupted by Ctrl+C (SIGINT)"
  exit 130
}

trap_debug() {
  {
    set +x

    if $DEBUG; then
      echo -n "[$(date -Is)]  "
      set -x
    fi
  } 2>/dev/null
}

set -E
trap '{ trap_ctrlc; } 2>/dev/null' INT
trap '{ trap_traceback; }' ERR
trap '{ trap_exit; } 2>/dev/null' EXIT
trap '{ trap_debug; } 2>/dev/null' DEBUG
