#!/usr/bin/env bash

set -euo pipefail

# Load common functions
base_dir="$(cd "$(dirname "$0")" && pwd)"
source "$base_dir"/common.sh

FORCE=false
RUNNING_QUESTIONS=()
ALL_QUESTION=(
  "ip_addr"
  "iii_login"
  "iii_email"
  "iii_password"
)

read_password() {
  local password=""
  # Check if arguments > 0
  if [ $# -eq 1 ]; then
    read -rsp "$1: " password
  else
    read -rsp "Password: " password
  fi
  # Run Command
  echo "$password"
}

usage() {
  echo "Help setting up environment variables."
  echo "If no options are passed, all questions will be run."
  echo
  echo "Usage: $(basename "$0") [options]... [questions]..."
  echo
  echo "Options:"
  echo "  -h,  --help                 print this help"
  echo
  echo "Questions:"
  echo "  all                         run all questions (will ignore other arguments)"
  echo "  ip_addr                     set IP address for the server"
  echo "  docker_sock                 set docker socket file"
  echo "  iii_login                   set III admin account"
  echo "  iii_email                   set III admin email"
  echo "  iii_password                set III admin password"
  exit 21
}

write_back_data() {
  local key="$1"
  local value="$2"
  local value_sensitive="${3:-false}"

  # Check if key is in .env file
  if ! grep -q "$key=" "${env_file:?}"; then
    INFO "$key not found in .env file, adding it"
    echo "$key='$value'" >>"$env_file"
  fi

  # Check if value contains double quote
  if [[ "$value" == *\"* ]]; then
    # From " to \"
    value="${value//\"/\\\\\"}"
  fi

  # If value contain '\$', then escape it
  if [[ "$value" == *\\\$* ]]; then
    # From $ to \$
    value="${value//\$/\\\\\\\\\\$}"
  else
    # Escape backslash
    value="${value//\\/\\\\}"
    # Escape dollar sign
    value="${value//\$/\\\\\$}"
  fi

  # Escape back quote
  value="${value//\`/\\\`}"

  # Write back to .env file, replace the old key, using awk to escape special characters
  awk -v key="$key" -v value="$value" 'BEGIN { FS=OFS="=\"" }
    { for(i=3; i<=NF; i++)
      {
        $2 = $2"=\""$i
      }
    }
    $1 == key {
      $2 = value"\""
    }
    NF {
      if ($1 ~ /^#/) {
        NF = NF
      }
      else {
        NF = 2
      }
    } 1' "$env_file" >"$env_file.tmp"

  if [ "${value_sensitive}" = false ]; then
    INFO "\e[97m$key\e[0m set to \e[97m$value\e[0m"
  else
    INFO "\e[97m$key\e[0m set to \e[97m********\e[0m"
  fi

  # Replace the old file, we don't need the tmp file anymore
  mv "$env_file.tmp" "$env_file"
}

question_ip_addr() {
  local IPv4_format="^(([1-9]?[0-9]|1[0-9][0-9]|2([0-4][0-9]|5[0-5]))\.){3}([1-9]?[0-9]|1[0-9][0-9]|2([0-4][0-9]|5[0-5]))$"
  local valid=false

  # Check if IP_ADDR is set
  if [ -z "${IP_ADDR:-}" ]; then
    valid=false
  else
    if [ "$FORCE" = true ]; then
      valid=false
    elif [[ "$IP_ADDR" =~ $IPv4_format ]]; then
      valid=true
      INFO "\e[97mIP address\e[0m already set to \e[97m$IP_ADDR\e[0m"
      return
    else
      valid=false
      WARN "Current ip \e[97m$IP_ADDR\e[0m is invalid, please enter a valid IP address"
    fi
  fi

  # Prompt question
  if [ "$valid" = false ]; then
    INFO "Getting IP address for the server"
  fi

  while ! $valid; do
    read -r ip
    if [[ "$ip" =~ $IPv4_format ]]; then
      valid=true
    else
      WARN "Invalid IP address, should be an IPv4 address format"
    fi
  done

  write_back_data "IP_ADDR" "$ip"
}

question_docker_sock() {
  local valid=false
  local answer

  # Check if DOCKER_SOCKET is set
  if [ -z "${DOCKER_SOCKET:-}" ]; then
    valid=false
  else
    if [ "$FORCE" = true ]; then
      valid=false
    else
      valid=true
      INFO "\e[97mDocker socket\e[0m already set to \e[97m$DOCKER_SOCKET\e[0m"
      return
    fi
  fi

  # Prompt question
  if [ "$valid" = false ]; then
    INFO "Setting docker socket file, it will auto detect if not set"
  fi

  while ! $valid; do
    # Trying to auto detect docker socket
    if [ "$valid" = false ]; then
      if [ -S "$XDG_RUNTIME_DIR/docker.sock" ]; then
        INFO "Found docker socket at \e[97m$XDG_RUNTIME_DIR/docker.sock\e[0m"
        answer="$XDG_RUNTIME_DIR/docker.sock"
        valid=true
        break
      fi
      if [ -S "/run/user/$(id -u)/docker.sock" ]; then
        INFO "Found docker socket at \e[97m/run/user/$(id -u)/docker.sock\e[0m"
        answer="/run/user/$(id -u)/docker.sock"
        valid=true
        break
      fi
      if [ -S "/var/run/docker.sock" ]; then
        INFO "Found docker socket at \e[97m/var/run/docker.sock\e[0m"
        answer="/var/run/docker.sock"
        valid=true
        break
      fi
    fi

    # If not found, prompt user to enter
    WARN "Docker socket not found, please enter the docker socket file manually"
    read -r answer
    if [ -S "$answer" ]; then
      valid=true
    else
      WARN "Invalid docker socket, should be a socket file"
    fi
  done

  write_back_data "DOCKER_SOCKET" "$answer"
}

question_iii_login() {
  local rule="^[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,58}[a-zA-Z0-9]$"
  local valid=false
  local answer

  if [ -z "${III_ADMIN_LOGIN:-}" ]; then
    valid=false
  else
    if [ "$FORCE" = true ]; then
      valid=false
    else
      if [[ "$III_ADMIN_LOGIN" =~ $rule ]]; then
        valid=true
        INFO "\e[97mIII init login account\e[0m already set to \e[97m$III_ADMIN_LOGIN\e[0m"
        return
      else
        valid=false
        WARN "Current III init login account \e[97m$III_ADMIN_LOGIN\e[0m is invalid, please enter a valid III init login account"
      fi
    fi
  fi

  if [ "$valid" = false ]; then
    INFO "Setting III init login account"
  fi

  while ! $valid; do
    read -r answer
    if [[ "$answer" =~ $rule ]]; then
      valid=true
    else
      WARN "Invalid III init login account, should only contain alphanumeric characters, underscores, periods, and dashes, and should not start or end with a period or dash"
    fi
  done

  write_back_data "III_ADMIN_LOGIN" "$answer"
}

question_iii_email() {
  local rule=""
  rule+="^[a-zA-Z0-9!#$%&'*+/=?^_\`{|}~-]+(\.[a-zA-Z0-9!#$%&'*+/=?^_\`{|}~-]+)*"
  rule+="@"
  rule+="[a-zA-Z0-9]([a-zA-Z0-9.-]?[a-zA-Z0-9])*\.[a-zA-Z]{2,}$"
  local valid=false
  local answer

  if [ -z "${III_ADMIN_EMAIL:-}" ]; then
    valid=false
  else
    if [ "$FORCE" = true ]; then
      valid=false
    else
      if [[ "$III_ADMIN_EMAIL" =~ $rule ]]; then
        valid=true
        INFO "\e[97mIII init login email\e[0m already set to \e[97m$III_ADMIN_EMAIL\e[0m"
        return
      else
        valid=false
        WARN "Current III init login email \e[97m$III_ADMIN_EMAIL\e[0m is invalid, please enter a valid III init login email"
      fi
    fi
  fi

  if [ "$valid" = false ]; then
    INFO "Setting III init login email"
  fi

  while ! $valid; do
    read -r answer
    if [[ "$answer" =~ $rule ]]; then
      valid=true
    else
      WARN "Invalid III init login email, should be a valid email address"
    fi
  done

  write_back_data "III_ADMIN_EMAIL" "$answer"
}

check_password() {
  local valid=false
  local answer="$1"

  if [ -z "$answer" ] || [ "$answer" = "{{PASSWORD}}" ] || [ "${#answer}" -lt 8 ] || [ "${#answer}" -gt 20 ]; then
    valid=false
  else
    if [[ "$answer" =~ [[:lower:]] && "$answer" =~ [[:upper:]] && "$answer" =~ [[:digit:]] && "$answer" =~ [[:punct:]] ]]; then
      valid=true
    else
      valid=false
    fi
  fi

  echo "$valid"
}

test_password() {
  local valid=false
  local answer
  local key="$1"
  local value="$2"

  if [ -z "$value" ]; then
    valid=false
  else
    if [ "$FORCE" = true ]; then
      valid=false
    else
      if [ "$value" = "{{PASSWORD}}" ]; then
        valid=false
      else
        if [ "$(check_password "$value")" = true ]; then
          valid=true
          INFO "Password \e[97m$key\e[0m already meat the requirement"
          return
        else
          valid=false
          WARN "Current password \e[97m$key\e[0m is invalid, please enter a valid password"
        fi
      fi
    fi
  fi

  if [ "$valid" = false ]; then
    INFO "Setting password \e[97m$key\e[0m"
  fi

  while ! $valid; do
    answer="$(read_password "$key")"
    echo
    if [ "$(check_password "$answer")" = true ]; then
      valid=true
    else
      WARN "Invalid password, should be 8-20 characters long and contain at least one lowercase letter, one uppercase letter, one number, and one special character"
    fi
  done

  write_back_data "$key" "$answer" true
}

question_iii_password() {
  local password_list=(
    "GITLAB_ROOT_PASSWORD"
    "SQ_AM_PASSWORD"
    "SQ_DB_PASSWORD"
    "REDMINE_DB_PASSWORD"
    "III_DB_PASSWORD"
  )
  test_password "III_ADMIN_PASSWORD" "$III_ADMIN_PASSWORD"

  # Load .env file
  set -a
  # shellcheck source=/dev/null
  . "$env_file"
  set +a

  if [ -z "${III_ADMIN_PASSWORD:-}" ]; then
    WARN "III init login password is empty, please set III init login password"
    exit 1
  fi

  for password in "${password_list[@]}"; do
    if [ -z "${!password:-}" ] || [ "${!password}" == "{{PASSWORD}}" ] || [ "${!password}" != "$III_ADMIN_PASSWORD" ]; then
      write_back_data "$password" "$III_ADMIN_PASSWORD" true
    fi
  done
}

if [ $# -eq 0 ]; then
  usage
fi

# If set_env has arguments, run the question function and exit
while [[ "$#" -gt 0 ]]; do
  case $1 in
  -h | --help) usage ;;
  -f | --force)
    FORCE=true
    ;;
  all)
    RUNNING_QUESTIONS=("${ALL_QUESTION[@]}")
    break
    ;;
  *) RUNNING_QUESTIONS+=("$1") ;;
  esac
  shift
done

# Backup .env file
cp "$env_file" "$env_file.bak"
INFO "Backup \e[97m$env_file\e[0m file to \e[97m$env_file.bak\e[0m"

# For each question, run the function
for question in "${RUNNING_QUESTIONS[@]}"; do
  question_"$question"
done
