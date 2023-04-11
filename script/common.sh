#!/usr/bin/env bash

bin_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
project_dir="$(cd "$(dirname "$bin_dir")" && pwd)"

source "$bin_dir"/functions.sh

# Change directory to project directory
cd "$project_dir" || FAILED "Failed to change directory to $project_dir"

# Source .env file
env_file="${project_dir}"/.env

# If .env file not exists, copy from .env.example
if [ ! -f "$env_file" ]; then
  cp "$env_file".example "$env_file"
  # Since we only generate the env file, we don't fill the actual value here
fi

# Load .env file
set -a
# shellcheck source=/dev/null
. "$env_file"
set +a
