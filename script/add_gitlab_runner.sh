#!/usr/bin/env bash

set -euo pipefail

# Load common functions
base_dir="$(cd "$(dirname "$0")" && pwd)"
source "$base_dir"/common.sh

SHARED_RUNNER_NAME=""
GITLAB_URL=gitlab:${GITLAB_PORT}
GITLAB_INIT_TOKEN=""
RUNNER_REGISTRATION_TOKEN=""
RUNNER_EXEC="docker compose exec runner"

usage() {
  echo "Add GitLab Runner to GitLab"
  echo
  echo "Usage: $(basename "$0") <SHARED_RUNNER_NAME>"
  exit 21
}

main() {
  INFO "Adding GitLab Runner \e[97m$SHARED_RUNNER_NAME\e[0m to GitLab..."

  INFO "Getting GitLab Runner registration token..."
  RUNNER_REGISTRATION_TOKEN="$(docker compose exec gitlab gitlab-rails runner -e production "puts Gitlab::CurrentSettings.current_application_settings.runners_registration_token")"

  INFO "Registering GitLab Runner..."
  $RUNNER_EXEC gitlab-runner register -n \
    --url "http://gitlab:$GITLAB_PORT/" \
    --registration-token "$RUNNER_REGISTRATION_TOKEN" \
    --executor "docker" \
    --docker-image alpine:latest \
    --docker-privileged \
    --docker-volumes "$DOCKER_SOCKET:/var/run/docker.sock" \
    --description "$SHARED_RUNNER_NAME" \
    --tag-list "shared-runner" \
    --run-untagged="true" \
    --locked="false" \
    --access-level="not_protected"

  INFO "Provisioning GitLab Config..."
  # Get current /etc/gitlab-runner/config.toml concurrent value
  concurrent="$($RUNNER_EXEC cat /etc/gitlab-runner/config.toml | grep concurrent | awk '{print $3}')"
  INFO "Current concurrent value: $concurrent"
  # Modify /etc/gitlab-runner/config.toml concurrent value
  $RUNNER_EXEC sed -i "s/concurrent = $concurrent/concurrent = $((concurrent + 1))/" /etc/gitlab-runner/config.toml
  concurrent="$($RUNNER_EXEC cat /etc/gitlab-runner/config.toml | grep concurrent | awk '{print $3}')"
  INFO "New concurrent value: $concurrent"

  INFO "GitLab Runner \e[97m$SHARED_RUNNER_NAME\e[0m successfully added to GitLab"
}

# If no arguments are passed, print usage
if [ $# -eq 0 ]; then
  usage
fi

SHARED_RUNNER_NAME="$1"
shift

# Check if GITLAB_INIT_TOKEN is set
if [ -z "$GITLAB_INIT_TOKEN" ]; then
  # Check if file exist
  if [ ! -f "${project_dir:?}"/HEAD.env ]; then
    ERROR "Cannot find HEAD.env, please run \e[97m${project_dir}/setup.sh\e[0m to start project"
    exit 1
  fi

  GITLAB_INIT_TOKEN="$(jq -r '.GITLAB_PRIVATE_TOKEN' "$project_dir"/HEAD.env)"
fi

# Check if GitLab is running
if ! $RUNNER_EXEC curl -s -k "http://$GITLAB_URL/api/v4/version" >/dev/null; then
  ERROR "GitLab is not running, please run \e[97m${project_dir}/setup.sh\e[0m to start project"
  exit 1
fi

main
