#!/usr/bin/env bash

set -e

# shellcheck disable=SC2046
export $(grep -v '^#' .env | xargs)

function cecho() {
  local level=$1
  shift
  # Turn level to lower case
  level=$(echo "$level" | tr '[:upper:]' '[:lower:]')

  # If level is info, use light green color and print to stdout
  if [ "$level" = "info" ]; then
    echo -e "\033[1;32m[INFO]\033[0m $*"
  # If level is warn, use yellow color and print to stdout
  elif [ "$level" = "warn" ]; then
    echo -e "\033[1;33m[WARN]\033[0m $*"
  # If level is error, use red color and print to stderr
  elif [ "$level" = "error" ]; then
    echo -e "\033[1;31m[ERROR]\033[0m $*" >&2
  fi
}

function _command_check() {
  # Check if .initialized exist, if so, skip setup
  if [ -f .initialized ]; then
    cecho INFO "Already initialized, skipping prepare..."
    cecho INFO "If you want to re-run initialize, please remove .initialized file first"
    return
  fi

  sudo sysctl -w vm.max_map_count=524288
  sudo sysctl -w fs.file-max=131072
  ulimit -n 131072
  ulimit -u 8192

  # If docker not installed
  if ! command -v docker &>/dev/null; then
    cecho INFO "docker could not be found, install via https://get.docker.com/"
    echo "[+] curl https://get.docker.com/ | bash"
    curl https://get.docker.com/ | bash
  fi

  # If jq-utils not installed
  if ! command -v jq &>/dev/null; then
    cecho INFO "jq could not be found, install via apt manager"
    echo "[+] sudo apt install -y jq"
    sudo apt update
    sudo apt install -y jq
  fi

  cecho INFO "Command check complete"
  touch .initialized
  cecho INFO "Done! Command check complete, continue setup..."
}

function _prepare() {
  cecho INFO "Generating redmine.sql"

  cp redmine.sql.tmpl redmine.sql
  touch redmine.sql.log

  REDMINE_SALT=$(echo -n "$REDMINE_DB_PASSWORD" | md5sum | awk '{print $1}')
  REDMINE_HASHED_DB_PASSWORD=$(echo -n "$REDMINE_DB_PASSWORD" | sha1sum | awk '{print $1}')
  REDMINE_HASHED_PASSWORD=$(echo -n "$REDMINE_SALT$REDMINE_HASHED_DB_PASSWORD" | sha1sum | awk '{print $1}')
  REDMINE_API_KEY=$(echo $RANDOM | md5sum | head -c 20)
  REDMINE_DOMAIN_NAME=$IP_ADDR":"$REDMINE_PORT

  sed -i "s|{{hashed_password}}|$REDMINE_HASHED_PASSWORD|g" redmine.sql
  sed -i "s|{{salt}}|$REDMINE_SALT|g" redmine.sql
  sed -i "s|{{api_key}}|$REDMINE_API_KEY|g" redmine.sql
  sed -i "s|{{devops_domain_name}}|$REDMINE_DOMAIN_NAME|g" redmine.sql

  chmod 777 redmine.sql redmine.sql.log

  cecho INFO "redmine.sql and REDMINE_API_KEY generated, key is: $REDMINE_API_KEY"
}

_command_check

# If environments.json exist, do not run setup
if [ -f environments.json ]; then
  cecho WARN "environments.json exist, skip setup..."
  cecho WARN "If you want to re-setup, please remove environments.json first"
  cecho WARN "Assume you want to start up the services, start up services now..."
  docker compose up -d
  cecho INFO "Done! Exiting setup script..."
  exit 0
fi

# If docker compose ps lines count > 1, means docker compose is running
if [ "$(docker compose ps | wc -l)" -gt 1 ]; then
  cecho INFO "docker compose is running, do you want to tear down services and startup again? (y/N)"
  read -r answer
  # If answer is capital Y, convert to lower case
  answer=$(echo "$answer" | tr '[:upper:]' '[:lower:]')
  if [ "$answer" = "y" ]; then
    docker compose down -v
  else
    cecho INFO "Skip teardown, up all services now..."
    docker compose up -d
    cecho INFO "Done! Exiting setup script..."
    exit 0
  fi
