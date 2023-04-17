#!/usr/bin/env bash

set -euo pipefail

base_dir="$(cd "$(dirname "$0")" && pwd)" # Base directory of this script
project_dir="$base_dir"/Lite              # Default project directory

if [ ! -f "$base_dir"/common.sh ]; then
  echo "Downloading minimal required files..."
  # Download functions.sh if functions.sh not exists
  wget -q -O "$base_dir"/functions.sh https://raw.githubusercontent.com/iii-org/deploy-devops-lite/master/script/functions.sh
  chmod +x "$base_dir"/functions.sh

  source "$base_dir"/functions.sh

  WARN "Missing \e[92mcommon.sh\e[0m, assuming this is a standalone script."

  mkdir -p "$project_dir"
else
  # If common.sh exists, we are in the project directory
  source "$base_dir"/common.sh
fi

done_script() {
  INFO "Restart docker compose"
  INFO "If you wish to start up your self, you are safe to exit now."
  echo -e "Press \e[96mCtrl+C\e[0m to exit, sleep 5 seconds to continue..."
  sleep 5

  docker compose pull
  docker compose up \
    --remove-orphans -d
}

update_via_git() {
  cd "${project_dir}" || FAILED "Failed to change directory to ${project_dir}"

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
  cd "${project_dir}" || FAILED "Failed to change directory to ${project_dir}"
  cd ..

  INFO "Downloading latest release..."

  # https://github.com/iii-org/deploy-devops-lite/archive/refs/heads/master.tar.gz
  wget -q -O release.tar.gz https://github.com/iii-org/deploy-devops-lite/archive/refs/heads/master.tar.gz

  INFO "Extracting files..."
  tar -xzf release.tar.gz

  INFO "Copying files..."
  cp -rT deploy-devops-lite-master/ "$project_dir"

  INFO "Cleaning up..."
  rm -rf deploy-devops-lite-master
  rm release.tar.gz

  done_script
}

# Check if .git exists
if [ ! -d "${project_dir}"/.git ]; then
  update_via_tar
else
  update_via_git
fi

# WARNING: This script will **REPLACED** while upgrading, please put any custom script before this line.
