#!/usr/bin/env bash

set -eu

# Load common functions
base_dir="$(cd "$(dirname "$0")" && pwd)"
source "$base_dir"/script/common.sh

get_distribution() {
  # Copy from https://get.docker.com/
  lsb_dist=""
  # Every system that we officially support has /etc/os-release
  if [ -r /etc/os-release ]; then
    lsb_dist="$(. /etc/os-release && echo "$ID")"
  fi
  # Returning an empty string here should be alright since the
  # case statements don't act unless you provide an actual value
  echo "$lsb_dist" | tr '[:upper:]' '[:lower:]'
}

command_check() {
  # Check if .initialized exist, if so, skip setup
  if [ -f .initialized ]; then
    INFO "Already initialized, skipping prepare..."
    INFO "If you want to re-run initialize, please remove .initialized file first"
    return
  fi

  if ! command_exists curl; then
    INFO "curl could not be found, install via apt manager"
    echo "[+] sudo apt-get update && sudo apt-get install -y curl"
    sudo apt-get update -qq >/dev/null
    sudo apt-get install -y -qq curl >/dev/null
    INFO "Install curl done!"
  fi

  if ! command_exists jq; then
    INFO "jq could not be found, install via apt manager"
    echo "[+] sudo apt-get update && sudo apt-get install -y jq"
    sudo apt-get update -qq >/dev/null
    sudo apt-get install -y -qq jq >/dev/null
    INFO "Install jq done!"
  fi

  if ! command_exists docker; then
    INFO "docker could not be found, install via https://get.docker.com/"
    echo "[+] curl -s https://get.docker.com/ | bash"
    curl -s https://get.docker.com/ | bash

    INFO "Setting up docker in rootless mode..."
    sudo apt-get update -qq >/dev/null
    sudo apt-get install -y -qq uidmap >/dev/null
    dockerd-rootless-setuptool.sh install

    BIN="$(dirname "$(command -v dockerd-rootless.sh)")"

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
        INFO "dbus service is active, continue setup..."
        break
      fi
    done

    INFO "Install docker done! Running docker in rootless mode!"
  fi

  INFO "Command check complete"
  touch .initialized
  INFO "Done! Command check complete, continue setup..."
}

sonarqube_check() {
  INFO "Checking sonarqube requirements"

  # Check vm.max_map_count is greater than or equal to 524288
  if [ "$(sudo sysctl -n vm.max_map_count)" -lt 524288 ]; then
    INFO "vm.max_map_count is less than 524288"
    INFO "Executing command to set vm.max_map_count up to 524288..."
    sudo sysctl -w vm.max_map_count=524288

    INFO "Persisting vm.max_map_count to \e[97m/etc/sysctl.d/99-sonarqube.conf\e[0m"
    echo "vm.max_map_count=524288" | sudo tee -a /etc/sysctl.d/99-sonarqube.conf
  fi

  # Check fs.file-max is greater than or equal to 131072
  if [ "$(sudo sysctl -n fs.file-max)" -lt 131072 ]; then
    INFO "fs.file-max is less than 131072"
    INFO "Executing command to set fs.file-max up to 131072..."
    sudo sysctl -w fs.file-max=131072

    INFO "Persisting fs.file-max to \e[97m/etc/sysctl.d/99-sonarqube.conf\e[0m"
    echo "fs.file-max=131072" | sudo tee -a /etc/sysctl.d/99-sonarqube.conf
  fi

  # Check at least 131072 file descriptors are available
  if [ "$(ulimit -n)" -lt 131072 ]; then
    INFO "ulimit -n is less than 131072"
    INFO "Executing command to set ulimit -n up to 131072..."
    ulimit -n 131072
    INFO "Done!"
  fi

  # Check at least 8192 threads are available
  if [ "$(ulimit -u)" -lt 8192 ]; then
    INFO "ulimit -u is less than 8192"
    INFO "Executing command to set ulimit -u up to 8192..."
    ulimit -u 8192
    INFO "Done!"
  fi

  NOTICE "Sonarqube requirements check complete"
}

