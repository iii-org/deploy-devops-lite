#!/usr/bin/env bash

# This script is used to setup the project, include all necessary scripts
# And make sure the .env file is exist and loaded

BINARY_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
PROJECT_DIR="$(cd "$(dirname "$BINARY_DIR")" && pwd)"

DEBUG=false
export DEBUG

SPINNING=false
export SPINNING

# Log: https://serverfault.com/a/103569
#      https://unix.stackexchange.com/a/145654
#      https://blog.tratif.com/2023/01/09/bash-tips-1-logging-in-shell-scripts/

source "$BINARY_DIR"/functions.sh
source "$BINARY_DIR"/traps.sh

ENVIRONMENT_FILE="${PROJECT_DIR}"/.env

# If .env file does not exist, copy from .env.example
if [[ ! -f "$ENVIRONMENT_FILE" ]]; then
  # Make sure .env file is exist
  # So when we loaded the .env file, it will not throw error
  cp "$ENVIRONMENT_FILE".example "$ENVIRONMENT_FILE"
fi

# Call the function to load the .env file
load_env_file
