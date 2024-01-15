#!/usr/bin/env bash

# This script is used to setup the project, include all necessary scripts
# And make sure the .env file is exist and loaded

BINARY_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
PROJECT_DIR="$(cd "$(dirname "$BINARY_DIR")" && pwd)"

SPINNING=false
export SPINNING

# Load colors
source "$BINARY_DIR"/library/libcolor.sh

# Load basic logging module
source "$BINARY_DIR"/library/liblog.sh

# This script load all functions
source $BINARY_DIR/library/libcommon.sh
source $BINARY_DIR/library/libtitle.sh

source "$BINARY_DIR"/library/libsetup.sh
source "$BINARY_DIR"/library/libdocker.sh
source "$BINARY_DIR"/library/libvariable.sh

source "$BINARY_DIR"/library/traps.sh

ENVIRONMENT_FILE="${PROJECT_DIR}"/.env

# If .env file does not exist, copy from .env.example
if [[ ! -f "$ENVIRONMENT_FILE" ]]; then
  # Make sure .env file is exist
  # So when we loaded the .env file, it will not throw error
  cp "$ENVIRONMENT_FILE".example "$ENVIRONMENT_FILE"
fi

# Call the function to load the .env file
load_env_file
