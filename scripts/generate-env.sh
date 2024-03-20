#!/usr/bin/env bash

set -euo pipefail

# Load common functions
base_dir="$(cd "$(dirname "$0")" && pwd)"
source "$base_dir"/common.sh

usage() {
  cat <<EOF
Checking and setting up environment variables.

Usage: $(basename "$0") [options]...

Options:
  -h,  --help                 print this help
EOF
  exit 0
}

port_validator() {
  local port="$1"
  if [[ "$port" =~ ^[0-9]+$ ]]; then
    if [[ "$port" -lt 1 || "$port" -gt 65535 ]]; then
      WARN "Port number must be between 1 and 65535."
      return 1
    fi
  else
    WARN "Port number must be a number."
    return 1
  fi
}

password_validator() {
  local password="$1"
  # If password is equal to '{{PASSWORD}}', then it's not set
  if [[ "$password" = '{{PASSWORD}}' ]]; then
    WARN "Password is not set."
    return 1
  fi

  if [[ ${#password} -lt 8 ]]; then
    WARN "Password must be at least 8 characters."
    return 1
  fi

  if [[ "${#password}" -gt 20 ]]; then
    WARN "Password must be less than 20 characters."
    return 1
  fi

  if [[ "$password" =~ [[:lower:]] && "$password" =~ [[:upper:]] && "$password" =~ [[:digit:]] && "$password" =~ [[:punct:]] ]]; then
    return 0
  else
    WARN "Password must contain at least one uppercase letter, one lowercase letter, one number, and one special character."
    return 1
  fi

  password=$(echo "$password" | tr '[:upper:]' '[:lower:]')

  local hashed_pwd
  hashed_pwd=$(echo -n "$password" | sha256sum | cut -d ' ' -f 1)

  if grep -q "^$hashed_pwd$" $base_dir/digests/digests_*; then
    WARN "You are using a weak password. Please try another one."
    return 1
  else
    return 0
  fi
}

account_validator() {
  local string="$1"
  if [[ ${#string} -lt 2 ]]; then
    WARN "Account must be at least 2 characters."
    return 1
  fi
  if [[ ${#string} -gt 32 ]]; then
    WARN "Account must be less than 32 characters."
    return 1
  fi
  if [[ "$string" = "admin" ]]; then
    WARN "Account name is not allowed to be admin."
    return 1
  fi
  # Account should only allow alphanumeric characters and underscore
  if [[ ! "$string" =~ ^[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,30}[a-zA-Z0-9]$ ]]; then
    WARN "Account must only contain alphanumeric characters and underscore."
    WARN " (rule: ^[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,30}[a-zA-Z0-9]$)"
    return 1
  fi
}

option_validator() {
  local option="$1"
  shift
  local options=("$@")
  for o in "${options[@]}"; do
    if [[ "${o}" == "${option}" ]]; then
      return 0
    fi
  done
  WARN "Invalid option. Must be one of: ${WHITE}${options[*]}${NOFORMAT}"
  return 1
}

ip_validator() {
  local ip="$1"
  if [[ "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    local IFS='.'
    # shellcheck disable=SC2206
    local -a a=($ip)
    if [[ ${#a[@]} -ne 4 ]]; then
      WARN "IP address must be in the form of x.x.x.x"
      return 1
    fi
    for i in "${a[@]}"; do
      if [[ "$i" -lt 0 || "$i" -gt 255 ]]; then
        WARN "Maximum value of each octet is 255"
        return 1
      fi
    done
  else
    WARN "IP address must be in the form of x.x.x.x"
    return 1
  fi
}

email_validator() {
  local email="$1"
  if [[ "$email" =~ ^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$ ]]; then
    return 0
  else
    WARN "Email address is not valid."
    return 1
  fi
}

socket_validator() {
  local socket="$1"
  if [[ ! -S "$socket" ]]; then
    WARN "Socket file does not exist."
    return 1
  fi
}

ask_port() {
  local port_name="$1"
  local default_port="$2"
  local port

  while true; do
    echo -n "Please enter ${port_name} port [${default_port}]: "

    read -r port

    if [[ -z "$port" ]]; then
      port="$default_port"
    fi
    if port_validator "$port"; then
      break
    fi
  done

  ANSWER="$port"
  export ANSWER
}

ask_password() {
  local password_name="$1"
  local result
  local check

  while true; do
    echo -n "Please enter ${password_name}: "
    read -rs result
    echo 1>&2

    echo -n "Please enter password again: "
    read -rs check
    echo 1>&2

    if [[ "$result" != "$check" ]]; then
      ERROR "Password does not match, please try again."
      continue
    fi

    if password_validator "$result"; then
      break
    fi
  done

  ANSWER="$result"
  export ANSWER
}

ask_account() {
  local string_name="$1"
  local default_string="$2"
  local string

  while true; do
    echo -n "Please enter ${string_name} [${default_string}]: "

    read -r string

    if [[ -z "$string" ]]; then
      string="$default_string"
    fi
    if account_validator "$string"; then
      break
    fi
  done

  ANSWER="$string"
  export ANSWER
}

ask_ip() {
  local ip_name="$1"
  local default_ip="$2"
  local ip

  while true; do
    echo -n "Please enter ${ip_name} [${default_ip}]: "

    read -r ip

    if [[ -z "$ip" ]]; then
      ip="$default_ip"
    fi
    if ip_validator "$ip"; then
      break
    fi
  done

  ANSWER="$ip"
  export ANSWER
}

ask_email() {
  local email_name="$1"
  local email

  while true; do
    echo -n "Please enter ${email_name}: "

    read -r email

    if email_validator "$email"; then
      break
    fi
  done

  ANSWER="$email"
  export ANSWER
}

ask_option() {
  local option_name="$1"
  local options=("${!2}")
  local default_option="${3:-${options[0]}}" # default to first
  local option
  local index

  DEBUG "Option name: $option_name"
  DEBUG "Options: ${options[*]}"
  DEBUG "Default option: $default_option"

  while true; do
    index=1
    INFO "Please select ${option_name}:"
    for o in "${options[@]}"; do
      echo " ${index}) ${o}"
      index=$((index + 1))
    done

    echo -n "Please enter ${option_name} [${default_option}]: "

    read -r option

    DEBUG "Select option: $option"

    if [[ -z "$option" ]]; then
      option="$default_option"
    fi
    if [ "$option" -eq "$option" ] 2>/dev/null; then # check if it's an integer
      if [[ "$option" -ge 1 ]] && [[ "$option" -le ${#options[@]} ]]; then
        option=${options[$((option - 1))]} # translate index to option
      else
        WARN "Invalid index. Please try again."
        continue
      fi
    fi
    if option_validator "$option" "${options[@]}"; then
      break
    fi
  done
  ANSWER="$option"
  export ANSWER
}

get_answer() {
  echo "${ANSWER:-}"
}

sync_passwords() {
  local password_list=(
    "SQ_AM_PASSWORD"
    "GITLAB_ROOT_PASSWORD"
  )

  for password in "${password_list[@]}"; do
    # If password is not equal to III_ADMIN_PASSWORD, then write it
    if [[ "${!password:-}" != "$III_ADMIN_PASSWORD" ]]; then
      variable_write "$password" "${III_ADMIN_PASSWORD:-}" true
    fi
  done

  INFO "✅ Passwords sync finished!"
  INFO "🔄 Generating random db passwords..."

  local random_list=(
    "SQ_DB_PASSWORD"
    "III_DB_PASSWORD"
    "REDMINE_DB_PASSWORD"
  )

  for password in "${random_list[@]}"; do
    if [[ "${!password:-}" = '' ]] || [[ "${!password:-}" = '{{PASSWORD}}' ]]; then
      variable_write "$password" "$(generate_random_string 32)" true
    fi
  done
}

check_env() {
  local options=("IP" "DNS")
  if [[ -z "${MODE:-}" ]]; then
    INFO "ℹ️ It seems that you are running ${WHITE}III DevOps Community${NOFORMAT} for the first time."
    INFO "💡 If you change the mode in the future."
    INFO "   ${RED}Re-install${NOFORMAT} ${WHITE}III DevOps Community${NOFORMAT} to avoid unexpected errors."

    # TODO: check if DNS mode are ready
    #    INFO "💡 If you are not sure, please choose ${WHITE}IP${NOFORMAT} mode."
    #    ask_option "network mode" options[@] "${options[0]}"
    #    MODE="$(get_answer)"

    MODE="IP"
    variable_write "MODE" "$MODE"
  else
    if ! option_validator "$MODE" "${options[@]}"; then

      # TODO: check if DNS mode are ready
      #    ask_option "network mode" options[@] "${options[0]}"
      #    MODE="$(get_answer)"

      MODE="IP"
      variable_write "MODE" "$MODE"
    fi
  fi

  # TODO: If DNS mode, ask domain name and certificate path / certificate method

  _ip_f() {
    ask_ip "IP address" "$(ip -o route get to 8.8.8.8 | sed -n 's/.*src \([0-9.]\+\).*/\1/p')"
    IP_ADDR="$(get_answer)"
    variable_write "IP_ADDR" "$IP_ADDR"
  }

  if [[ -z "${IP_ADDR:-}" ]]; then
    _ip_f
  else
    if ! ip_validator "$IP_ADDR"; then
      _ip_f
    fi
  fi

  _dir_f() {
    BASE_DIR="${PROJECT_DIR:?}"
    variable_write "BASE_DIR" "$BASE_DIR"
  }

  # Files
  if [[ -z "${BASE_DIR:-}" ]]; then
    _dir_f
  else
    if [[ "${BASE_DIR}" != "${PROJECT_DIR:?}" ]]; then
      _dir_f
    fi
  fi

  _docker_f() {
    DOCKER_SOCKET="$(detect_docker_socket)"
    variable_write "DOCKER_SOCKET" "$DOCKER_SOCKET"
  }

  if [[ -z "${DOCKER_SOCKET:-}" ]]; then
    _docker_f
  else
    if ! socket_validator "$DOCKER_SOCKET"; then
      _docker_f
    fi
  fi

  _login_f() {
    ask_account "III init login account" "sysadmin"
    III_ADMIN_LOGIN="$(get_answer)"
    variable_write "III_ADMIN_LOGIN" "$III_ADMIN_LOGIN"
  }

  if [[ -z "${III_ADMIN_LOGIN:-}" ]]; then
    _login_f
  else
    if ! account_validator "$III_ADMIN_LOGIN"; then
      _login_f
    fi
  fi

  _email_f() {
    ask_email "III init login email"
    III_ADMIN_EMAIL="$(get_answer)"
    variable_write "III_ADMIN_EMAIL" "$III_ADMIN_EMAIL"
  }

  if [[ -z "${III_ADMIN_EMAIL:-}" ]]; then
    _email_f
  else
    if ! email_validator "$III_ADMIN_EMAIL"; then
      _email_f
    fi
  fi

  _pwd_f() {
    ask_password "III init login password"
    III_ADMIN_PASSWORD="$(get_answer)"
    variable_write "III_ADMIN_PASSWORD" "$III_ADMIN_PASSWORD" true
  }

  if [[ -z "${III_ADMIN_PASSWORD:-}" ]]; then
    _pwd_f
  else
    if ! password_validator "$III_ADMIN_PASSWORD"; then
      _pwd_f
    fi
  fi

  sync_passwords

  INFO "✅ Environment variables check finished!"
}

if [[ "$#" -eq 0 ]]; then
  usage
fi

# If set_env has arguments, run the question function and exit
while [[ "$#" -gt 0 ]]; do
  case $1 in
  -h | --help) usage ;;
  all) ;;
  *)
    FAILED "Invalid argument: $1"
    ;;
  esac
  shift
done

check_env