fi

_prepare
docker compose up -d

function setup_gitlab() {
  cecho INFO "Waiting gitlab startup"

  # shellcheck disable=SC2034
  for i in {1..300}; do
    set +e # Disable exit on error
    STATUS_CODE="$(docker compose exec runner curl -s -k -q --max-time 5 -w '%{http_code}' -o /dev/null "http://gitlab:$GITLAB_PORT/users/sign_in")"
    set -e # Enable exit on error

    if [ "$STATUS_CODE" -eq 200 ]; then
      echo "."
      cecho INFO "Gitlab startup complete, getting initial access token"
      break
    fi
    echo -n "."
    sleep 1
  done

  # shellcheck disable=SC2002
  GITLAB_INIT_ACCESS_TOKEN="$(cat /dev/urandom | tr -dc '[:alpha:]' | fold -w "${1:-20}" | head -n 1)" # Should 20 chars long
  GITLAB_INIT_RESPONSE="$(docker compose exec gitlab gitlab-rails runner "token = User.admins.last.personal_access_tokens.create(scopes: ['api', 'read_user', 'read_repository'], name: 'IIIdevops_init_token'); token.set_token('$GITLAB_INIT_ACCESS_TOKEN'); token.save!")"

  # If success, no output
  if [ -z "$GITLAB_INIT_RESPONSE" ]; then
    cecho INFO "Initial access token created, token is: $GITLAB_INIT_ACCESS_TOKEN"
    cecho INFO "You can test token via command: "
    echo "  docker compose exec runner curl --header \"PRIVATE-TOKEN: $GITLAB_INIT_ACCESS_TOKEN\" \"http://gitlab:$GITLAB_PORT/api/v4/user\""
  else
    cecho ERROR "Initial access token creation failed, response: \n$GITLAB_INIT_RESPONSE"
    exit 1
  fi

  cecho INFO "Creating shared runner"

  GITLAB_RUNNER_REGISTRATION_TOKEN="$(docker compose exec gitlab gitlab-rails runner -e production "puts Gitlab::CurrentSettings.current_application_settings.runners_registration_token")"

  # if shared runner token is not 20 chars, means error
  if [ "${#GITLAB_RUNNER_REGISTRATION_TOKEN}" -ne 20 ]; then
    cecho ERROR "Failed to get shared runner token, response: \n$GITLAB_RUNNER_REGISTRATION_TOKEN"
    exit 1
  fi

  cecho INFO "Gitlab shared runner token retrieved, token is: $GITLAB_RUNNER_REGISTRATION_TOKEN"
  cecho INFO "Registering shared runner..."

  docker compose exec runner gitlab-runner register -n \
    --url "http://gitlab:$GITLAB_PORT/" \
    --registration-token "$GITLAB_RUNNER_REGISTRATION_TOKEN" \
    --executor "docker" \
    --docker-image alpine:latest \
    --description "shared-runner" \
    --tag-list "shared-runner" \
    --run-untagged="true" \
    --locked="false" \
    --access-level="not_protected"

  cecho INFO "Gitlab shared runner registered"
  cecho INFO "Gitlab setup complete"
}

function setup_redmine() {
  cecho INFO "Waiting redmine startup"

  # shellcheck disable=SC2034
  for i in {1..300}; do
    set +e # Disable exit on error
    STATUS_CODE="$(docker compose exec redmine curl -s -k -q --max-time 5 -w '%{http_code}' -o /dev/null http://localhost:3000)"
    set -e # Enable exit on error

    if [ "$STATUS_CODE" -eq 200 ]; then
      echo "."
      cecho INFO "Redmine startup complete"
      break
    fi
    echo -n "."
    sleep 1
  done

  cecho INFO "Importing redmine database..."
  docker compose exec rm-database psql -U postgres -d redmine_database -f /tmp/redmine.sql &>.redmine-sql-import.log
  cecho INFO "Redmine database imported, check the file .redmine-sql-import.log for more details"
  cecho INFO "Redmine setup complete"
}

