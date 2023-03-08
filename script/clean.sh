#!/usr/bin/env bash

set -eu

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

NOTICE "Environment cleaned up, please run \e[96msetup.sh\e[0m to re-initialize the environment."
