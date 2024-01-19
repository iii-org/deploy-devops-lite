#!/usr/bin/env bash

set -euo pipefail

base_dir="$(cd "$(dirname "$0")" && pwd)" # Base directory of this script
PROJECT_DIR="$base_dir/IIIDevOps"         # Default project directory
user="$(id -un 2>/dev/null || true)"      # Get current username
SCRIPT_UPGRADE=${SCRIPT_UPGRADE:-false}   # Flag to check if this script is upgrading
BRANCH="${BRANCH:-master}"                # Default branch to upgrade

usage() {
  cat <<EOF
Usage: $(basename "${BASH_SOURCE[0]}") [OPTION]...

Basic upgrade script for III DevOps Community version.

Options:
  -h, --help  Print this help and exit
  --branch    Upgrade to specific branch
EOF
  exit 21
}

migrate_old_generated() {
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
}

migrate_old_env() {
  if [ ! -f "${PROJECT_DIR}/generate/.env" ]; then
    return
  fi

  rpl_rw() {
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
  rpl_rw "GITLAB_ROOT_PASSWORD" true
  rpl_rw "GITLAB_PORT"
  rpl_rw "SQ_DB_PASSWORD" true
  rpl_rw "SQ_AM_PASSWORD" true
  rpl_rw "SQ_PORT"
  rpl_rw "REDMINE_DB_PASSWORD" true
  rpl_rw "REDMINE_PORT"
  rpl_rw "III_DB_PORT"
  rpl_rw "III_DB_PASSWORD" true
  rpl_rw "III_PORT"
  rpl_rw "III_ADMIN_LOGIN"
  rpl_rw "III_ADMIN_EMAIL"
  rpl_rw "III_ADMIN_PASSWORD" true
  rpl_rw "IP_ADDR"
  rpl_rw "DOCKER_SOCKET"

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

  INFO "Fetching latest upgrade script from ${WHITE}${BRANCH}${NOFORMAT} branch..."
  wget -q -O ${UPGRADE_SCRIPT} "https://raw.githubusercontent.com/iii-org/deploy-devops-lite/${BRANCH}/scripts/upgrade.sh"

  INFO "Check if upgrade script is changed..."
  if ! diff -q ${OLD_SCRIPT} ${UPGRADE_SCRIPT} >/dev/null; then
    INFO "${YELLOW}[NEW]${NOFORMAT} Upgrade script is changed!"
    mv ${UPGRADE_SCRIPT} ${OLD_SCRIPT}
    chmod +x ${OLD_SCRIPT}
    SCRIPT_UPGRADE=true ${OLD_SCRIPT} --branch ${BRANCH} || exit 0
    exit 0
  fi

  INFO "${GREEN}[OK]${NOFORMAT} Upgrade script is up-to-date!"
}

done_script() {
  cd "${PROJECT_DIR}" || FAILED "Failed to change directory to ${PROJECT_DIR}"
  migrate_old_env

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

  INFO "Checking git status..."
  if git diff-index --quiet HEAD --; then
    FAILED "There are uncommitted changes, please commit or stash them first."
  fi

  INFO "Checkout to ${BRANCH} branch..."
  # Git checkout should ignore upgrade.sh changed
  git checkout "${BRANCH}" -- scripts/upgrade.sh

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

  # TODO: RELEASE API: https://api.github.com/repos/iii-org/deploy-devops-lite/releases/latest
  INFO "Downloading latest release..."
  wget -q -O release.tar.gz "https://github.com/iii-org/deploy-devops-lite/archive/refs/heads/${BRANCH}.tar.gz"

  INFO "Extracting files..."
  tar -xzf release.tar.gz

  INFO "Removing old files..."
  rm -rf "${PROJECT_DIR}"

  INFO "Copying files..."
  cp -rT deploy-devops-lite-${BRANCH}/ "${PROJECT_DIR}"

  if [[ -d "${backup_location}/generate" ]]; then
    INFO "Copying old generated files..."
    cp -rT "${backup_location}/generate" "${PROJECT_DIR}/generate"
  fi

  INFO "Cleaning up..."
  rm -rf deploy-devops-lite-${BRANCH}
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

  while [ $# -gt 0 ]; do
    case "$1" in
    -h | --help)
      usage
      ;;
    --branch)
      BRANCH="${2:-$BRANCH}"
      shift
      ;;
    *)
      echo "Illegal option $1"
      ;;
    esac
    shift $(($# > 0 ? 1 : 0))
  done

  DEBUG "Target branch: ${WHITE}${BRANCH}${NOFORMAT}"
  fetch_latest_upgrade_script
  migrate_old_generated

  if [ "$user" != "root" ]; then
    INFO "Changing permission of all files to current user (preventing permission issues)"
    INFO "Current user: $user"
    sudo chown -R "$user":"$user" "${PROJECT_DIR}"
  fi

  # Check if .git exists
  if [ ! -d "${PROJECT_DIR}"/.git ]; then
    update_via_tar
  else
    update_via_git
  fi
}

# WARNING: This script will **REPLACED** while upgrading, please put any custom script before this line.
main "$@"
