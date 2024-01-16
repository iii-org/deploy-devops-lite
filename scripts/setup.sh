#!/usr/bin/env bash

set -euo pipefail

# Load common functions
base_dir="$(cd "$(dirname "$0")" && pwd)"
source "$base_dir"/common.sh
source "$base_dir"/library/ascii.sh

COMMAND_CHECK_FLAG="$base_dir"/.checked

usage() {
  cat <<EOF
Usage: $(basename "${BASH_SOURCE[0]}") [OPTION]...

Install III DevOps Community version.

Miscellaneous:
  -h, --help                Print this help and exit
EOF
  exit 21
}

parse_params() {
  while :; do
    case "${1-}" in
    -h | --help) usage ;;
    -?*) FAILED "Unknown option: $1" ;;
    *) break ;;
    esac
    shift
  done
}

command_check() {
  if [[ -f $COMMAND_CHECK_FLAG ]]; then
    INFO "✅ Commands already checked!"
    INFO "💡 To re-run the commands check, remove file:"
    INFO "   ${WHITE}${COMMAND_CHECK_FLAG}${NOFORMAT}"
    return
  fi

  install_command() {
    local command=${1:?}

    if ! command_exists "$command"; then
      INFO "Installing ${WHITE}$command${NOFORMAT}..."
      sudo apt-get update -qq >/dev/null
      sudo apt-get install -y -qq "$command" >/dev/null
      INFO "Installed ${WHITE}$command${NOFORMAT} finished!"
    fi
  }

  if sudo_timeout; then
    INFO "ℹ️ You may need to enter your password to install some packages."
    sudo -v
  fi

  install_command "git"
  install_command "curl"
  install_command "jq"

  if ! command_exists docker; then
    INFO "Install docker rootless base on https://get.docker.com/"
    "$BINARY_DIR"/install_docker.sh
  fi

  touch "$COMMAND_CHECK_FLAG"
  INFO "✅ Commands check finished!"
}

env_validate() {
  "${BINARY_DIR:?"$(_unbound_variable_handler BINARY_DIR $LINENO)"}"/generate-env.sh all
  load_env_file
}

env_exist_check() {
  if [[ -e $III_ENV ]]; then
    INFO "❗ ${YELLOW}Detected existing environment file!${NOFORMAT}"
    if [[ -s $III_ENV ]]; then
      INFO "⏭️ Environment file is not empty, skip generating..."
      NOTICE "💡 If you wish to ${RED}re-install${NOFORMAT} ${WHITE}III DevOps Community${NOFORMAT}, run:"
      NOTICE "   ${WHITE}$PROJECT_DIR/run.sh clean && $PROJECT_DIR/run.sh${NOFORMAT}"
      INFO "🛑 Stopping setup..."
      exit 0
    else
      INFO "Environment file is empty, continue installing..."
    fi
  fi
}

docker_running_check() {
  # Get current docker compose how many service is created or running
  local containers_count
  containers_count="$($DOCKER_COMPOSE_COMMAND ps -aq | wc -l)"
  if [[ "$containers_count" -gt 0 ]]; then
    INFO "❗ ${YELLOW}Detected existing containers!${NOFORMAT}"
    INFO "❗ If you wish to ${RED}re-install${NOFORMAT} ${WHITE}III DevOps Community${NOFORMAT}, run:"
    INFO "   ${WHITE}$DOCKER_COMPOSE_COMMAND down -v && $PROJECT_DIR/setup.sh${NOFORMAT}"
    INFO "🛑 Stopping setup..."
    exit 0
  fi
}

sonarqube_requirement_check() {
  INFO "🔍 Checking SonarQube requirements..."

  if sudo_timeout; then
    INFO "ℹ️ We need sudo permission to check some requirements."
    sudo -v
  fi

  # Check vm.max_map_count is greater than or equal to 524288
  if [ "$(sudo sysctl -n vm.max_map_count)" -lt 524288 ]; then
    INFO "vm.max_map_count is less than 524288"
    INFO "Executing command to set vm.max_map_count up to 524288..."
    sudo sysctl -w vm.max_map_count=524288

    INFO "Persisting vm.max_map_count to ${WHITE}/etc/sysctl.d/99-sonarqube.conf${NOFORMAT}"
    echo "vm.max_map_count=524288" | sudo tee -a /etc/sysctl.d/99-sonarqube.conf
  fi

  # Check fs.file-max is greater than or equal to 131072
  if [ "$(sudo sysctl -n fs.file-max)" -lt 131072 ]; then
    INFO "fs.file-max is less than 131072"
    INFO "Executing command to set fs.file-max up to 131072..."
    sudo sysctl -w fs.file-max=131072

    INFO "Persisting fs.file-max to ${WHITE}/etc/sysctl.d/99-sonarqube.conf${NOFORMAT}"
    echo "fs.file-max=131072" | sudo tee -a /etc/sysctl.d/99-sonarqube.conf
  fi

  # Check at least 131072 file descriptors are available
  if [ "$(ulimit -n)" -lt 131072 ]; then
    INFO "ulimit -n is less than 131072"
    INFO "Executing command to set ulimit -n up to 131072..."
    ulimit -n 131072
  fi

  # Check at least 8192 threads are available
  if [ "$(ulimit -u)" -lt 8192 ]; then
    INFO "ulimit -u is less than 8192"
    INFO "Executing command to set ulimit -u up to 8192..."
    ulimit -u 8192
  fi

  INFO "✅ SonarQube requirements check finished!"
}

