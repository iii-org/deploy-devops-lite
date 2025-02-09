#!/usr/bin/env bash

# This script is used to set up each service
spinner() {
  SPINNING=true
  SPIN_CURRENT=$1 # Process Id of the previous running command

  local spin='-\|/'
  local charWidth=1

  local i=0
  tput civis # cursor invisible

  while kill -0 "$SPIN_CURRENT" 2>/dev/null; do
    local i=$(((i + "${charWidth}") % ${#spin}))

    echo -en "${spin:$i:$charWidth}"
    echo -en "\033[1D"

    sleep .1
  done

  tput cnorm
  wait "$SPIN_CURRENT" # capture exit code
  return $?
}

check_service_up() {
  local service_name="$1"
  local url="$2"
  local url_params="${*:3}"

  local timeout=600
  local STATUS_CODE

  INFO "⏳ Waiting for $service_name to be ready..."

  (
    while true; do
      if [[ "$timeout" -le 0 ]]; then
        ERROR "⏳ Timeout while waiting for $service_name to be ready"
        ERROR "🔚 Last status code: ${RED}$STATUS_CODE${NOFORMAT}"
        ERROR "🌐 Request URL: ${WHITE}$url${NOFORMAT}"
        exit 1
      fi

      set +e # Disable exit on error
      STATUS_CODE=$(
        eval "curl -s -k -q --max-time 5 -w '%{http_code}' -o /dev/null $url $url_params"
      )
      set -e # Enable exit on error

      if [[ "$STATUS_CODE" -eq "200" ]]; then
        INFO "✅ $service_name is ready"
        break
      fi

      timeout=$((timeout - 1))
      sleep 1
    done
  ) &
  spinner $!
}

get_service_authority() {
  # Convert to lower
  local service_name="${1,,}"

  # Create a local map, key is service name, value is service port
  local -A service_port_map
  service_port_map["gitlab"]="$PORT_GITLAB"
  service_port_map["redmine"]="$PORT_REDMINE"
  service_port_map["sonarqube"]="$PORT_SONARQUBE"
  service_port_map["api"]="$PORT_III_API"
  service_port_map["ui"]="$PORT_III_UI"
  service_port_map["minio"]="$PORT_MINIO"

  if [[ "$MODE" == "IP" ]]; then
    echo "$IP_ADDR:${service_port_map[$service_name]}"
  else
    service_name="DOMAIN_${service_name^^}"
    echo "${!service_name}"
  fi
}

get_service_url() {
  local service_name="$1"
  local service_url
  service_url="$(get_service_authority "$service_name")"

  if [[ "$MODE" == "IP" ]]; then
    echo "http://$service_url"
  else
    echo "https://$service_url"
  fi
}

setup_gitlab_variable() {
  local KEY="$1"
  local VALUE="$2"
  local PROTECTED=false
  local MASKED="${3:-true}"

  local RESPONSE
  local JQ_KEY

  local DATA
  DATA="$(
    jq -n \
      --arg key "$KEY" \
      --arg value "$VALUE" \
      --arg protected "$PROTECTED" \
      --arg masked "$MASKED" \
      '{key: $key, value: $value, protected: $protected, masked: $masked}'
  )"

  RESPONSE="$(
    curl -s -k -X POST "$(get_service_url "gitlab")/api/v4/admin/ci/variables" \
      -H "PRIVATE-TOKEN: $GITLAB_INIT_TOKEN" \
      -H "Content-Type: application/json" \
      -d "$DATA"
  )"

  JQ_KEY=$(echo "$RESPONSE" | jq -r '.key')

  if [[ "$JQ_KEY" != "$KEY" ]]; then
    ERROR "❌ Setting Gitlab CICD variable ${WHITE}$KEY${NOFORMAT} failed, response:"
    ERROR "$RESPONSE"
    exit 1
  fi

  INFO "🔑 Gitlab CICD variable ${WHITE}$KEY${NOFORMAT} set successfully!"
}

setup_gitlab() {
  local gitlab_url
  gitlab_url="$(get_service_url "gitlab")"
  minio_url="$(get_service_url "minio")"

  check_service_up "GitLab" \
    "-X GET ${gitlab_url}/-/readiness?all=1"

  INFO "🔧 Setting up GitLab..."

  local INIT_TOKEN
  INIT_TOKEN="glpat-$(generate_random_string 20)"
  local RESPONSE
  expires_at=$(date -d "+1 year" +"%Y-%m-%d")
  RESPONSE="$(
    $DOCKER_COMPOSE_COMMAND exec gitlab \
      gitlab-rails runner "token = User.admins.last.personal_access_tokens.create(scopes: ['api', 'read_user', 'read_repository'], name: 'IIIdevops_init_token', expires_at: '$expires_at'); token.set_token('$INIT_TOKEN'); token.save!"
  )"

  if [[ -z "$RESPONSE" ]]; then
    INFO "🔑 GitLab init token is: ${ORANGE}$INIT_TOKEN${NOFORMAT}"
    INFO "📅 Token expired at: $expires_at"
    INFO "🛠️ You can test it via:"
    INFO "   ${YELLOW}curl -H \"PRIVATE-TOKEN: $INIT_TOKEN\" \"$gitlab_url/api/v4/users\"${NOFORMAT}"
    variable_write "GITLAB_INIT_TOKEN" "$INIT_TOKEN"
  else
    ERROR "❌ Failed to get GitLab init token"
    ERROR "$RESPONSE"
    exit 1
  fi

  # Create shared runner
  INFO "🔧 Creating shared runner..."
  local REGISTRATOR_TOKEN
  REGISTRATOR_TOKEN=$(
    curl --silent --show-error --request POST \
      --header "PRIVATE-TOKEN: $INIT_TOKEN" \
      --header "Content-Type: application/json" \
      --data '{
        "runner_type": "instance_type",
        "description": "shared-runner",
        "tag_list": ["shared-runner"],
        "run_untagged": true,
        "locked": false,
        "access_level": "not_protected"
      }' \
      "$gitlab_url/api/v4/user/runners" | jq -r '.token'
  )

  # Check if the token was successfully retrieved
  if [ -z "$REGISTRATOR_TOKEN" ]; then
    echo "Failed to retrieve registrator token."
    exit 1
  else
    echo "Registrator token retrieved successfully: $REGISTRATOR_TOKEN"
  fi

  INFO "🔑 GitLab shared runner registration token is: ${ORANGE}$REGISTRATOR_TOKEN${NOFORMAT}"
  variable_write "GITLAB_REGISTRATOR_TOKEN" "$REGISTRATOR_TOKEN"

  # Register shared runner
  INFO "🔧 Registering shared runner..."

  $DOCKER_COMPOSE_COMMAND exec runner \
    gitlab-runner register -n \
    --url "$gitlab_url" \
    --token "$REGISTRATOR_TOKEN" \
    --executor "docker" \
    --docker-image alpine:latest

  INFO "✅ Registered shared runner"
  
  $DOCKER_COMPOSE_COMMAND exec runner \
    curl -s -k -X PUT "$gitlab_url/api/v4/application/settings?allow_local_requests_from_web_hooks_and_services=true" \
    -H "PRIVATE-TOKEN: $REGISTRATOR_TOKEN" >/dev/null

  $DOCKER_COMPOSE_COMMAND exec runner \
    curl -s -k -X PUT "$gitlab_url/api/v4/application/settings?signup_enabled=false" \
    -H "PRIVATE-TOKEN: $REGISTRATOR_TOKEN" >/dev/null

  $DOCKER_COMPOSE_COMMAND exec runner \
    curl -s -k -X PUT "$gitlab_url/api/v4/application/settings?auto_devops_enabled=false" \
    -H "PRIVATE-TOKEN: $REGISTRATOR_TOKEN" >/dev/null

  $DOCKER_COMPOSE_COMMAND exec runner /bin/bash -c "
  cp /etc/gitlab-runner/config.toml /etc/gitlab-runner/config.toml.backup
  sed -i \"/\[runners\.cache\]/,/\[runners\.docker\]/ c\  [runners.cache]\\n    MaxUploadedArchiveSize = 0\\n    Type = \\\"s3\\\"\\n    Path = \\\"gitlab-runner\\\"\\n    Shared = true\\n    [runners.cache.s3]\\n      ServerAddress = \\\"${minio_url#http://}\\\"\\n      AccessKey = \\\"${MINIO_ACCESS_KEY}\\\"\\n      SecretKey = \\\"${MINIO_SECRET_KEY}\\\"\\n      BucketName = \\\"runner-cache\\\"\\n      BucketLocation = \\\"us-east-1\\\"\\n      Insecure = true\\n    [runners.cache.gcs]\\n    [runners.cache.azure]\\n  [runners.docker]\" /etc/gitlab-runner/config.toml
  "

  INFO "🔧 Configured GitLab runner cache"
  $DOCKER_COMPOSE_COMMAND exec runner /bin/bash -c "cat /etc/gitlab-runner/config.toml"

  $DOCKER_COMPOSE_COMMAND restart runner

  setup_gitlab_variable "DEVOPS_API" "$(get_service_url "api")" false
  setup_gitlab_variable "SONAR_TOKEN" "$SONARQUBE_ADMIN_TOKEN"
  setup_gitlab_variable "SONAR_URL" "$(get_service_url "sonarqube")" false

  INFO "✅ GitLab setup finished!"
}