function setup_sonarqube() {
  local SONARQUBE_RESPONSE
  cecho INFO "Waiting sonarqube startup"

  # shellcheck disable=SC2034
  for i in {1..60}; do
    set +e # Disable exit on error
    STATUS_CODE="$(curl -s -k -q --max-time 5 -w '%{http_code}' -o /dev/null \
      --request POST "http://localhost:$SQ_PORT/api/user_tokens/generate" \
      -H 'Authorization: Basic YWRtaW46YWRtaW4=' \
      --form 'name="API_SERVER"' \
      --form 'login="admin"')"
    set -e # Enable exit on error

    if [ "$STATUS_CODE" -eq 200 ]; then
      echo "."
      cecho INFO "Sonarqube startup complete, getting initial access token"
      break
    fi
    echo -n "."
    sleep 1
  done

  # Due to we use API to check sonarqube startup, we need to revoke the token we just created
  curl -s -k --request POST "http://localhost:$SQ_PORT/api/user_tokens/revoke" \
    -H 'Authorization: Basic YWRtaW46YWRtaW4=' \
    --form 'name="API_SERVER"' \
    --form 'login="admin"'

  SONARQUBE_RESPONSE="$(
    curl -s -k \
      --request POST "http://localhost:$SQ_PORT/api/user_tokens/generate" \
      -H 'Authorization: Basic YWRtaW46YWRtaW4=' \
      --form 'name="API_SERVER"' \
      --form 'login="admin"'
  )"

  if [ "$(echo "$SONARQUBE_RESPONSE" | jq -r '.name')" = "API_SERVER" ]; then
    SONARQUBE_ADMIN_TOKEN=$(echo "$SONARQUBE_RESPONSE" | jq -r '.token')
  else
    cecho ERROR "Failed to get sonarqube initial access token, response: \n$SONARQUBE_RESPONSE"
    exit 1
  fi

  cecho INFO "Sonarqube admin token retrieved, token is: $SONARQUBE_ADMIN_TOKEN"

  # Find default_template
  SONARQUBE_RESPONSE=$(curl -s -k \
    "http://localhost:$SQ_PORT/api/permissions/search_templates" \
    -H 'Authorization: Basic YWRtaW46YWRtaW4=')

  if ! echo "$SONARQUBE_RESPONSE" | grep -q 'templateId'; then
    cecho ERROR "Failed to get sonarqube default template, response: \n$SONARQUBE_RESPONSE"
    exit 1
  fi

  SONARQUBE_TEMPLATE_ID=$(echo "$SONARQUBE_RESPONSE" | jq -r '.defaultTemplates[0].templateId')
  cecho INFO "Sonarqube default template ID is: $SONARQUBE_TEMPLATE_ID"

  # Setting permissions
  permission_str="admin,codeviewer,issueadmin,securityhotspotadmin,scan,user"

  for permission in $(echo "$permission_str" | tr ',' ' '); do
    SONARQUBE_RESPONSE=$(
      curl -s -k \
        --request POST "http://localhost:$SQ_PORT/api/permissions/add_group_to_template" \
        -H 'Authorization: Basic YWRtaW46YWRtaW4=' \
        --form 'templateId="'"$SONARQUBE_TEMPLATE_ID"'"' \
        --form 'permission="'"$permission"'"' \
        --form 'groupName="sonar-administrators"'
    )

    if [ -n "$SONARQUBE_RESPONSE" ]; then
      cecho ERROR "Add permission to sonar-administrators failed, permission: $permission"
      cecho ERROR "Response: $SONARQUBE_RESPONSE"
    else
      cecho INFO "Add permission to sonar-administrators success, permission: $permission"
    fi

    SONARQUBE_RESPONSE=$(
      curl -s -k \
        --request POST "http://localhost:$SQ_PORT/api/permissions/remove_group_from_template" \
        -H 'Authorization: Basic YWRtaW46YWRtaW4=' \
        --form 'templateId="'"$SONARQUBE_TEMPLATE_ID"'"' \
        --form 'permission="'"$permission"'"' \
        --form 'groupName="sonar-users"'
    )

    if [ -n "$SONARQUBE_RESPONSE" ]; then
      cecho ERROR "Remove permission from sonar-users failed, permission: $permission"
      cecho ERROR "Response: $SONARQUBE_RESPONSE"
    else
      cecho INFO "Remove permission from sonar-users success, permission: $permission"
    fi
  done

  # Update admin password
  SONARQUBE_RESPONSE=$(
    curl -s -k \
      --request POST "http://localhost:$SQ_PORT/api/users/change_password" \
      -H 'Authorization: Basic YWRtaW46YWRtaW4=' \
      --form 'login="admin"' \
      --form 'password="'"$SQ_AM_PASSWORD"'"' \
      --form 'previousPassword="admin"'
  )

  if [ -n "$SONARQUBE_RESPONSE" ]; then
    cecho ERROR "Update sonarqube admin password failed, response: \n$SONARQUBE_RESPONSE"
    exit 1
  fi

  cecho INFO "Sonarqube setup complete"
}

