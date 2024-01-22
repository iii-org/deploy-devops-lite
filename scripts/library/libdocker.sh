#!/usr/bin/env bash

DOCKER_VERSION=""                           # The version of docker, e.g. "24.0.4"
DOCKER_COMMAND="docker"                     # The command to run docker, e.g. "docker" or "sudo docker"
DOCKER_WITHOUT_SUDO=false                   # Whether docker can be run without sudo
DOCKER_COMPOSER=""                          # The command to run docker compose, e.g. "docker compose" or "docker-compose"
DOCKER_COMPOSE_CONFIG="docker-compose.yaml" # The docker compose config file to use, e.g. "docker-compose.yml"
DOCKER_COMPOSE_VERSION=""                   # The version of docker compose, e.g. "v2.20.2"
DOCKER_COMPOSE_COMMAND=""                   # The command to run docker compose, e.g. "docker compose -f docker-compose.yml"

export DOCKER_VERSION
export DOCKER_COMMAND
export DOCKER_WITHOUT_SUDO
export DOCKER_COMPOSER
export DOCKER_COMPOSE_CONFIG
export DOCKER_COMPOSE_VERSION
export DOCKER_COMPOSE_COMMAND

docker_print_info() {
  INFO "$(title_center "DOCKER INFO")"
  INFO "Docker version: ${GREEN}${DOCKER_VERSION}${NOFORMAT}"
  INFO "Docker command: ${GREEN}${DOCKER_COMMAND}${NOFORMAT}"
  INFO "Docker compose version: ${GREEN}${DOCKER_COMPOSE_VERSION}${NOFORMAT}"
  INFO "Docker compose command: ${GREEN}${DOCKER_COMPOSE_COMMAND}${NOFORMAT}"
  INFO "Docker compose config: ${GREEN}${DOCKER_COMPOSE_CONFIG}${NOFORMAT}"
  INFO "Run docker without sudo: $(if [[ "$DOCKER_WITHOUT_SUDO" == "true" ]]; then echo "${GREEN}true${NOFORMAT}"; else echo "${RED}false${NOFORMAT}"; fi)"
  INFO "========================================"
}

docker_permission_check() {
  # Check have correct docker permission
  if ! $DOCKER_COMMAND ps >/dev/null 2>&1; then
    ERROR "Docker permission check failed, please check if you have correct docker permission"
    ERROR "Maybe you try to run docker in root mode? Set the correct docker socket and try again"
    exit 1
  fi
}

docker_get_version() {
  local socket
  socket="$(detect_docker_socket)"

  if command_exists docker; then
    DOCKER_VERSION="$(docker version --format '{{.Server.Version}}')"
  else
    return
  fi

  # If user is not in docker group, check if docker rootless is enabled
  if ! groups | grep -q docker; then
    # Check socket is owned by current user
    if [[ "$(stat -c '%U' "$socket")" == "$USER" ]]; then
      DOCKER_WITHOUT_SUDO=true
    fi
  else
    DOCKER_WITHOUT_SUDO=true
  fi

  if docker compose version &>/dev/null; then
    # Docker Compose version v2.19.1
    DOCKER_COMPOSER="docker compose"
    DOCKER_COMPOSE_VERSION="$(docker compose version --short)"
  elif docker-compose --version &>/dev/null; then
    # docker-compose version X.Y.Z, build <identifier>
    DOCKER_COMPOSER="docker-compose"
    DOCKER_COMPOSE_VERSION="$(docker-compose --version | grep -oP '(?<=version )[^,]+')"
  fi

  if $DOCKER_WITHOUT_SUDO; then
    DOCKER_COMMAND="docker"
  else
    DOCKER_COMMAND="sudo docker"
    DOCKER_COMPOSER="sudo $DOCKER_COMPOSER"
  fi

  DOCKER_COMPOSE_COMMAND="$DOCKER_COMPOSER"

  # Failed to get docker compose version
  if [[ -z "$DOCKER_COMPOSE_VERSION" ]]; then
    FAILED "Failed to get docker compose version, please check your docker installation."
    exit 1
  fi

  docker_version_check
}

# version_compare compares two version strings (either SemVer (Major.Minor.Path),
# or CalVer (YY.MM) version strings. It returns 0 (success) if version A is newer
# or equal than version B, or 1 (fail) otherwise. Patch releases and pre-release
# (-alpha/-beta) are not taken into account
#
# examples:
#
# version_compare 23.0.0 20.10 // 0 (success)
# version_compare 23.0 20.10   // 0 (success)
# version_compare 20.10 19.03  // 0 (success)
# version_compare 20.10 20.10  // 0 (success)
# version_compare 19.03 20.10  // 1 (fail)
version_compare() (
  yy_a="$(echo "$1" | cut -d'.' -f1)"
  yy_b="$(echo "$2" | cut -d'.' -f1)"
  if [ "$yy_a" -lt "$yy_b" ]; then
    return 1
  fi
  if [ "$yy_a" -gt "$yy_b" ]; then
    return 0
  fi
  mm_a="$(echo "$1" | cut -d'.' -f2)"
  mm_b="$(echo "$2" | cut -d'.' -f2)"

  # trim leading zeros to accommodate CalVer
  mm_a="${mm_a#0}"
  mm_b="${mm_b#0}"

  if [ "${mm_a:-0}" -lt "${mm_b:-0}" ]; then
    return 1
  fi

  return 0
)

docker_version_check() {
  DOCKER_COMPOSE_VERSION="$(docker compose version --short)"

  # If docker compose version below 2.20, failed the script
  if version_compare "2.20" "$DOCKER_COMPOSE_VERSION"; then
    FAILED "Docker compose version is too old, please upgrade to 2.20 or above."
  fi

  # If docker compose version is 2.24.*, failed the script
  if [[ "$DOCKER_COMPOSE_VERSION" =~ ^2\.24\..* ]]; then
    ERROR "Error docker compose version, please downgrade to 2.20 - 2.23."
    ERROR "See: https://github.com/docker/compose/issues/11379"
    exit 0
  fi
}
