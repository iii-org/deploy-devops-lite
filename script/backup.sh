#!/usr/bin/env bash

set -euo pipefail

# Load common functions
base_dir="$(cd "$(dirname "$0")" && pwd)"
source "$base_dir"/common.sh

# Backup directory
BACKUP_DIR="${project_dir:?}"/backup
GITLAB_BACKUP_DATA="$BACKUP_DIR"/gitlab_backup.tar
GITLAB_BACKUP_CONFIG="$BACKUP_DIR"/gitlab_config.tar
GITLAB_RUNNER_CONFIG="$BACKUP_DIR"/gitlab-runner-config.toml
SONARQUBE_SQL="$BACKUP_DIR"/sonarqube.sql
REDMINE_FILES="$BACKUP_DIR"/redmine_files.tar.gz
REDMINE_SQL="$BACKUP_DIR"/redmine.sql

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

backup_gitlab_runner_config() {
  INFO "Backup GitLab Runner config..."
  docker compose exec -t runner cat /etc/gitlab-runner/config.toml >"$GITLAB_RUNNER_CONFIG"
  INFO "Backup GitLab Runner config done"
}

backup_sonarqube() {
  INFO "Backup SonarQube data..."

  # shellcheck disable=SC1004
  docker compose exec sonarqube-db \
    bash -c 'PGPASSWORD="${POSTGRESQL_PASSWORD}" pg_dump \
      -U "${POSTGRESQL_USERNAME}" \
      --dbname="${POSTGRESQL_DATABASE}"' >"$SONARQUBE_SQL"

  INFO "Backup SonarQube done"
}

backup_redmine() {
  INFO "Backup Redmine service..."

  # Backup Redmine files
  docker compose exec redmine bash -c 'cd /usr/src/redmine/files && tar czf - .' >"$REDMINE_FILES"

  # shellcheck disable=SC1004
  docker compose exec redmine-db \
    bash -c 'PGPASSWORD="${POSTGRESQL_PASSWORD}" pg_dump \
      -U "${POSTGRES_USER}" \
      --dbname="${POSTGRES_DB}"' >"$REDMINE_SQL"

  INFO "Backup Redmine done"
}

backup_gitlab
backup_gitlab_runner_config
backup_sonarqube
backup_redmine