function generate_environment_json() {
  cecho INFO "Generating environments.json..."

  # Using heredoc to generate environments.json
  cat <<EOF >environments.json
{
	"GITLAB_PRIVATE_TOKEN": "$GITLAB_INIT_ACCESS_TOKEN",
	"REDMINE_API_KEY": "$REDMINE_API_KEY",
	"SONARQUBE_ADMIN_TOKEN": "$SONARQUBE_ADMIN_TOKEN"
}
EOF

  cecho INFO "environments.json generated!"
}

function post_script() {
  local POST_RESPONSE
  POST_RESPONSE="$(docker compose exec runner curl -s -k \
    --request POST --header "PRIVATE-TOKEN: $GITLAB_INIT_ACCESS_TOKEN" \
    "http://gitlab:$GITLAB_PORT/api/v4/admin/ci/variables" \
    --form 'key=SONAR_TOKEN' \
    --form 'value="'"$SONARQUBE_ADMIN_TOKEN"'"' \
    --form 'protected=true' \
    --form 'masked=true')"

  key=$(echo "$POST_RESPONSE" | jq -r '.key')

  if [ "$key" != "SONAR_TOKEN" ]; then
    cecho ERROR "Setting Gitlab CICD variable failed, response: \n$POST_RESPONSE"
    exit 1
  fi

  SONARQUBE_HOST_URL="http://$IP_ADDR:$SQ_PORT"
  cecho INFO "Setting Gitlab CICD variable SONAR_HOST_URL to $SONARQUBE_HOST_URL"

  POST_RESPONSE="$(docker compose exec runner curl -s -k \
    --request POST --header "PRIVATE-TOKEN: $GITLAB_INIT_ACCESS_TOKEN" \
    "http://gitlab:$GITLAB_PORT/api/v4/admin/ci/variables" \
    --form 'key=SONAR_HOST_URL' \
    --form 'value="'"$SONARQUBE_HOST_URL"'"' \
    --form 'protected=true')"

  key=$(echo "$POST_RESPONSE" | jq -r '.key')

  if [ "$key" != "SONAR_HOST_URL" ]; then
    cecho ERROR "Setting Gitlab CICD variable failed, response: \n$POST_RESPONSE"
    exit 1
  fi

  cecho INFO "Post script finished!"
}

setup_gitlab
setup_redmine
setup_sonarqube
post_script
generate_environment_json

cecho INFO "Setup script finished!"