prepare_check() {
  sonarqube_check

  # Check IP_ADDR is set
  if [ -z "$IP_ADDR" ]; then
    ERROR "IP_ADDR is not set, please modify \e[97m.env\e[0m file first and run this script again"
    exit 1
  fi

  INFO "Your ip address is currently set to: \e[97;104m$IP_ADDR\e[0m, if you want to change it, please modify \e[97m.env\e[0m file"
  INFO "Sleeping 5 seconds, press Ctrl+C to cancel"
  sleep 5

  INFO "Generating redmine.sql"

  cp redmine.sql.tmpl redmine.sql
  touch environments.json

  REDMINE_SALT=$(echo -n "$REDMINE_DB_PASSWORD" | md5sum | awk '{print $1}')
  REDMINE_HASHED_DB_PASSWORD=$(echo -n "$REDMINE_DB_PASSWORD" | sha1sum | awk '{print $1}')
  REDMINE_HASHED_PASSWORD=$(echo -n "$REDMINE_SALT$REDMINE_HASHED_DB_PASSWORD" | sha1sum | awk '{print $1}')
  REDMINE_API_KEY="$(tr -dc 'a-f0-9' </dev/urandom | fold -w 20 | head -n 1)"

  REDMINE_DOMAIN_NAME=$IP_ADDR":"$REDMINE_PORT

  sed -i "s|{{hashed_password}}|$REDMINE_HASHED_PASSWORD|g" redmine.sql
  sed -i "s|{{salt}}|$REDMINE_SALT|g" redmine.sql
  sed -i "s|{{api_key}}|$REDMINE_API_KEY|g" redmine.sql
  sed -i "s|{{devops_domain_name}}|$REDMINE_DOMAIN_NAME|g" redmine.sql

  chmod 777 redmine.sql

  INFO "redmine.sql and REDMINE_API_KEY generated, key is: $REDMINE_API_KEY"
}

lsb_dist="$(get_distribution)"
# If distribution not in ubuntu or debian, exit
if [ "$lsb_dist" != "ubuntu" ] && [ "$lsb_dist" != "debian" ]; then
  ERROR "Your distribution is currently not supported, please use Ubuntu or Debian"
  exit 1
fi

command_check

# If environments.json exist, do not run setup
if [ -e environments.json ]; then
  # If environments.json not empty, means setup already done
  if [ -s environments.json ]; then
    NOTICE "environments.json exist, skip setup..."
    NOTICE "If you want to re-setup, please remove environments.json first"
    NOTICE "Use \e[7;40;96mrm environments.json\e[0m to remove environments.json"
    NOTICE "Assume you want to start up the services, start up services now..."
    docker compose up -d
    INFO "Done! Exiting setup script..."
    exit 0
  fi
fi

# If docker compose ps lines count > 1, means docker compose is running
if [ "$(docker compose ps | wc -l)" -gt 1 ]; then
  INFO "docker compose is running, do you want to tear down services and startup again? (y/N)"
  read -r answer
  # If answer is capital Y, convert to lower case
  answer=$(echo "$answer" | tr '[:upper:]' '[:lower:]')
  if [ "$answer" = "y" ]; then
    docker compose down -v
  else
    INFO "Skip teardown, up all services now..."
    docker compose up -d
    INFO "Done! Exiting setup script..."
    exit 0
  fi
fi

prepare_check
docker compose up -d

setup_gitlab() {
  INFO "Waiting gitlab startup"

  # shellcheck disable=SC2034
  for i in {1..300}; do
    set +e # Disable exit on error
    STATUS_CODE="$(docker compose exec runner curl -s -k -q --max-time 5 -w '%{http_code}' -o /dev/null "http://gitlab:$GITLAB_PORT/users/sign_in")"
    set -e # Enable exit on error

    if [ "$STATUS_CODE" -eq 200 ]; then
      echo
      INFO "Gitlab startup complete, getting initial access token"
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
    INFO "Initial access token created, token is: $GITLAB_INIT_ACCESS_TOKEN"
    INFO "You can test token via command: "
    echo "  docker compose exec runner curl --header \"PRIVATE-TOKEN: $GITLAB_INIT_ACCESS_TOKEN\" \"http://gitlab:$GITLAB_PORT/api/v4/user\""
  else
    ERROR "Initial access token creation failed, response: \n$GITLAB_INIT_RESPONSE"
    exit 1
  fi

  INFO "Creating shared runner"

  GITLAB_RUNNER_REGISTRATION_TOKEN="$(docker compose exec gitlab gitlab-rails runner -e production "puts Gitlab::CurrentSettings.current_application_settings.runners_registration_token")"

  # if shared runner token is not 20 chars, means error
  if [ "${#GITLAB_RUNNER_REGISTRATION_TOKEN}" -ne 20 ]; then
    ERROR "Failed to get shared runner token, response: \n$GITLAB_RUNNER_REGISTRATION_TOKEN"
    exit 1
  fi

  INFO "Gitlab shared runner token retrieved, token is: $GITLAB_RUNNER_REGISTRATION_TOKEN"
  INFO "Registering shared runner..."

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

  INFO "Gitlab shared runner registered"
  NOTICE "Gitlab setup complete"
}

setup_redmine() {
  INFO "Waiting redmine startup"

  # shellcheck disable=SC2034
  for i in {1..300}; do
    set +e # Disable exit on error
    STATUS_CODE="$(docker compose exec redmine curl -s -k -q --max-time 5 -w '%{http_code}' -o /dev/null http://localhost:3000)"
    set -e # Enable exit on error

    if [ "$STATUS_CODE" -eq 200 ]; then
      echo
      INFO "Redmine startup complete"
      break
    fi
    echo -n "."
    sleep 1
  done

  INFO "Importing redmine database..."
  docker compose exec rm-database psql -U postgres -d redmine_database -f /tmp/redmine.sql &>.redmine-sql-import.log
  INFO "Redmine database imported, check the file \e[97m.redmine-sql-import.log\e[0m for more details"
  NOTICE "Redmine setup complete"
}

