#!/usr/bin/env bash

set -euo pipefail

# Load common functions
base_dir="$(cd "$(dirname "$0")" && pwd)"
source "$base_dir"/script/common.sh

GITLAB_RUNNER="docker compose exec runner"

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

is_wsl() {
  case "$(uname -r)" in
  *microsoft*) true ;; # WSL 2
  *Microsoft*) true ;; # WSL 1
  *) false ;;
  esac
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
    "${bin_dir:?}"/install_docker.sh

    # Set docker socket location, should auto detect
    "${bin_dir}"/generate_env.sh docker_sock
    source "$base_dir"/script/common.sh

    INFO "Install docker done! Running docker in rootless mode!"
  fi

  # docker compose version
  if ! docker compose version >/dev/null 2>&1; then
    ERROR "Make sure \e[97mdocker compose\e[0m is runnable"
    ERROR "You can install via https://docs.docker.com/compose/install/"
    ERROR "Or you can install via \e[97msudo apt install docker-compose-plugin\e[0m (depends on your docker version)"
    exit 1
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

redis_check() {
  INFO "Checking Redis requirements"

  # Check vm.overcommit_memory is enabled
  if [ "$(sudo sysctl -n vm.overcommit_memory)" -ne 1 ]; then
    INFO "vm.overcommit_memory is enabled"
    INFO "Executing command to set vm.overcommit_memory to 1..."
    sudo sysctl -w vm.overcommit_memory=1

    INFO "Persisting vm.overcommit_memory to \e[97m/etc/sysctl.d/99-redis.conf\e[0m"
    echo "vm.overcommit_memory=1" | sudo tee -a /etc/sysctl.d/99-redis.conf
  fi

  NOTICE "Redis requirements check complete"
}

prepare_check() {
  sonarqube_check
  redis_check

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
  touch HEAD.env

  REDMINE_SALT=$(echo -n "$REDMINE_DB_PASSWORD" | md5sum | awk '{print $1}')
  REDMINE_HASHED_DB_PASSWORD=$(echo -n "$REDMINE_DB_PASSWORD" | sha1sum | awk '{print $1}')
  REDMINE_HASHED_PASSWORD=$(echo -n "$REDMINE_SALT$REDMINE_HASHED_DB_PASSWORD" | sha1sum | awk '{print $1}')
  REDMINE_API_KEY="$(
    tr </dev/urandom -dc 'a-f0-9' | head -c 20
    echo
  )"

  REDMINE_DOMAIN_NAME=$IP_ADDR":"$REDMINE_PORT

  sed -i "s|{{hashed_password}}|$REDMINE_HASHED_PASSWORD|g" redmine.sql
  sed -i "s|{{salt}}|$REDMINE_SALT|g" redmine.sql
  sed -i "s|{{api_key}}|$REDMINE_API_KEY|g" redmine.sql
  sed -i "s|{{devops_domain_name}}|$REDMINE_DOMAIN_NAME|g" redmine.sql

  chmod 777 redmine.sql

  INFO "redmine.sql and REDMINE_API_KEY generated, key is: $REDMINE_API_KEY"
}

# Check if current running user is not root
if [ "$(id -u)" = 0 ]; then
  ERROR "Please run this script as non-root user"
  exit 1
fi

lsb_dist="$(get_distribution)"
# If distribution not in ubuntu or debian, exit
if [ "$lsb_dist" != "ubuntu" ] && [ "$lsb_dist" != "debian" ]; then
  # Detect WSL
  if is_wsl; then
    ERROR "WSL is currently not supported, please use Ubuntu or Debian on a virtual machine or a physical machine."
    exit 1
  fi

  ERROR "Your distribution is currently not supported, please use Ubuntu or Debian"
  exit 1
fi

command_check

# Check .env set in correct format
"${bin_dir:?}"/generate_env.sh all
source "$base_dir"/script/common.sh

# If command_check complete, check if docker socket is set
if [ -S "$DOCKER_SOCKET" ]; then
  INFO "Docker is set to \e[97m$DOCKER_SOCKET\e[0m, continue setup..."
else
  # If docker socket not set, auto detect
  "${bin_dir:?}"/generate_env.sh docker_sock
  source "$base_dir"/script/common.sh