setup_redmine() {
  local redmine_url
  redmine_url="$(get_service_url "redmine")"

  check_service_up "Redmine" \
    "-X GET ${redmine_url}"

  INFO "🔧 Setting up Redmine..."

  INFO "📥 Importing Redmine database..."

  # Make sure redmine-db service is exist before importing database
  $DOCKER_COMPOSE_COMMAND exec -T redmine-db psql -U postgres -d redmine_database -f /tmp/redmine.sql 1>"$PROJECT_DIR/generate/redmine-db.log"

  INFO "✅ Imported Redmine database"

  INFO "✅ Redmine setup finished!"
}

setup_sonarqube() {
  local sonarqube_url
  sonarqube_url="$(get_service_url "sonarqube")"

  check_service_up "SonarQube" \
    "-X POST ${sonarqube_url}/api/user_tokens/generate" \
    "-H 'Authorization: Basic YWRtaW46YWRtaW4='" \
    "--form 'name=\"API_SERVER\"'" \
    "--form 'login=\"admin\"'"

  INFO "🔧 Setting up SonarQube..."

  # We need to revoke the token we used to check service up
  curl -s -k -X POST "$sonarqube_url/api/user_tokens/revoke" \
    -H 'Authorization: Basic YWRtaW46YWRtaW4=' \
    --form 'name="API_SERVER"' \
    --form 'login="admin"'

  local RESPONSE
  RESPONSE="$(
    curl -s -k -X POST "$sonarqube_url/api/user_tokens/generate" \
      -H 'Authorization: Basic YWRtaW46YWRtaW4=' \
      --form 'name="API_SERVER"' \
      --form 'login="admin"'
  )"

  local ADMIN_TOKEN
  if [[ "$(echo "$RESPONSE" | jq -r '.name')" = "API_SERVER" ]]; then
    ADMIN_TOKEN="$(echo "$RESPONSE" | jq -r '.token')"
  else
    ERROR "Failed to get SonarQube admin token"
    ERROR "$RESPONSE"
    exit 1
  fi

  INFO "🔑 SonarQube admin token is: ${ORANGE}$ADMIN_TOKEN${NOFORMAT}"
  variable_write "SONARQUBE_ADMIN_TOKEN" "$ADMIN_TOKEN"

  RESPONSE="$(curl -s -k "$sonarqube_url/api/permissions/search_templates" \
    -H 'Authorization: Basic YWRtaW46YWRtaW4=')"

  local SONARQUBE_TEMPLATE_ID
  SONARQUBE_TEMPLATE_ID="$(echo "$RESPONSE" | jq -r '.defaultTemplates[0].templateId')"

  # Make sure template ID exists
  if [[ -z "$SONARQUBE_TEMPLATE_ID" ]] || [[ "$SONARQUBE_TEMPLATE_ID" = "null" ]]; then
    ERROR "Failed to get SonarQube default template ID"
    ERROR "$RESPONSE"
    exit 1
  fi

  INFO "🔑 SonarQube default template ID is: ${ORANGE}$SONARQUBE_TEMPLATE_ID${NOFORMAT}"

  # Execute the permissions
  local PERMISSION_LIST="admin,codeviewer,issueadmin,securityhotspotadmin,scan,user"

  for PERMISSION in $(echo "$PERMISSION_LIST" | tr ',' ' '); do
    RESPONSE="$(
      curl -s -k -X POST "$sonarqube_url/api/permissions/add_group_to_template" \
        -H 'Authorization: Basic YWRtaW46YWRtaW4=' \
        --form 'templateId="'"$SONARQUBE_TEMPLATE_ID"'"' \
        --form 'permission="'"$PERMISSION"'"' \
        --form 'groupName="sonar-administrators"'
    )"

    if [[ -n "$RESPONSE" ]]; then
      ERROR "❌ Failed to add permission ${CYAN}$PERMISSION${NOFORMAT} to group sonar-administrators"
      ERROR "$RESPONSE"
      exit 1
    else
      INFO "✅ Added permission ${CYAN}$PERMISSION${NOFORMAT} to group sonar-administrators"
    fi

    RESPONSE="$(
      curl -s -k -X POST "$sonarqube_url/api/permissions/remove_group_from_template" \
        -H 'Authorization: Basic YWRtaW46YWRtaW4=' \
        --form 'templateId="'"$SONARQUBE_TEMPLATE_ID"'"' \
        --form 'permission="'"$PERMISSION"'"' \
        --form 'groupName="sonar-users"'
    )"

    if [[ -n "$RESPONSE" ]]; then
      ERROR "❌ Failed to add permission ${CYAN}$PERMISSION${NOFORMAT} to group sonar-users"
      ERROR "$RESPONSE"
      exit 1
    else
      INFO "✅ Added permission ${CYAN}$PERMISSION${NOFORMAT} to group sonar-users"
    fi
  done

  # Create default quality gate
  RESPONSE="$(
    curl -s -k -X POST "$sonarqube_url/api/qualitygates/create" \
      -H 'Authorization: Basic YWRtaW46YWRtaW4=' \
      --form 'name="Default Quality Gate"'
  )"
  # QUALITY_GATE_ID=$(echo "$SONARQUBE_RESPONSE" | jq -r '.id')

  RESPONSE="$(
    curl -s -k -X POST "$sonarqube_url/api/qualitygates/set_as_default" \
      -H 'Authorization: Basic YWRtaW46YWRtaW4=' \
      --form 'name="Default Quality Gate"'
  )"

  INFO "✅ Created default quality gate"

  # Update admin password
  INFO "🔑 Updating SonarQube admin password"
  RESPONSE="$(
    curl -s -k -X POST "$sonarqube_url/api/users/change_password" \
      -H 'Authorization: Basic YWRtaW46YWRtaW4=' \
      --form 'login="admin"' \
      --form 'password="'"$SQ_AM_PASSWORD"'"' \
      --form 'previousPassword="admin"'
  )"

  if [[ -n "$RESPONSE" ]]; then
    ERROR "❌ Failed to update SonarQube admin password"
    ERROR "$RESPONSE"
    exit 1
  else
    INFO "✅ Updated SonarQube admin password"
  fi

  INFO "✅ SonarQube setup finished!"
}

setup_minio() {
  local minio_url
  minio_url="$(get_service_url "minio")"

  INFO "🔧 Setting up Minio..."

  # Create bucket
  INFO "📁 Creating bucket..."
  $DOCKER_COMPOSE_COMMAND exec minio bash -c  "
    mc alias set myminio $minio_url $MINIO_ACCESS_KEY $MINIO_SECRET_KEY && \
    mc mb myminio/runner-cache
  "

  INFO "✅ Minio setup finished!"
}