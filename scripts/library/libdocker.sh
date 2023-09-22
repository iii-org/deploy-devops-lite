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
    DOCKER_COMPOSE_VERSION="$(docker compose version | grep -oP '(?<=version )[^,]+')"
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
}
