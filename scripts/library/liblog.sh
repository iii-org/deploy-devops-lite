#!/bin/bash

# https://serverfault.com/a/103569
# https://unix.stackexchange.com/a/145654
# https://blog.tratif.com/2023/01/09/bash-tips-1-logging-in-shell-scripts/
# https://medium.com/_/dd657970cd5d

ERROR=5
WARNING=4
NOTICE=3
INFO=2
DEBUG=1

LOG_LEVEL=${LOG_LEVEL:-${INFO}}
LOG_FOLDER="${PROJECT_DIR}/logs"
export LOG_FOLDER
LOG_LOGGING="${LOG_FOLDER}/logging.log"
LOG_DEVICE_INFO="${LOG_FOLDER}/device_info.log"
export LOG_DEVICE_INFO

# declare array for level string
declare -a LOG_LEVEL_MAP
LOG_LEVEL_MAP=(
  [${ERROR}]="[ERROR]"
  [${WARNING}]="[WARNING]"
  [${NOTICE}]="[NOTICE]"
  [${INFO}]="[INFO]"
  [${DEBUG}]="[DEBUG]"
)

declare -a LOG_LEVEL_COLOR
LOG_LEVEL_COLOR=(
  [${ERROR}]=${RED}
  [${WARNING}]=${ORANGE}
  [${NOTICE}]=${YELLOW}
  [${INFO}]=${GREEN}
  [${DEBUG}]=${CYAN}
)

msg() {
  local level=$1
  local message=${*:2}
  local timestamp
  timestamp=$(date +"%H:%M:%S")

  if [[ ${level} -ge ${LOG_LEVEL} ]]; then
    local prefix_string="${LOG_LEVEL_COLOR[${level}]}${LOG_LEVEL_MAP[${level}]}${NOFORMAT} ${timestamp}"

    printf "$prefix_string %b\n" "${*:2}"

    timestamp=$(date +"%m/%d %H:%M:%S")

    if [[ ! -d "${LOG_FOLDER}" ]]; then
      mkdir -p "${LOG_FOLDER}"
    fi

    echo -e "${timestamp} ${LOG_LEVEL_MAP[${level}]} ${message}" >>"${LOG_LOGGING}"
  fi
}

DEBUG() {
  msg ${DEBUG} "${*}"
}

INFO() {
  msg ${INFO} "${*}"
}

NOTICE() {
  msg ${NOTICE} "${*}"
}

WARNING() {
  msg ${WARNING} "${*}"
}

WARN() {
  WARNING "${*}"
}

ERROR() {
  msg ${ERROR} "${*}"
}

FAILED() {
  local msg=$1
  local code=${2-1} # default exit status 1
  ERROR "${msg}"
  exit "$code"
}

_LOG_STARTED() {
  if [[ -n "${PARENT_PID:-}" ]]; then
    DEBUG " [PID] Parent: ${ORANGE}${PARENT_PID}${NOFORMAT}"
    DEBUG " [PID] Self: ${ORANGE}$$${NOFORMAT}"
    return
  fi

  printf "%$(tput cols)s\n" | tr " " "=" >>"${LOG_LOGGING}"
  echo "New logging started at: $(date +"%Y/%m/%d %H:%M:%S [%z]")" >>"${LOG_LOGGING}"

  PARENT_PID=$$
  export PARENT_PID
  DEBUG "Parent process started in: ${ORANGE}${PARENT_PID}${NOFORMAT}"
}

collect_device_info() {
  local log_file="$1"

  echo "================= System Information =================" >>"${log_file}"
  echo "Date: $(date -u +"%Y-%m-%d %H:%M:%S") (UTC)" >>"${log_file}"
  echo "Hostname: $(hostname)" >>"${log_file}"
  echo "Kernel: $(uname -a)" >>"${log_file}"
  echo "Current user: $(whoami)" >>"${log_file}"
  echo "PWD: $PWD" >>"${log_file}"
  echo "Shell: $SHELL" >>"${log_file}"

  echo "=== Docker info ===" >>"${log_file}"
  if command -v docker >/dev/null 2>&1; then
    echo "Docker version: $(docker version -f '{{.Server.Version}}')" >>"${log_file}"

    echo "Docker security options:" >>"${log_file}"
    docker info -f '{{.SecurityOptions}}' >>"${log_file}"

    if docker compose version &>/dev/null; then
      echo "Docker compose command: docker compose" >>"${log_file}"
      echo "Docker compose version: $(docker compose version | grep -oP '(?<=version )[^,]+')" >>"${log_file}"
    elif docker-compose --version &>/dev/null; then
      echo "Docker compose command: docker-compose" >>"${log_file}"
      echo "Docker compose version: $(docker-compose --version | grep -oP '(?<=version )[^,]+')" >>"${log_file}"
    else
      echo "Docker compose command: NOT FOUND" >>"${log_file}"
    fi
  else
    echo "Docker: NOT FOUND" >>"${log_file}"
    echo "Docker compose command: NOT FOUND" >>"${log_file}"
  fi

  echo "======================================================" >>"${log_file}"
  echo "" >>"${log_file}"
  echo "================== /etc/os-release ===================" >>"${log_file}"
  cat /etc/os-release >>"${log_file}"
  echo "======================================================" >>"${log_file}"
  echo "" >>"${log_file}"
  echo "====================== Variables =====================" >>"${log_file}"
  ulimit -a >>"${log_file}"
  echo "======================================================" >>"${log_file}"
  env | sort >>"${log_file}"
  echo "======================================================" >>"${log_file}"
  (
    set -o posix
    set
  ) >>"${log_file}"
  echo "======================================================" >>"${log_file}"
  echo "" >>"${log_file}"
  echo "============= System memory and CPU info =============" >>"${log_file}"
  echo "Architecture: $(uname -m)" >>"${log_file}"
  echo "Bits: $(getconf LONG_BIT)" >>"${log_file}"
  echo "CPU(s): $(nproc)" >>"${log_file}"
  echo "Model name: $(cat /proc/cpuinfo | grep "model name" | head -n1 | cut -d ":" -f2 | xargs)" >>"${log_file}"
  free -h >>"${log_file}"
  echo "======================================================" >>"${log_file}"
}

_LOG_STARTED
