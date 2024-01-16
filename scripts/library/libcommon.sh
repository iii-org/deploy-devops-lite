#!/usr/bin/env bash

command_exists() {
  command -v "$@" >/dev/null 2>&1
}

get_distribution() {
  # Modified from https://get.docker.com/
  local dists=""
  # Every system that we officially support has /etc/os-release
  if [ -r /etc/os-release ]; then
    dists="$(. /etc/os-release && echo "$ID")"
  fi
  # Returning an empty string here should be alright since the
  # case statements don't act unless you provide an actual value
  echo "$dists" | tr '[:upper:]' '[:lower:]'
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

get_init_token() {
  if [[ -z "${GITLAB_INIT_TOKEN:-}" ]]; then
    # If not set, get from HEAD.env
    if [[ ! -f "${PROJECT_DIR}/generate/HEAD.env" ]]; then
      ERROR "Cannot find HEAD.env, please run ${WHITE}${PROJECT_DIR}/run.sh${NOFORMAT} to start services."
      exit 1
    fi

    source "${PROJECT_DIR}/generate/HEAD.env"

    if [[ -z "${GITLAB_INIT_TOKEN:-}" ]]; then
      ERROR "Cannot find GITLAB_INIT_TOKEN in HEAD.env, please run ${WHITE}${PROJECT_DIR}/run.sh${NOFORMAT} to start services."
      exit 1
    else
      variable_write "GITLAB_INIT_TOKEN" "${GITLAB_INIT_TOKEN}"
    fi
  fi
  DEBUG "Using init token: ${ORANGE}${GITLAB_INIT_TOKEN}${NOFORMAT}"
}

check_runas_root() {
  if [ "$(id -u)" == "0" ]; then
    ERROR "Please run this script as normal user, not root."
    exit 1
  fi

  if ! command_exists sudo; then
    ERROR "No sudo command found, please install sudo and add your user to sudoers."
    exit 1
  fi

  INFO "✅ Running as a non-root user!"
}

check_distro() {
  local distro
  distro="$(get_distribution)"

  # Check if distro is based on Debian
  if [[ "$distro" == "ubuntu" || "$distro" == "debian" ]]; then
    INFO "✅ Supported system: ${GREEN}$distro${NOFORMAT}, continue..."
  else
    # Check ID_LIKE
    local id_like
    # shellcheck disable=SC2153
    id_like="$(. /etc/os-release && echo "$ID_LIKE")"
    # If ID_LIKE contains "debian", then it's based on Debian
    if [[ "$id_like" == *"debian"* ]]; then
      INFO "✅ Supported Debian-based distro, your distro is: ${GREEN}$distro${NOFORMAT}"
    else
      FAILED "❌ Unsupported distribution: ${GREEN}$distro${NOFORMAT}, please use Ubuntu or Debian."
    fi
  fi
}

load_env_file() {
  { set -a; } 2>/dev/null
  # shellcheck source=/dev/null
  . "${ENVIRONMENT_FILE:?Environment file not set}"
  { set +a; } 2>/dev/null
}

generate_random_string() {
  local length="$1"
  local RULE="${2:-[:alnum:]}"

  echo "$(
    tr </dev/urandom -dc "$RULE" | head -c ${length}
    true
  )"
}

sudo_timeout() {
  local status
  # https://unix.stackexchange.com/q/692061
  status="$(sudo -n uptime 2>&1 | grep -c "load")"

  return "${status}"
}

_unbound_variable_handler() {
  local var_name="$1"
  local line_number="$2"
  ERROR "Variable ${ORANGE}$var_name${NOFORMAT} is undefined at line ${GREEN}$line_number${NOFORMAT}"
  ERROR "Check your environment file: ${WHITE}$ENVIRONMENT_FILE${NOFORMAT}"
  exit 1
}

detect_docker_socket() {
  local socket
  if [ -S "${XDG_RUNTIME_DIR:-/home/${USER}/.local/share}/docker.sock" ]; then
    socket="${XDG_RUNTIME_DIR:-/home/${USER}/.local/share}/docker.sock"
  elif [ -S "/run/user/$(id -u)/docker.sock" ]; then
    socket="/run/user/$(id -u)/docker.sock"
  elif [ -S "/var/run/docker.sock" ]; then
    socket="/var/run/docker.sock"
  elif [ -S "/run/docker.sock" ]; then
    socket="/run/docker.sock"
  else
    ERROR "Cannot detect docker socket file."
    exit 1
  fi
  echo "$socket"
}
