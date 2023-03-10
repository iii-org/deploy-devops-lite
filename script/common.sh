#!/usr/bin/env bash

INFO() {
  printf "\e[1;32m[INFO]\e[0m %b\n" "$*"
}

NOTICE() {
  printf "\e[1;96m[NOTICE]\e[0m %b\n" "$*"
}

WARN() {
  printf "\e[1;33m[WARN]\e[0m %b\n" "$*"
}

ERROR() {
  printf "\e[1;31m[ERROR]\e[0m %b\n" "$*" >&2
}

FAILED() {
  printf "\e[1;31m[FAILED]\e[0m %b\n" "$*" >&2
  exit 1
}

command_exists() {
  command -v "$@" >/dev/null 2>&1
}

url_encode() {
  local string="${1}"
  local strlen=${#string}
  local encoded=""
  local pos c o

  for ((pos = 0; pos < strlen; pos++)); do
    c=${string:$pos:1}
    case "$c" in
    [-_.~a-zA-Z0-9]) o="${c}" ;;
    *) printf -v o '%%%02x' "'$c" ;;
    esac
    encoded+="${o}"
  done
  echo "${encoded}"
}

url_decode() {
  local url_encoded="${1//+/ }"
  printf '%b' "${url_encoded//%/\\x}"
}

check_docker_in_rootless() {
  local response

  if ! command_exists docker; then
    FAILED "Docker not found, please install docker first"
  fi

  response="$(docker info -f '{{json .SecurityOptions}}' 2>&1)"

  # Check if docker is running in rootless mode
  if echo "$response" | grep -q "rootless"; then
    # Rootless mode
    echo "true"
  else
    # If response contains "permission denied"
    if echo "$response" | grep -q "permission denied"; then
      # Root mode
      echo "false"
    else
      # Unknown mode
      FAILED "Failed to check if docker is running in rootless mode"
    fi
  fi
}

print_exit() {
  local return_value=$?
  if [ "$return_value" -eq 130 ]; then
    # Catch SIGINT (Ctrl+C) by trap_ctrlc
    exit 130
  elif [ "$return_value" -eq 21 ]; then
    # Catch exit 21 by usage
    exit 21
  elif [ "$return_value" -eq 0 ]; then
    NOTICE "Script executed successfully"
  else
    ERROR "Exit with code $return_value, please check the error message above"
    exit "$return_value"
  fi
}

bash_traceback() {
  if [[ ! $- =~ "e" ]]; then
    return
  fi

  # Modified from https://gist.github.com/Asher256/4c68119705ffa11adb7446f297a7beae
  local return_value=$?
  set +o xtrace
  local bash_command=${BASH_COMMAND}
  ERROR "In ${BASH_SOURCE[1]}:${BASH_LINENO[0]}"
  ERROR "\\t\e[97m${bash_command}\e[0m exited with status $return_value"

  if [ ${#FUNCNAME[@]} -gt 2 ]; then
    # Print out the stack trace described by $function_stack
    ERROR "Traceback of ${BASH_SOURCE[1]} (most recent call last):"
    for ((i = 0; i < ${#FUNCNAME[@]} - 1; i++)); do
      local funcname="${FUNCNAME[$i]}"
      [ "$i" -eq "0" ] && funcname=$bash_command
      ERROR "  ${BASH_SOURCE[$i + 1]}:${BASH_LINENO[$i]}\\t$funcname"
    done
  fi
}

trap_ctrlc() {
  NOTICE "Script interrupted by Ctrl+C (SIGINT)"
  exit 130
}

set -E
trap trap_ctrlc INT
trap bash_traceback ERR
trap print_exit EXIT

bin_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
project_dir="$(cd "$(dirname "$bin_dir")" && pwd)"

cd "$project_dir" || FAILED "Failed to change directory to $project_dir"
env_file="${project_dir}"/.env

# If .env file not exists, copy from .env.example
if [ ! -f "$env_file" ]; then
  cp "$env_file".example "$env_file"
  "${bin_dir:?}"/generate_env.sh all
fi

# Load .env file
set -a
# shellcheck source=/dev/null
. "$env_file"
set +a
