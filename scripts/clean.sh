#!/usr/bin/env bash

set -euo pipefail

# Load common functions
base_dir="$(cd "$(dirname "$0")" && pwd)"
source "$base_dir"/common.sh

docker_get_version

cd "${PROJECT_DIR:?}" || FAILED "Failed to change directory to ${PROJECT_DIR:?}"

WARN "${ORANGE}This script will remove all data in docker volumes.${NOFORMAT}"
WARN "${ORANGE}Please make sure you have backed up your data.${NOFORMAT}"
echo -e "Press ${RED}Ctrl+C${NOFORMAT} to cancel, sleep 5 seconds to continue..."
sleep 5

DOCKER_SOCKET="$(detect_docker_socket)" $DOCKER_COMPOSE_COMMAND down -v

if [[ -f "${PROJECT_DIR}/.checked" ]]; then
  rm "${PROJECT_DIR}/.checked"
  INFO "✅ Commands check file removed"
fi

if [[ -d "${PROJECT_DIR}/generate" ]]; then
  sudo rm -rf "${PROJECT_DIR}/generate"
  INFO "✅ Generate folder removed"
fi

if [[ -f "${PROJECT_DIR}/.env" ]]; then
  rm "${PROJECT_DIR}/.env"
  if [[ -f "${PROJECT_DIR}/.env.bak" ]]; then
    rm "${PROJECT_DIR}/.env.bak"
  fi
  INFO "✅ Environment config file removed"
fi

# For folders in templates, remove all .git folders
INFO "ℹ️ Removing .git folders in templates"
for template_dir in templates/*; do
  if [[ -d "$template_dir" ]]; then
    if $DOCKER_WITHOUT_SUDO; then
      find "$template_dir" -name .git -type d -prune \
        -exec rm -rf {} \; \
        -exec echo -e "  -> removed \e[97m{}\e[0m" \;
    else
      find "$template_dir" -name .git -type d -prune \
        -exec sudo rm -rf {} \; \
        -exec echo -e "  -> removed \e[97m{}\e[0m" \;
    fi
  fi
done

NOTICE "Environment cleaned up, please run ${CYAN}run.sh${NOFORMAT} to re-install."
