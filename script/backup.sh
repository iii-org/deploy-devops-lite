#!/usr/bin/env bash

set -euo pipefail

# Load common functions
base_dir="$(cd "$(dirname "$0")" && pwd)"
source "$base_dir"/common.sh

# Backup directory
BACKUP_DIR="${project_dir:?}"/backup
GITLAB_BACKUP_DATA="$BACKUP_DIR"/gitlab_backup.tar
GITLAB_BACKUP_CONFIG="$BACKUP_DIR"/gitlab_config.tar

if [ ! -d "$BACKUP_DIR" ]; then
  mkdir -p "$BACKUP_DIR"
else
  INFO "Clean up backup directory..."
  rm -rf "${BACKUP_DIR:?}"/*
fi

backup_gitlab() {
  INFO "Backup GitLab data..."
  docker compose exec -t gitlab gitlab-backup create BACKUP=dump
  docker compose cp --archive gitlab:/var/opt/gitlab/backups/dump_gitlab_backup.tar "$GITLAB_BACKUP_DATA"
  docker compose exec gitlab rm -f /var/opt/gitlab/backups/dump_gitlab_backup.tar

  INFO "Backup GitLab config..."
  docker compose exec -t gitlab gitlab-ctl backup-etc >/dev/null 2>&1
  CONFIG_TAR_NAME="$(docker compose exec gitlab ls -t /etc/gitlab/config_backup | head -n1)"
  INFO "Configuration backup archive complete: $CONFIG_TAR_NAME"
  docker compose cp --archive gitlab:/etc/gitlab/config_backup/"$CONFIG_TAR_NAME" "$GITLAB_BACKUP_CONFIG"
  docker compose exec gitlab rm -f /etc/gitlab/config_backup/"$CONFIG_TAR_NAME"

  INFO "Backup GitLab done"
}

backup_gitlab
