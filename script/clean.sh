#!/usr/bin/env bash

set -euo pipefail

# Load common functions
base_dir="$(cd "$(dirname "$0")" && pwd)"
source "$base_dir"/common.sh

cd "${project_dir:?}" || FAILED "Failed to change directory to ${project_dir:?}"

WARN "\e[33mThis script will remove all data in docker volumes.\e[0m"
WARN "\e[33mPlease make sure you have backed up your data.\e[0m"
echo -e "Press \e[96mCtrl+C\e[0m to cancel, sleep 5 seconds to continue..."
sleep 5

docker compose down -v
if [ -f .initialized ]; then
  rm .initialized
  INFO "Environment initialized flag removed"
fi
if [ -f environments.json ]; then
  rm environments.json
  INFO "Environment config file removed"
fi

# For folders in templates, remove all .git folders
INFO "Removing .git folders in templates"
for template_dir in templates/*; do
  if [ -d "$template_dir" ]; then
    if [ "$(check_docker_in_rootless)" == "true" ]; then
      find "$template_dir" -name .git -type d -prune \
        -exec rm -rf {} \; -exec echo -e "  -> removed \e[97m{}\e[0m" \;
    else
      find "$template_dir" -name .git -type d -prune \
        -exec sudo rm -rf {} \; -exec echo -e "  -> removed \e[97m{}\e[0m" \;
    fi
  fi
done

NOTICE "Environment cleaned up, please run \e[96msetup.sh\e[0m to re-initialize the environment."
