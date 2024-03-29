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
    cd "${PROJECT_DIR}" || FAILED "Failed to change directory to ${PROJECT_DIR}"
    rm -rf -- ..?* .[!.]* *
    cd -

    INFO "Copy old files to new folder..."
    # Copy old files to new folder
    mv "${PROJECT_DIR}.bak" "${PROJECT_DIR}/generate"
  fi
}

rerun_command() {
  if [[ "${BRANCH}" != "master" ]]; then
    INFO "▶ ${YELLOW}./run.sh upgrade --branch ${BRANCH}${NOFORMAT}"
  else
    INFO "▶ ${YELLOW}./run.sh upgrade${NOFORMAT}"
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

  if ! type variable_write >/dev/null 2>&1; then
    INFO "variable_write function not found, which is upgrade from old version."
    INFO "Re run upgrade script to generate new .env file."
    INFO "Run this command to upgrade:"
    rerun_command
    exit 0
  fi

  DEBUG "Env file: $ENVIRONMENT_FILE"

  # Copy example .env to generate folder
  if [[ ! -f "$ENVIRONMENT_FILE" ]]; then
    # Make sure .env file is exist
    # So when we loaded the .env file, it will not throw error
    cp "$ENVIRONMENT_FILE".example "$ENVIRONMENT_FILE"
  fi

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
  INFO "Old environment file is migrated to new version."
  INFO "Please re-run command to start services."
  rerun_command
  exit 0
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

    # Force remove .version for upgrade script
    if [[ -f "${PROJECT_DIR}/.version" ]]; then
      rm "${PROJECT_DIR}/.version"
    fi

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

  if [[ -n "${DOCKER_COMPOSE_COMMAND:-}" ]]; then
    INFO "Using docker compose command: ${GREEN}${DOCKER_COMPOSE_COMMAND}${NOFORMAT}"
  else
    docker_get_version
  fi

  INFO "Restarting docker compose"
  INFO "If you wish to start up your self, you are safe to exit now."
  echo -e "Press \e[96mCtrl+C\e[0m to exit, sleep 5 seconds to continue..."
  sleep 5

  $DOCKER_COMPOSE_COMMAND pull
  # Fix mount permission issue
  $DOCKER_COMPOSE_COMMAND restart
  # Remove unused containers and update containers
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

  # Get remote name
  REMOTE_NAME=$(git remote)

  INFO "Checkout to ${BRANCH} branch..."
  # Git checkout should ignore upgrade.sh changed
  git checkout "${REMOTE_NAME}/${BRANCH}" -- scripts/upgrade.sh

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
  DEBUG "URL:" "https://github.com/iii-org/deploy-devops-lite/archive/refs/heads/${BRANCH}.tar.gz"
  wget -q -O release.tar.gz "https://github.com/iii-org/deploy-devops-lite/archive/refs/heads/${BRANCH}.tar.gz"

  INFO "Extracting files..."
  tar -xzf release.tar.gz

  INFO "Removing old files..."
  cd "${PROJECT_DIR}" || FAILED "Failed to change directory to ${PROJECT_DIR}"
  find . -mindepth 1 -maxdepth 1 \
    -not -name 'generate' \
    -not -name 'logs' \
    -not -name '.env' \
    -not -name '.version' \
    -exec rm -rf {} \;

  cd -

  INFO "Copying files..."
  cp -rT deploy-devops-lite-${BRANCH}/ "${PROJECT_DIR}"

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

  {
    if [[ -n "${project_dir:-}" ]]; then
      PROJECT_DIR="${project_dir}"
    fi

    if [[ -n "${bin_dir:-}" ]]; then
      BINARY_DIR="${bin_dir}"
    fi

    # Load color.sh
    if [[ -z "${WHITE:-}" ]]; then
      local COLOR_SCRIPT
      COLOR_SCRIPT="$(mktemp)"

      INFO "Fetching color script from ${BRANCH} branch..."
      wget -q -O ${COLOR_SCRIPT} "https://raw.githubusercontent.com/iii-org/deploy-devops-lite/${BRANCH}/scripts/library/libcolor.sh"
      # shellcheck source=scripts/library/libcolor.sh
      source "${COLOR_SCRIPT}"
      unset COLOR_SCRIPT
    else
      DEBUG "Color is already loaded"
    fi

    # Check if DEBUG function exists
    if ! type DEBUG >/dev/null 2>&1; then
      # Skip download new scripts upgrade.sh
      SCRIPT_UPGRADE=true
      local DEBUG_SCRIPT
      DEBUG_SCRIPT="$(mktemp)"

      INFO "Fetching log script from ${WHITE}${BRANCH}${NOFORMAT} branch..."
      wget -q -O ${DEBUG_SCRIPT} "https://raw.githubusercontent.com/iii-org/deploy-devops-lite/${BRANCH}/scripts/library/liblog.sh"

      # shellcheck source=scripts/library/liblog.sh
      source "${DEBUG_SCRIPT}"
      unset DEBUG_SCRIPT
    else
      DEBUG "Log is already loaded"
    fi

    # Check if docker_get_version function exists
    if ! type docker_get_version >/dev/null 2>&1; then
      local DOCKER_SCRIPT
      DOCKER_SCRIPT="$(mktemp)"

      INFO "Fetching docker script from ${WHITE}${BRANCH}${NOFORMAT} branch..."
      wget -q -O ${DOCKER_SCRIPT} "https://raw.githubusercontent.com/iii-org/deploy-devops-lite/${BRANCH}/scripts/library/libdocker.sh"
      # shellcheck source=scripts/library/libdocker.sh
      source "${DOCKER_SCRIPT}"
      unset DOCKER_SCRIPT
    else
      DEBUG "Docker script already loaded"
    fi
  }
  DEBUG "Target branch: ${WHITE}${BRANCH}${NOFORMAT}"
  fetch_latest_upgrade_script
  migrate_old_generated

  if [ "$user" != "root" ]; then
    INFO "Changing permission of all files to current user (preventing permission issues)"
    INFO "Current user: $user"
    sudo chown -R "$user":"$user" "${PROJECT_DIR}"
  fi

  updatelatest_version_fn() {
    echo "${REMOTE_HASH}" >"${PROJECT_DIR}/.version"

    INFO "Validating updated hash file..."
    if [[ $(cat "${PROJECT_DIR}/.version") == "${REMOTE_HASH}" ]]; then
      INFO "Hash file is valid, updating..."
      update_via_tar
    else
      ERROR "Can not update hash file, aborting..."
      exit 0
    fi
  }

  fetch_remote_hash() {
    REMOTE_HASH=$(curl -s https://api.github.com/repos/iii-org/deploy-devops-lite/commits/"${BRANCH}" | jq -r '.sha')
  }

  # Check if .git exists
  if [ ! -d "${PROJECT_DIR}"/.git ]; then
    if [[ -f "${PROJECT_DIR}/.version" ]]; then
      INFO "Checking version..."
      INFO "Last update check is at ${GREEN}$(date -r "${PROJECT_DIR}/.version" +"%Y-%m-%d %H:%M:%S")${NOFORMAT}"
      LOCAL_HASH=$(cat "${PROJECT_DIR}/.version")

      # Check if .version is not empty, and file should modified less than 1 hour
      if [[ -s "${PROJECT_DIR}/.version" ]] && [[ $(find "${PROJECT_DIR}/.version" -mmin -60) ]]; then
        INFO "Last update check is less than 1 hour, skipping update check"
        exit 0
      else
        INFO "Fetching the latest commit hash..."
        fetch_remote_hash

        if [[ "${REMOTE_HASH}" != "${LOCAL_HASH}" ]]; then
          INFO "${GREEN}[NEW]${NOFORMAT} version is available!"
          INFO "Remote hash: ${YELLOW}${REMOTE_HASH}${NOFORMAT}"
          INFO "Local hash: ${YELLOW}${LOCAL_HASH}${NOFORMAT}"

          updatelatest_version_fn

        else
          INFO "Already up-to-date"

          # Remember to update .version last modified time
          touch "${PROJECT_DIR}/.version"
          exit 0
        fi
      fi
    else
      fetch_remote_hash
      updatelatest_version_fn
    fi
  else
    update_via_git
  fi
}

# WARNING: This script will **REPLACED** while upgrading, please put any custom script before this line.
main "$@"
