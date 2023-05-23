#!/usr/bin/env bash
# shellcheck disable=SC1090

set -euo pipefail

sourced=false
(return 0 2>/dev/null) && sourced=true || sourced=false

if ! ${sourced}; then
  base_dir="$(cd -P -- "$(dirname -- "$0")" && pwd -P)"
  source "$base_dir"/common.sh
fi

env_file="${project_dir:?}"/.env
FORCE=false
QUESTIONS=()
ALL_SETS=(
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
  local _text_
  read -r -d '' _text_ <<EOF || true
Usage: $(basename "${0}") [options]... [questions]...
Help setting up environment variables.
If no options are passed, all questions will be run.

Questions:
  all                       run all questions (will ignore other arguments)
  ip                        set IP address for the server
  docker_sock               set docker socket file
  iii_login                 set III admin account
  iii_email                 set III admin email
  iii_password              set III admin password

Miscellaneous:
  -h, --help                display this help text and exit
      --disable-color       disable color output
  -f, --force               force reset the question
EOF
  echo "$_text_"
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

  # Due to GitLab password policy, password should not contain common passwords
  # https://docs.gitlab.com/ee/user/profile/user_passwords.html#block-weak-passwords
  # Password checking rule: https://gitlab.com/gitlab-org/gitlab/-/blob/master/config/weak_password_digests.yml#L15-27
  local common_word_check
  common_word_check=(
    "devops"
    "gitlab"
    "@" # not allowed cause it will use to connect database
  )

  if [ -z "$answer" ] || [ "$answer" = "{{PASSWORD}}" ] || [ "${#answer}" -lt 8 ] || [ "${#answer}" -gt 20 ]; then
    valid=false
  else
    if [[ "$answer" =~ [[:lower:]] && "$answer" =~ [[:upper:]] && "$answer" =~ [[:digit:]] && "$answer" =~ [[:punct:]] ]]; then
      valid=true
    fi
  fi

  for word in "${common_word_check[@]}"; do
    # copy answer to lowercase
    answer2="${answer,,}"
    if [[ "${answer2}" =~ ${word} ]]; then
      valid=false
    fi
  done

  # Check if password sha is in common password list
  # Put in the last to reduce the number of sha256sum calculation
  if ${valid}; then
    answer2="$(echo "${answer,,}" | sha256sum | awk '{ print $1 }')"
    # check if password is in common password list
    while IFS= read -r weak_password; do
      if [[ "${answer2}" == "${weak_password}" ]]; then
        valid=false
      fi
    done <<<"$(cat "${bin_dir:?}/common_password.txt")"
  fi

  if ${valid}; then
    return 0
  fi
  return 1
}

test_password() {
  local valid=false
  local answer
  local key="$1"
  local value="$2"

  if [ -n "${value}" ]; then
    if [ "$value" != "{{PASSWORD}}" ]; then
      if check_password "$value"; then
        valid=true
      fi
    fi
  fi

  if ${FORCE}; then
    valid=false
    WARN "Due to \e[1;97m--force\e[0m, ${key} will be reset"
  fi

  if ${valid}; then
    INFO "Password \e[97m$key\e[0m already meat the requirement"
    return 0
  fi

  INFO "Setting password \e[97m$key\e[0m"

  while ! $valid; do
    answer1="$(read_password "$key")"
    echo
    answer2="$(read_password "Confirm password")"
    echo
    if [ "${answer1}" = "${answer2}" ]; then
      if check_password "${answer1}"; then
        valid=true
      else
        WARN "Invalid password, should be 8-20 characters long and contain at least one lowercase letter, one uppercase letter, one number, and one special character"
        WARN "DO NOT contain these words: 'devops', 'gitlab' (case-insensitive)"
        WARN "See: https://docs.gitlab.com/ee/user/profile/user_passwords.html#block-weak-passwords"
      fi
    else
      WARN "Passwords do not match, please try again"
    fi
  done

  write_back_data "$key" "${answer1}" true
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
    QUESTIONS=("${ALL_SETS[@]}")
    break
    ;;
  *) QUESTIONS+=("$1") ;;
  esac
  shift
done

# Backup .env file
cp "$env_file" "$env_file.bak"
INFO "Backup \e[97m$env_file\e[0m file to \e[97m$env_file.bak\e[0m"

# For each question, run the function
for question in "${QUESTIONS[@]}"; do
  question_"$question"
done