redis_requirement_check() {
  INFO "🔍 Checking Redis requirements..."

  if sudo_timeout; then
    INFO "ℹ️ We need sudo permission to check some requirements."
    sudo -v
  fi

  # Check vm.overcommit_memory is enabled
  if [ "$(sudo sysctl -n vm.overcommit_memory)" -ne 1 ]; then
    INFO "vm.overcommit_memory is enabled"
    INFO "Executing command to set vm.overcommit_memory to 1..."
    sudo sysctl -w vm.overcommit_memory=1

    INFO "Persisting vm.overcommit_memory to ${WHITE}/etc/sysctl.d/99-redis.conf${NOFORMAT}"
    echo "vm.overcommit_memory=1" | sudo tee -a /etc/sysctl.d/99-redis.conf
  fi

  INFO "✅ Redis requirements check finished!"
}

requirements_check() {
  INFO "$(title_center "REQUIREMENTS CHECK")"
  sonarqube_requirement_check
  redis_requirement_check

  INFO "📄 Copying sample files..."

  mkdir -p "$PROJECT_DIR"/generate

  # Copy static files
  if [[ ! -f "$PROJECT_DIR"/generateredis.conf ]]; then
    cp "$PROJECT_DIR"/sample/redis.conf "$PROJECT_DIR"/generate
  fi

  if [[ ! -f "$PROJECT_DIR"/generate/redmine-configuration.yml ]]; then
    cp "$PROJECT_DIR"/sample/redmine-configuration.yml "$PROJECT_DIR"/generate
  fi

  cp "$PROJECT_DIR"/sample/redmine.sql.template "$PROJECT_DIR"/generate/redmine.sql
  touch "$III_ENV"

  INFO "✅ Sample files copied!"

  INFO "🔄 Generating Redmine SQL file..."

  local SALT HASHED_DBPWD HASHED_PWD API_KEY AUTHORITY
  SALT="$(echo -n "$REDMINE_DB_PASSWORD" | md5sum | awk '{print $1}')"
  HASHED_DBPWD="$(echo -n "$REDMINE_DB_PASSWORD" | sha1sum | awk '{print $1}')"
  HASHED_PWD="$(echo -n "$SALT$HASHED_DBPWD" | sha1sum | awk '{print $1}')"
  API_KEY="$(
    tr </dev/urandom -dc 'a-f0-9' | head -c 20
    echo
  )"

  AUTHORITY="$(get_service_authority "redmine")"

  sed -i "s|{{hashed_password}}|$HASHED_PWD|g" "$PROJECT_DIR"/generate/redmine.sql
  sed -i "s|{{salt}}|$SALT|g" "$PROJECT_DIR"/generate/redmine.sql
  sed -i "s|{{api_key}}|$API_KEY|g" "$PROJECT_DIR"/generate/redmine.sql
  sed -i "s|{{devops_domain_name}}|$AUTHORITY|g" "$PROJECT_DIR"/generate/redmine.sql

  chmod 644 "$PROJECT_DIR"/generate/redmine.sql

  INFO "🔑 Redmine API key: ${ORANGE}$API_KEY${NOFORMAT}"
  variable_write "REDMINE_API_KEY" "$API_KEY"
  INFO "🔄 Generating Redmine SQL file finished!"

  INFO "========================================"
}

start_services() {
  INFO "🚀 Starting services..."

  $DOCKER_COMPOSE_COMMAND up \
    --detach \
    --no-deps \
    --remove-orphans

  INFO "🌟 Services started!"
}

gen_API_env() {
  INFO "🔄 Generating HEAD.env file..."

  JWT_SECRET_KEY="$(generate_random_string 20 'a-f0-9')"

  # Using heredoc to generate HEAD.env
  cat <<EOF >"$III_ENV"
GITLAB_PRIVATE_TOKEN=$GITLAB_INIT_TOKEN
JWT_SECRET_KEY=$JWT_SECRET_KEY
REDMINE_API_KEY=$REDMINE_API_KEY
SONARQUBE_ADMIN_TOKEN=$SONARQUBE_ADMIN_TOKEN
EOF

  INFO "✅ HEAD.env generated!"
}

after_script() {
  full_sep
  INFO "🎉 ${WHITE}III DevOps Community${NOFORMAT} is ready!"
  INFO "🎉 You can now visit ${WHITE}$(get_service_url "ui")${NOFORMAT} to start using it!"
  INFO "GitLab: ${WHITE}$(get_service_url "gitlab")${NOFORMAT}"
  INFO "Redmine: ${WHITE}$(get_service_url "redmine")${NOFORMAT}"
  INFO "SonarQube: ${WHITE}$(get_service_url "sonarqube")${NOFORMAT}"
}

main() {
  parse_params "$@"

  banner

  check_runas_root
  check_distro
  command_check
  env_validate
  docker_get_version
  docker_print_info
  env_exist_check
  docker_permission_check
  docker_running_check
  requirements_check
  start_services
  setup_sonarqube
  setup_redmine
  setup_gitlab
  gen_API_env
  after_script
}

main "$@"
