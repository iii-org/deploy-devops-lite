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

bin_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
project_dir="$(cd "$(dirname "$bin_dir")" && pwd)"

cd "$project_dir" || FAILED "Failed to change directory to $project_dir"
env_file="${project_dir}"/.env

# If .env file not exists, copy from .env.example
if [ ! -f "$env_file" ]; then
  cp "$env_file".example "$env_file"
fi

# Load .env file
set -a
# shellcheck source=/dev/null
. "$env_file"
set +a
