#!/usr/bin/env bash

set -euo pipefail

# Load common functions
base_dir="$(cd "$(dirname "$0")" && pwd)"
source "$base_dir"/common.sh
docker_get_version

SHARED_RUNNER_NAME=""
ACTION=""
RUNNER_REGISTRATION_TOKEN=""
RUNNER_EXEC="$DOCKER_COMPOSE_COMMAND exec runner"

# Only for IP mode
if [[ "${MODE:-}" = "IP" ]]; then
  DOMAIN_GITLAB="gitlab:${GITLAB_PORT}"
  URL_GITLAB="http://${DOMAIN_GITLAB}"
fi

usage() {
  cat <<EOF
Usage: $(basename "$0") [options]... <ACTION> <SHARED_RUNNER_NAME>

Add or remove GitLab runner.

Actions:
  add         Alias for new
  delete      Alias for remove
  new         Add GitLab runner
  remove      Remove GitLab runner

Options:
  -h,  --help                 print this help
EOF
  exit 21
}

new() {
  INFO "Adding GitLab Runner \e[97m$SHARED_RUNNER_NAME\e[0m to GitLab..."

  INFO "Getting GitLab Runner registration token..."
  RUNNER_REGISTRATION_TOKEN="$($DOCKER_COMPOSE_COMMAND exec gitlab gitlab-rails runner -e production "puts Gitlab::CurrentSettings.current_application_settings.runners_registration_token")"

  INFO "Registering GitLab Runner..."
  $RUNNER_EXEC gitlab-runner register -n \
    --url "${URL_GITLAB}/" \
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

remove() {
  local concurrent
  concurrent="$($RUNNER_EXEC cat /etc/gitlab-runner/config.toml | grep concurrent | awk '{print $3}')"

  if [ "$concurrent" -eq 1 ]; then
    ERROR "Can not remove the last GitLab Runner"
    exit 1
  fi

  INFO "Removing GitLab Runner \e[97m$SHARED_RUNNER_NAME\e[0m from GitLab..."

  INFO "Checking GitLab Runner exist..."
  if [ -z "$($DOCKER_COMPOSE_COMMAND exec gitlab gitlab-rails runner -e production "puts Ci::Runner.where(description: '$SHARED_RUNNER_NAME').first")" ]; then
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
if [ $# -ne 2 ]; then
  usage
fi

ACTION="$1"
shift
SHARED_RUNNER_NAME="$1"
shift

get_init_token
if ! $RUNNER_EXEC curl -s -k "${URL_GITLAB}/api/v4/version" >/dev/null; then
  ERROR "GitLab is not running, please run \e[97m${project_dir:?}/run.sh\e[0m to start project"
  exit 1
fi

case $ACTION in
add | new)
  new
  ;;
del | delete | remove)
  remove
  ;;
esac
