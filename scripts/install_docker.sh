#!/usr/bin/env bash
# shellcheck disable=SC2155

set -euo pipefail

# Load common functions
base_dir="$(cd "$(dirname "$0")" && pwd)"
source "$base_dir"/common.sh

# Via https://get.docker.com/
echo "[+] curl -s https://get.docker.com/ | bash"
curl -s https://get.docker.com/ | bash

INFO "🔃 Adding user to docker group..."
sudo usermod -aG docker "$USER"
INFO "✅ Docker installed successfully! Please re-run './run.sh' to continue installing."