setup_sonarqube() {
  local SONARQUBE_RESPONSE
  INFO "Waiting sonarqube startup"

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
      echo
      INFO "Sonarqube startup complete, getting initial access token"
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
    ERROR "Failed to get sonarqube initial access token, response: \n$SONARQUBE_RESPONSE"
    exit 1
  fi

  INFO "Sonarqube admin token retrieved, token is: $SONARQUBE_ADMIN_TOKEN"

  # Find default_template
  SONARQUBE_RESPONSE=$(curl -s -k \
    "http://localhost:$SQ_PORT/api/permissions/search_templates" \
    -H 'Authorization: Basic YWRtaW46YWRtaW4=')

  if ! echo "$SONARQUBE_RESPONSE" | grep -q 'templateId'; then
    ERROR "Failed to get sonarqube default template, response: \n$SONARQUBE_RESPONSE"
    exit 1
  fi

  SONARQUBE_TEMPLATE_ID=$(echo "$SONARQUBE_RESPONSE" | jq -r '.defaultTemplates[0].templateId')
  INFO "Sonarqube default template ID is: $SONARQUBE_TEMPLATE_ID"

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
      ERROR "Add permission to sonar-administrators failed, permission: $permission"
      ERROR "Response: $SONARQUBE_RESPONSE"
    else
      INFO "Add permission to sonar-administrators success, permission: $permission"
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
      ERROR "Remove permission from sonar-users failed, permission: $permission"
      ERROR "Response: $SONARQUBE_RESPONSE"
    else
      INFO "Remove permission from sonar-users success, permission: $permission"
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
    ERROR "Update sonarqube admin password failed, response: \n$SONARQUBE_RESPONSE"
    exit 1
  fi

  NOTICE "Sonarqube setup complete"
}

generate_environment_json() {
  INFO "Generating environments.json..."
  JWT_SECRET_KEY="$(tr -dc 'a-f0-9' </dev/urandom | fold -w 20 | head -n 1)"

  # Using heredoc to generate environments.json
  cat <<EOF >environments.json
{
	"GITLAB_PRIVATE_TOKEN": "$GITLAB_INIT_ACCESS_TOKEN",
	"JWT_SECRET_KEY": "$JWT_SECRET_KEY",
	"REDMINE_API_KEY": "$REDMINE_API_KEY",
	"SONARQUBE_ADMIN_TOKEN": "$SONARQUBE_ADMIN_TOKEN"
}
EOF

  NOTICE "environments.json generated!"
}

post_script() {
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
    ERROR "Setting Gitlab CICD variable failed, response: \n$POST_RESPONSE"
    exit 1
  fi

  SONARQUBE_HOST_URL="http://$IP_ADDR:$SQ_PORT"
  INFO "Setting Gitlab CICD variable SONAR_HOST_URL to $SONARQUBE_HOST_URL"

  POST_RESPONSE="$(docker compose exec runner curl -s -k \
    --request POST --header "PRIVATE-TOKEN: $GITLAB_INIT_ACCESS_TOKEN" \
    "http://gitlab:$GITLAB_PORT/api/v4/admin/ci/variables" \
    --form 'key=SONAR_HOST_URL' \
    --form 'value="'"$SONARQUBE_HOST_URL"'"' \
    --form 'protected=true')"

  key=$(echo "$POST_RESPONSE" | jq -r '.key')

  if [ "$key" != "SONAR_HOST_URL" ]; then
    ERROR "Setting Gitlab CICD variable failed, response: \n$POST_RESPONSE"
    exit 1
  fi

  API_ORIGIN="http://$IP_ADDR:$III_PORT"
  POST_RESPONSE="$(docker compose exec runner curl -s -k \
    --request POST --header "PRIVATE-TOKEN: $GITLAB_INIT_ACCESS_TOKEN" \
    "http://gitlab:$GITLAB_PORT/api/v4/admin/ci/variables" \
    --form 'key=API_ORIGIN' \
    --form 'value="'"$API_ORIGIN"'"' \
    --form 'protected=true')"

  key=$(echo "$POST_RESPONSE" | jq -r '.key')

  if [ "$key" != "API_ORIGIN" ]; then
    ERROR "Setting Gitlab CICD variable failed, response: \n$POST_RESPONSE"
    exit 1
  fi

  NOTICE "Post script finished!"
}

setup_gitlab
setup_redmine
setup_sonarqube
post_script
generate_environment_json

INFO "Setup script finished!"