fi

# Check have correct docker permission
if ! docker ps >/dev/null 2>&1; then
  ERROR "Docker permission check failed, please check if you have correct docker permission"
  ERROR "Maybe you try to run docker in root mode? Set the correct docker socket and try again"
  exit 1
fi

# If HEAD.env exist, do not run setup
if [ -e HEAD.env ]; then
  # If HEAD.env not empty, means setup already done
  if [ -s HEAD.env ]; then
    NOTICE "HEAD.env exist, skip setup..."
    NOTICE "If you want to re-setup, please remove HEAD.env first"
    NOTICE "Use \e[7;40;96mrm HEAD.env\e[0m to remove HEAD.env"
    NOTICE "Assume you want to start up the services, start up services now..."
    docker compose up --build --no-deps -d
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
    docker compose up --build --no-deps -d
    INFO "Done! Exiting setup script..."
    exit 0
  fi
fi

prepare_check
docker compose up --build --no-deps -d

setup_gitlab() {
  INFO "Waiting gitlab startup"

  # shellcheck disable=SC2034
  for i in {1..300}; do
    set +e # Disable exit on error
    STATUS_CODE="$($GITLAB_RUNNER curl -s -k -q --max-time 5 -w '%{http_code}' -o /dev/null "http://gitlab:$GITLAB_PORT/users/sign_in")"
    set -e # Enable exit on error

    if [ "$STATUS_CODE" -eq 200 ]; then
      echo
      INFO "Gitlab startup complete, getting initial access token"
      break
    fi
    echo -n "."
    sleep 1
  done

  GITLAB_INIT_ACCESS_TOKEN="$(
    tr </dev/urandom -dc '[:alpha:]' | head -c 20
    echo
  )" # Should 20 chars long
  GITLAB_INIT_RESPONSE="$(docker compose exec gitlab gitlab-rails runner "token = User.admins.last.personal_access_tokens.create(scopes: ['api', 'read_user', 'read_repository'], name: 'IIIdevops_init_token'); token.set_token('$GITLAB_INIT_ACCESS_TOKEN'); token.save!")"

  # If success, no output
  if [ -z "$GITLAB_INIT_RESPONSE" ]; then
    INFO "Initial access token created, token is: $GITLAB_INIT_ACCESS_TOKEN"
    INFO "You can test token via command: "
    echo "  $GITLAB_RUNNER curl --header \"PRIVATE-TOKEN: $GITLAB_INIT_ACCESS_TOKEN\" \"http://gitlab:$GITLAB_PORT/api/v4/user\""
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

  $GITLAB_RUNNER gitlab-runner register -n \
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

  "${bin_dir:?}"/add_gitlab_template.sh --token "$GITLAB_INIT_ACCESS_TOKEN" --init

  $GITLAB_RUNNER curl -s -k \
    --request PUT "http://gitlab:$GITLAB_PORT/api/v4/application/settings?allow_local_requests_from_web_hooks_and_services=true" \
    --header "PRIVATE-TOKEN: $GITLAB_INIT_ACCESS_TOKEN" >/dev/null

  $GITLAB_RUNNER curl -s -k \
    --request PUT "http://gitlab:$GITLAB_PORT/api/v4/application/settings?signup_enabled=false" \
    --header "PRIVATE-TOKEN: $GITLAB_INIT_ACCESS_TOKEN" >/dev/null

  $GITLAB_RUNNER curl -s -k \
    --request PUT "http://gitlab:$GITLAB_PORT/api/v4/application/settings?auto_devops_enabled=false" \
    --header "PRIVATE-TOKEN: $GITLAB_INIT_ACCESS_TOKEN" >/dev/null

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
  docker compose exec redmine-db psql -U postgres -d redmine_database -f /tmp/redmine.sql &>.redmine-sql-import.log
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

  # Create default quality gate
  SONARQUBE_RESPONSE=$(
    curl -s -k \
      --request POST "http://localhost:$SQ_PORT/api/qualitygates/create" \
      -H 'Authorization: Basic YWRtaW46YWRtaW4=' \
      --form 'name="Default Quality Gate"'
  )

  #  QUALITY_GATE_ID=$(echo "$SONARQUBE_RESPONSE" | jq -r '.id')

  # Create set default quality gate
  SONARQUBE_RESPONSE=$(
    curl -s -k \
      --request POST "http://localhost:$SQ_PORT/api/qualitygates/set_as_default" \
      -H 'Authorization: Basic YWRtaW46YWRtaW4=' \
      --form 'name="Default Quality Gate"'
  )

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

