#!/usr/bin/env bash

set -euo pipefail

# Load common functions
base_dir="$(cd "$(dirname "$0")" && pwd)"
source "$base_dir"/common.sh

cd "${project_dir:?}" || FAILED "Failed to change directory to ${project_dir:?}"

# Check if .git exists
if [ ! -d "${project_dir}"/.git ]; then
  FAILED "This script only works for git repository"
fi

INFO "Updating git remotes"
git remote update

LOCAL=$(git rev-parse @)
REMOTE=$(git rev-parse '@{u}')

if [ "$LOCAL" = "$REMOTE" ]; then
  INFO "Already up-to-date"
  exit 0
fi

INFO "Pulling latest changes"
git pull

INFO "Restart docker compose"
INFO "If you wish to start up your self, you are safe to exit now."
echo -e "Press \e[96mCtrl+C\e[0m to exit, sleep 5 seconds to continue..."
sleep 5

docker compose pull
docker compose up \
  --remove-orphans -d
