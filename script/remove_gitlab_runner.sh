#!/usr/bin/env bash

set -euo pipefail

# Load common functions
base_dir="$(cd "$(dirname "$0")" && pwd)"
source "$base_dir"/common.sh

SHARED_RUNNER_NAME=""
GITLAB_URL=gitlab:${GITLAB_PORT}
RUNNER_EXEC="docker compose exec runner"

usage() {
  echo "Remove GitLab Runner from GitLab"
  echo
  echo "Usage: $(basename "$0") <SHARED_RUNNER_NAME>"
  exit 21
}

main() {
  local concurrent
  concurrent="$($RUNNER_EXEC cat /etc/gitlab-runner/config.toml | grep concurrent | awk '{print $3}')"

  if [ "$concurrent" -eq 1 ]; then
    ERROR "Can not remove the last GitLab Runner"
    exit 1
  fi

  INFO "Removing GitLab Runner \e[97m$SHARED_RUNNER_NAME\e[0m from GitLab..."

  INFO "Checking GitLab Runner exist..."
  if [ -z "$(docker compose exec gitlab gitlab-rails runner -e production "puts Ci::Runner.where(description: '$SHARED_RUNNER_NAME').first")" ]; then
    ERROR "GitLab Runner \e[97m$SHARED_RUNNER_NAME\e[0m is not registered"
    exit 1
  fi

  $RUNNER_EXEC gitlab-runner unregister --name "$SHARED_RUNNER_NAME"

  INFO "Provisioning GitLab Config..."
  # Get current /etc/gitlab-runner/config.toml concurrent value
  concurrent="$($RUNNER_EXEC cat /etc/gitlab-runner/config.toml | grep concurrent | awk '{print $3}')"
  INFO "Current concurrent value: $concurrent"
  # Modify /etc/gitlab-runner/config.toml concurrent value
  $RUNNER_EXEC sed -i "s/concurrent = $concurrent/concurrent = $((concurrent - 1))/" /etc/gitlab-runner/config.toml
  concurrent="$($RUNNER_EXEC cat /etc/gitlab-runner/config.toml | grep concurrent | awk '{print $3}')"
  INFO "New concurrent value: $concurrent"

  INFO "GitLab Runner \e[97m$SHARED_RUNNER_NAME\e[0m successfully removed from GitLab"
}

# If no arguments are passed, print usage
if [ $# -eq 0 ]; then
  usage
fi

SHARED_RUNNER_NAME="$1"
shift

# Check if GitLab is running
if ! $RUNNER_EXEC curl -s -k "http://$GITLAB_URL/api/v4/version" >/dev/null; then
  ERROR "GitLab is not running, please run \e[97m${project_dir:?}/setup.sh\e[0m to start project"
  exit 1
fi

main
