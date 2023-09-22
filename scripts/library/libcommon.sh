#!/usr/bin/env bash

msg() {
  echo >&2 -e "${1-}"
}

INFO() {
  msg "${GREEN}[INFO]${NOFORMAT} ${1}"
}

NOTICE() {
  msg "${CYAN}[NOTICE]${NOFORMAT} ${1}"
}

WARN() {
  msg "${ORANGE}[WARN]${NOFORMAT} ${1}"
}

ERROR() {
  msg "${RED}[ERROR]${NOFORMAT} ${1}" >&2
}

FAILED() {
  local msg=$1
  local code=${2-1} # default exit status 1
  msg "${RED}[FAILED]${NOFORMAT} ${msg}"
  exit "$code"
}

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

check_runas_root() {
  if [ "$(id -u)" == "0" ]; then
    ERROR "Please run this script as normal user, not root."
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
  echo "$(
    tr </dev/urandom -dc '[:alnum:]' | head -c ${length}
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

debug_disable() {
  # Disable output to debug message
  {
    if $DEBUG; then
      set +x
    fi
  } 2>/dev/null
}

debug_enable() {
  # Enable output to debug message
  {
    if $DEBUG; then
      set -x
    fi
  } 2>/dev/null
}
