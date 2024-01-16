#!/usr/bin/env bash

set -euo pipefail

base_dir="$(cd "$(dirname "$0")" && pwd)" # Base directory of this script
PROJECT_DIR="$base_dir"/Lite              # Default project directory
user="$(id -un 2>/dev/null || true)"      # Get current username
SCRIPT_UPGRADE=${SCRIPT_UPGRADE:-false}   # Flag to check if this script is upgrading

rpl_regen_env() {
  if [ ! -f "${PROJECT_DIR}/generate/.env" ]; then
    return
  fi

  rpl_pwd() {
    local show="${2:-false}"
    (
      source "${PROJECT_DIR}/generate/.env"
      local target="$1"
      local value="${!3:-${!1}}"
      variable_write "$target" "$value" $show
    )
  }

  INFO "Generate new version of .env..."
  # Using old .env generate new .env
  variable_write "MODE" "IP"
  rpl_pwd "GITLAB_ROOT_PASSWORD" true
  rpl_pwd "GITLAB_PORT"
  rpl_pwd "SQ_DB_PASSWORD" true
  rpl_pwd "SQ_AM_PASSWORD" true
  rpl_pwd "SQ_PORT"
  rpl_pwd "REDMINE_DB_PASSWORD" true
  rpl_pwd "REDMINE_PORT"
  rpl_pwd "III_DB_PORT"
  rpl_pwd "III_DB_PASSWORD" true
  rpl_pwd "III_PORT"
  rpl_pwd "III_ADMIN_LOGIN"
  rpl_pwd "III_ADMIN_EMAIL"
  rpl_pwd "III_ADMIN_PASSWORD" true
  rpl_pwd "IP_ADDR"
  rpl_pwd "DOCKER_SOCKET"

  rm "${PROJECT_DIR}/generate/.env"
  INFO "Done!"
}

fetch_latest_upgrade_script() {
  if ${SCRIPT_UPGRADE}; then
    return
  fi

  cd "${PROJECT_DIR}" || FAILED "Failed to change directory to ${PROJECT_DIR}"
  local OLD_SCRIPT="${PROJECT_DIR}/scripts/upgrade.sh"
  local UPGRADE_SCRIPT
  UPGRADE_SCRIPT="$(mktemp)"
  INFO "Temp script location: ${WHITE}${UPGRADE_SCRIPT}${NOFORMAT}"

  INFO "Fetching latest upgrade script..."
  wget -q -O ${UPGRADE_SCRIPT} https://raw.githubusercontent.com/iii-org/deploy-devops-lite/master/scripts/upgrade.sh

  INFO "Check if upgrade script is changed..."
  if ! diff -q ${OLD_SCRIPT} ${UPGRADE_SCRIPT} >/dev/null; then
    INFO "${YELLOW}[NEW]${NOFORMAT} Upgrade script is changed!"
    mv ${UPGRADE_SCRIPT} ${OLD_SCRIPT}
    chmod +x ${OLD_SCRIPT}
    SCRIPT_UPGRADE=true ${OLD_SCRIPT} || exit 0
    exit 0
  fi

  INFO "${GREEN}[OK]${NOFORMAT} Upgrade script is up-to-date!"
}

done_script() {
  cd "${PROJECT_DIR}" || FAILED "Failed to change directory to ${PROJECT_DIR}"
  rpl_regen_env

  INFO "Restart docker compose"
  INFO "If you wish to start up your self, you are safe to exit now."
  echo -e "Press \e[96mCtrl+C\e[0m to exit, sleep 5 seconds to continue..."
  sleep 5

  $DOCKER_COMPOSE_COMMAND pull
  $DOCKER_COMPOSE_COMMAND up \
    --detach \
    --remove-orphans

  INFO "Done, sleep 60 seconds to wait for services to start..."
  sleep 60

  INFO "Importing templates..."
  "${PROJECT_DIR}/scripts/template.sh"
}

update_via_git() {
  cd "${PROJECT_DIR}" || FAILED "Failed to change directory to ${PROJECT_DIR}"

  INFO "Updating git remotes..."
  git remote update

  LOCAL=$(git rev-parse @)
  REMOTE=$(git rev-parse '@{u}')

  if [ "$LOCAL" = "$REMOTE" ]; then
    INFO "Already up-to-date"
    exit 0
  fi

  INFO "Pulling latest changes..."
  git pull

  done_script
}

update_via_tar() {
  local temp_dir
  local backup_location
  temp_dir="$(mktemp -d)"
  backup_location="${temp_dir}/original.bak"

  cd "${temp_dir}" || FAILED "Failed to change directory to ${temp_dir}"

  INFO "Backup old files..."
  cp -R "${PROJECT_DIR}" "${backup_location}"

  INFO "Files backup location: ${WHITE}${backup_location}${NOFORMAT}"

  INFO "Downloading latest release..."

  # https://github.com/iii-org/deploy-devops-lite/archive/refs/heads/master.tar.gz
  wget -q -O release.tar.gz https://github.com/iii-org/deploy-devops-lite/archive/refs/heads/master.tar.gz

  INFO "Extracting files..."
  tar -xzf release.tar.gz

  INFO "Removing old files..."
  rm -rf "${PROJECT_DIR}"

  INFO "Copying files..."
  cp -rT deploy-devops-lite-master/ "${PROJECT_DIR}"

  if [[ -d "${backup_location}/generate" ]]; then
    INFO "Copying old generated files..."
    cp -rT "${backup_location}/generate" "${PROJECT_DIR}/generate"
  fi

  INFO "Cleaning up..."
  rm -rf deploy-devops-lite-master
  rm release.tar.gz

  done_script
}

main() {
  if [ -f "${base_dir}/common.sh" ]; then
    # If common.sh exists, we are in the project directory
    source "${base_dir}/common.sh"
  else
    echo "common.sh not found, make sure you are in the project directory."
    exit 1
  fi

  fetch_latest_upgrade_script

  if [ "$user" != "root" ]; then
    INFO "Changing permission of all files to current user (preventing permission issues)"
    INFO "Current user: $user"
    sudo chown -R "$user":"$user" "${PROJECT_DIR}"
  fi

  if [[ -f "${PROJECT_DIR}/HEAD.env" ]]; then
    # Old version, update to generate folder
    INFO "Migrating to new version..."

    cd "${PROJECT_DIR}" || FAILED "Failed to change directory to ${PROJECT_DIR}"
    cd ..

    INFO "Backup old files..."
    # Copy old files to backup folder
    mkdir "${PROJECT_DIR}.bak"
    cp "${PROJECT_DIR}/.env" \
      "${PROJECT_DIR}/HEAD.env" \
      "${PROJECT_DIR}/redis.conf" \
      "${PROJECT_DIR}/redmine-configuration.yml" \
      "${PROJECT_DIR}/redmine.sql" \
      "${PROJECT_DIR}.bak"

    INFO "Remove old files..."
    # Remove old files
    rm -rf "${PROJECT_DIR}"
    mkdir "${PROJECT_DIR}"

    INFO "Copy old files to new folder..."
    # Copy old files to new folder
    mv "${PROJECT_DIR}.bak" "${PROJECT_DIR}/generate"
  fi

  # Check if .git exists
  if [ ! -d "${PROJECT_DIR}"/.git ]; then
    update_via_tar
  else
    update_via_git
  fi
}

# WARNING: This script will **REPLACED** while upgrading, please put any custom script before this line.
main
