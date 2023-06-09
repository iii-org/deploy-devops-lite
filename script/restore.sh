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
IIIDEVOPS_FILES="$BACKUP_DIR"/iiidevops_files.tar.gz
IIIDEVOPS_SQL="$BACKUP_DIR"/iiidevops.sql
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

restore_runner() {
  INFO "Restore GitLab Runner config..."

  # Check if the backup file exists
  if [ ! -f "$GITLAB_RUNNER_CONFIG" ]; then
    ERROR "Backup file not found: $GITLAB_RUNNER_CONFIG"
    exit 1
  fi

  # Restore the GitLab Runner config
  docker compose cp --archive "$BACKUP_DIR"/gitlab-runner-config.toml runner:/etc/gitlab-runner/config.toml

  INFO "List GitLab Runner config..."
  # Check GitLab Runner
  docker compose exec runner gitlab-runner list

  INFO "Restore GitLab Runner config done"
}

restore_sonarqube() {
  INFO "Restore SonarQube data..."

  # Stop service
  docker compose stop sonarqube

  # DROP DATABASE
  # shellcheck disable=SC1004
  docker compose exec sonarqube-db \
    bash -c 'PGPASSWORD="${POSTGRESQL_PASSWORD}" psql \
      -U "${POSTGRESQL_USERNAME}" -c "DROP DATABASE ${POSTGRESQL_DATABASE}"' >/dev/null 2>&1

  # CREATE DATABASE
  # shellcheck disable=SC1004
  docker compose exec sonarqube-db \
    bash -c 'PGPASSWORD="${POSTGRESQL_PASSWORD}" psql \
      -U "${POSTGRESQL_USERNAME}" -c "CREATE DATABASE ${POSTGRESQL_DATABASE}"' >/dev/null 2>&1

  # shellcheck disable=SC1004
  docker compose exec -T sonarqube-db \
    bash -c 'PGPASSWORD="${POSTGRESQL_PASSWORD}" psql \
      -U "${POSTGRESQL_USERNAME}" "${POSTGRESQL_DATABASE}"' <"$SONARQUBE_SQL" >/dev/null 2>&1

  # Start service
  docker compose start sonarqube

  INFO "Restore SonarQube data done"
}

restore_redmine() {
  INFO "Restore Redmine data..."

  # Check if /usr/src/redmine/files empty
  if [ "$(docker compose exec redmine ls -A /usr/src/redmine/files)" ]; then
    # Remove all files in /usr/src/redmine/files
    docker compose exec redmine find /usr/src/redmine/files -mindepth 1 -delete
  fi

  # Restore files from backup
  docker compose cp --archive "$REDMINE_FILES" redmine:/usr/src/redmine/files.tar.gz
  docker compose exec redmine tar -xPf /usr/src/redmine/files.tar.gz -C /usr/src/redmine/files
  docker compose exec redmine rm /usr/src/redmine/files.tar.gz

  # Stop service
  docker compose stop redmine

  # Drop database
  # shellcheck disable=SC1004
  docker compose exec redmine-db \
    bash -c 'PGPASSWORD="${POSTGRESQL_PASSWORD}" psql \
      -U "${POSTGRES_USER}" -c "DROP DATABASE ${POSTGRES_DB}"' >/dev/null 2>&1

  # Create database
  # shellcheck disable=SC1004
  docker compose exec redmine-db \
    bash -c 'PGPASSWORD="${POSTGRESQL_PASSWORD}" psql \
      -U "${POSTGRES_USER}" -c "CREATE DATABASE ${POSTGRES_DB}"' >/dev/null 2>&1

  # Restore database
  # shellcheck disable=SC1004
  docker compose exec -T redmine-db \
    bash -c 'PGPASSWORD="${POSTGRESQL_PASSWORD}" psql \
      -U "${POSTGRES_USER}" "${POSTGRES_DB}"' <"$REDMINE_SQL" >/dev/null 2>&1

  # Start service
  docker compose start redmine

  INFO "Restore Redmine data done"
}

restore_iiidevops() {
  INFO "Restore iiidevops data..."

  local api_service="iii-devops-lite-api"
  local api_worker_service="iii-devops-lite-api-worker"
  local api_beat_service="iii-devops-lite-api-beat"
  local db_service="iii-devops-lite-db"
  local api_exec="docker compose exec $api_service"
  local db_exec="docker compose exec -T $db_service"

  # Check if /opt/nfs empty
  if [ "$($api_exec ls -A /opt/nfs)" ]; then
    # Remove all files in /opt/nfs
    $api_exec find /opt/nfs -mindepth 1 -delete
  fi

  # Restore files from backup
  docker compose cp --archive "$IIIDEVOPS_FILES" "$api_service":/opt/nfs.tar.gz
  $api_exec tar -xPf /opt/nfs.tar.gz -C /opt/nfs
  $api_exec rm /opt/nfs.tar.gz

  # Stop service
  docker compose stop "$api_service"
  docker compose stop "$api_worker_service"
  docker compose stop "$api_beat_service"

  # Drop database
  # shellcheck disable=SC1004
  # shellcheck disable=SC2016
  $db_exec bash -c 'PGPASSWORD="${POSTGRESQL_PASSWORD}" psql \
    -U "${POSTGRES_USER}" -c "DROP DATABASE ${III_DB}"' >/dev/null 2>&1

  # Create database
  # shellcheck disable=SC1004
  # shellcheck disable=SC2016
  $db_exec bash -c 'PGPASSWORD="${POSTGRESQL_PASSWORD}" psql \
    -U "${POSTGRES_USER}" -c "CREATE DATABASE ${III_DB}"' >/dev/null 2>&1

  # Restore database
  # shellcheck disable=SC1004
  # shellcheck disable=SC2016
  $db_exec bash -c 'PGPASSWORD="${POSTGRESQL_PASSWORD}" psql \
    -U "${POSTGRES_USER}" "${III_DB}"' <"$IIIDEVOPS_SQL" >/dev/null 2>&1

  # Start service
  docker compose start "$api_service"
  docker compose start "$api_worker_service"
  docker compose start "$api_beat_service"

  INFO "Restore iiidevops data done"
}

restore_gitlab
restore_runner
restore_sonarqube
restore_redmine
restore_iiidevops
