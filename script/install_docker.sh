#!/usr/bin/env bash
# shellcheck disable=SC2155

set -euo pipefail

# Load common functions
base_dir="$(cd "$(dirname "$0")" && pwd)"
source "$base_dir"/common.sh

# Via https://get.docker.com/
echo "[+] curl -s https://get.docker.com/ | bash"
curl -s https://get.docker.com/ | bash

INFO "Setting up docker in rootless mode..."
sudo apt-get update -qq >/dev/null
sudo apt-get install -y -qq uidmap >/dev/null

if systemctl --user show-environment >/dev/null 2>&1; then
  SYSTEMD=1
fi

if [ -n "${SYSTEMD:-}" ]; then
  # Linger user
  loginctl enable-linger "$(whoami)"

  export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u)/bus
  echo "export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u)/bus" >>~/.bashrc
  export XDG_RUNTIME_DIR=/run/user/$(id -u)
  echo "export XDG_RUNTIME_DIR=/run/user/$(id -u)" >>~/.bashrc

  # shellcheck disable=SC1090
  source ~/.bashrc

  # Critical check to make sure systemd is running, it can be triggered on login method
  echo 'Trying to start dbus service, sleep 3 seconds'
  sleep 3
fi

# Print systemd environment, check if $USER can use systemctl
systemctl --user show-environment

# Run dockerd-rootless.sh
dockerd-rootless-setuptool.sh install

BIN="$(dirname "$(command -v dockerd-rootless.sh)")"

# Set cap_net_bind_service capability to allow binding to privileged ports (e.g. 80, 443)
sudo setcap cap_net_bind_service=ep "$(command -v rootlesskit)"
systemctl --user restart docker

# Enable linger to keep the user systemd instance running
# From official docs https://docs.docker.com/engine/security/rootless/#daemon
systemctl --user start docker
systemctl --user enable docker
loginctl enable-linger "$(whoami)"

export PATH=$BIN:$PATH
echo "export PATH=$BIN:$PATH" >>~/.bashrc
export DOCKER_HOST=unix://${XDG_RUNTIME_DIR}/docker.sock
echo "export DOCKER_HOST=unix://${XDG_RUNTIME_DIR}/docker.sock" >>~/.bashrc

# Check if dbus service is active
# To fix https://docs.docker.com/engine/security/rootless/#docker-run-errors
for i in {1..10}; do
  if ! systemctl --user is-active --quiet dbus; then
    WARN "dbus service is not active, trying to start it..."
    WARN "if dbus is still inactive, please re-login to your system and run this script again"
    systemctl --user enable --now dbus
  else
    INFO "dbus service is active, continue..."
    break
  fi
done
