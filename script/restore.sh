#!/usr/bin/env bash

set -euo pipefail

# Load common functions
base_dir="$(cd "$(dirname "$0")" && pwd)"
source "$base_dir"/common.sh

# Backup directory
BACKUP_DIR="${project_dir:?}"/backup
GITLAB_BACKUP_DATA="$BACKUP_DIR"/gitlab_backup.tar
GITLAB_BACKUP_CONFIG="$BACKUP_DIR"/gitlab_config.tar
GITLAB_RUNNER="docker compose exec runner"

# Run as restore service
docker compose -f docker-compose.yaml -f docker-compose.restore.yaml up --build --no-deps -d

wait_gitlab() {
  # shellcheck disable=SC2034
  for i in {1..300}; do
    set +e # Disable exit on error
    STATUS_CODE="$($GITLAB_RUNNER curl -s -k -q --max-time 5 -w '%{http_code}' -o /dev/null "http://gitlab:$GITLAB_PORT/users/sign_in")"
    set -e # Enable exit on error

    if [ "$STATUS_CODE" -eq 200 ]; then
      echo
      INFO "GitLab ready, continue..."
      break
    fi
    echo -n "."
    sleep 1
  done
}

restore_gitlab() {
  INFO "Restore GitLab data..."

  # Check if the backup file exists
  if [ ! -f "$GITLAB_BACKUP_DATA" ]; then
    ERROR "Backup file not found: $GITLAB_BACKUP_DATA"
    exit 1
  fi

  if [ ! -f "$GITLAB_BACKUP_CONFIG" ]; then
    ERROR "Backup file not found: $GITLAB_BACKUP_CONFIG"
    exit 1
  fi

  wait_gitlab

  # Stop the processes that are connected to the database
  docker compose exec -it gitlab gitlab-ctl stop puma
  docker compose exec -it gitlab gitlab-ctl stop sidekiq

  INFO "=== Gitlab status ==="
  # Verify that the processes are all down before continuing
  set +e # Disable exit on error
  docker compose exec -it gitlab gitlab-ctl status
  set -e # Enable exit on error

  INFO "Restore GitLab config..."
  # Rename the existing /etc/gitlab, if any
  docker compose exec -it gitlab /bin/sh -c "mkdir -p /etc/gitlab.backup && mv /etc/gitlab/* /etc/gitlab.backup"
  docker compose exec -it gitlab mkdir -p /etc/gitlab/config_backup
  docker compose cp --archive "$GITLAB_BACKUP_CONFIG" gitlab:/etc/gitlab/config_backup/config_backup.tar
  docker compose exec -it gitlab tar -xPf /etc/gitlab/config_backup/config_backup.tar -C /
  docker compose exec -it gitlab gitlab-ctl reconfigure

  INFO "Restore GitLab data..."
  # Run the restore. NOTE: "_gitlab_backup.tar" is omitted from the name
  docker compose cp --archive "$GITLAB_BACKUP_DATA" gitlab:/var/opt/gitlab/backups/dump_gitlab_backup.tar
  docker compose exec -it gitlab chown git:git /var/opt/gitlab/backups/dump_gitlab_backup.tar
  docker compose exec -e GITLAB_ASSUME_YES=1 -it gitlab gitlab-backup restore BACKUP=dump

  # Restart the GitLab container
  docker compose -f docker-compose.yaml up gitlab --build --no-deps -d

  wait_gitlab

  INFO "Sanity check..."
  # Check GitLab
  docker compose exec -it gitlab gitlab-rake gitlab:check SANITIZE=true

  INFO "Restore GitLab done"
}

restore_gitlab