generate_environment_env() {
  INFO "Generating HEAD.env..."
  JWT_SECRET_KEY="$(
    tr </dev/urandom -cd 'a-f0-9' | head -c 20
    echo
  )"

  # Using heredoc to generate HEAD.env
  cat <<EOF >HEAD.env
GITLAB_PRIVATE_TOKEN=$GITLAB_INIT_ACCESS_TOKEN
JWT_SECRET_KEY=$JWT_SECRET_KEY
REDMINE_API_KEY=$REDMINE_API_KEY
SONARQUBE_ADMIN_TOKEN=$SONARQUBE_ADMIN_TOKEN
EOF

  NOTICE "HEAD.env generated!"
}

print_urls() {
  INFO "The deployment of III-DevOps-Lite services has been completed. Please try to connect to the following URL."
  INFO "Gitlab: http://$IP_ADDR:$GITLAB_PORT"
  INFO "Sonarqube: http://$IP_ADDR:$SQ_PORT"
  INFO "IIIdevops: http://$IP_ADDR"
}

post_script() {
  local POST_RESPONSE
  POST_RESPONSE="$(
    $GITLAB_RUNNER curl -s -k \
      --request POST "http://gitlab:$GITLAB_PORT/api/v4/admin/ci/variables" \
      --header "PRIVATE-TOKEN: $GITLAB_INIT_ACCESS_TOKEN" \
      --form 'key=SONAR_TOKEN' \
      --form 'value="'"$SONARQUBE_ADMIN_TOKEN"'"' \
      --form 'protected=false' \
      --form 'masked=true'
  )"

  key=$(echo "$POST_RESPONSE" | jq -r '.key')

  if [ "$key" != "SONAR_TOKEN" ]; then
    ERROR "Setting Gitlab CICD variable failed, response: \n$POST_RESPONSE"
    exit 1
  fi

  SONARQUBE_HOST_URL="http://$IP_ADDR:$SQ_PORT"
  INFO "Setting Gitlab CICD variable SONAR_HOST_URL to $SONARQUBE_HOST_URL"

  POST_RESPONSE="$(
    $GITLAB_RUNNER curl -s -k \
      --request POST "http://gitlab:$GITLAB_PORT/api/v4/admin/ci/variables" \
      --header "PRIVATE-TOKEN: $GITLAB_INIT_ACCESS_TOKEN" \
      --form 'key=SONAR_HOST_URL' \
      --form 'value="'"$SONARQUBE_HOST_URL"'"' \
      --form 'protected=false'
  )"

  key=$(echo "$POST_RESPONSE" | jq -r '.key')

  if [ "$key" != "SONAR_HOST_URL" ]; then
    ERROR "Setting Gitlab CICD variable failed, response: \n$POST_RESPONSE"
    exit 1
  fi

  API_ORIGIN="http://$IP_ADDR:$III_PORT"
  POST_RESPONSE="$(
    $GITLAB_RUNNER curl -s -k \
      --request POST "http://gitlab:$GITLAB_PORT/api/v4/admin/ci/variables" \
      --header "PRIVATE-TOKEN: $GITLAB_INIT_ACCESS_TOKEN" \
      --form 'key=API_ORIGIN' \
      --form 'value="'"$API_ORIGIN"'"' \
      --form 'protected=false'
  )"

  key=$(echo "$POST_RESPONSE" | jq -r '.key')

  if [ "$key" != "API_ORIGIN" ]; then
    ERROR "Setting Gitlab CICD variable failed, response: \n$POST_RESPONSE"
    exit 1
  fi

  # Clean up image once a day
  docker volume ls -qf dangling=true | xargs --no-run-if-empty docker volume rm

  NOTICE "Post script finished!"
}

setup_gitlab
setup_redmine
setup_sonarqube
post_script
generate_environment_env
print_urls
