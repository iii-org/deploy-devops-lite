#!/usr/bin/env bash

set -euo pipefail

base_dir="$(cd "$(dirname "$0")" && pwd)"
LOG_FOLDER="${base_dir}/logs"

usage() {
  cat <<EOF
Usage: $(basename "${BASH_SOURCE[0]}") [TARGET]... [OPTION]... [ARGUMENT]...

Basic run for III DevOps Community version.

Targets:
  setup             Setup III DevOps Community version (default)
  clean             Remove III DevOps Community version
  template          Update III DevOps templates to GitLab
  upgrade           Upgrade III DevOps Community version
  runner            Add or remove GitLab runner
  backup            Backup III DevOps Community version (not implemented)
  restore           Restore III DevOps Community version (not implemented)

Options:
  -h, --help  Print this help and exit
EOF
  exit 0
}

# If $1 exist and start with '-h', or '--help', then it's a help
if [[ -n "${1-}" && "${1-}" =~ ^-h|--help$ ]]; then
  usage
fi

# If $1 exist and not start with '-', then it's a target
if [[ -n "${1-}" && "${1-}" != -* ]]; then
  target="${1-}"
  shift
else
  target="setup"
fi

target_list=(
  "setup"
  "clean"
  "template"
  "upgrade"
  "runner"
  "backup"
  "restore"
)

# Find target in target_list
if [[ ! " ${target_list[*]} " =~ \ ${target}\  ]]; then
  echo -e "\033[1;31mInvalid target\033[0m: ${target}"
  usage
fi

script_command="$base_dir/scripts/${target}.sh $*"

if [[ ! -d "${LOG_FOLDER}" ]]; then
  mkdir -p "${LOG_FOLDER}"
fi

if [[ -f "${LOG_FOLDER}/${target}.log" ]]; then
  # Get file generate time
  file_time=$(stat -c %Y "${LOG_FOLDER}/${target}.log")
  mv "${LOG_FOLDER}/${target}.log" "${LOG_FOLDER}/${target}.$(date -d @$file_time +%Y%m%d%H%M%S).log"
fi

# Make sure change the working directory to the script's location
cd "$base_dir" || { echo "Cannot change directory to $base_dir" && exit 1; }

script --quiet -c "$script_command" "${LOG_FOLDER}/${target}.log"
