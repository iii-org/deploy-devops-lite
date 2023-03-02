#!/usr/bin/env bash

set -e

sudo sysctl -w vm.max_map_count=524288
sudo sysctl -w fs.file-max=131072
ulimit -n 131072
ulimit -u 8192

# If docker not installed
if ! command -v docker &>/dev/null; then
  echo "[INFO] docker could not be found, install via https://get.docker.com/"
  echo "+ curl https://get.docker.com/ | bash"
  curl https://get.docker.com/ | bash

#  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -
#  sudo add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable"
#  sudo apt-get install docker-ce=5:19.03.14~3-0~ubuntu-focal docker-ce-cli=5:19.03.14~3-0~ubuntu-focal docker-compose-plugin containerd.io -y
fi

## Generate redmine.sql
# shellcheck disable=SC2046
export $(grep -v '^#' .env | xargs)

cp redmine.sql.tmpl redmine.sql
touch redmine.sql.log

salt=$(echo -n "$REDMINE_DB_PASSWORD" | md5sum | awk '{print $1}')
hash_redmine_db_pwd=$(echo -n "$REDMINE_DB_PASSWORD" | sha1sum | awk '{print $1}')
hashed_password=$(echo -n "$salt$hash_redmine_db_pwd" | sha1sum | awk '{print $1}')
api_key=$(echo $RANDOM | md5sum | head -c 20)
redmine_domain_name=$IP_ADDR":"$REDMINE_PORT

sed -i "s|{{hashed_password}}|$hashed_password|g" redmine.sql
sed -i "s|{{salt}}|$salt|g" redmine.sql
sed -i "s|{{api_key}}|$api_key|g" redmine.sql
sed -i "s|{{devops_domain_name}}|$redmine_domain_name|g" redmine.sql

chmod 777 redmine.sql redmine.sql.log

docker compose up -d

echo "[INFO] Waiting gitlab startup"

# shellcheck disable=SC2034
for i in {1..300}; do
  set +e # Disable exit on error
  STATUS_CODE="$(docker compose exec runner curl -s -k -q --max-time 5 -w '%{http_code}' -o /dev/null http://gitlab:32080/users/sign_in)"
  set -e # Enable exit on error

  if [ "$STATUS_CODE" -eq 200 ]; then
    echo -e "\n[INFO] Gitlab startup complete, getting initial access token"
    break
  fi
  echo -n "."
  sleep 1
done

# shellcheck disable=SC2002
ACCESS_TOKEN="$(cat /dev/urandom | tr -dc '[:alpha:]' | fold -w "${1:-20}" | head -n 1)" # Should 20 chars long
RESPONSE="$(docker compose exec gitlab gitlab-rails runner "token = User.admins.last.personal_access_tokens.create(scopes: ['api', 'read_user', 'read_repository'], name: 'IIIdevops_init_token'); token.set_token('$ACCESS_TOKEN'); token.save!")"

# If success, no output
if [ -z "$RESPONSE" ]; then
  echo "[INFO] Initial access token created, token is: $ACCESS_TOKEN"
  echo "[INFO] You can test token via command: "
  echo "  docker compose exec runner curl --header \"PRIVATE-TOKEN: $ACCESS_TOKEN\" \"http://gitlab:32080/api/v4/user\""
else
  echo -e "[ERROR] Initial access token creation failed, response: \n$RESPONSE"
  exit 1
fi

echo "[INFO] Creating shared runner"

RUNNER_REGISTRATION_TOKEN="$(docker compose exec gitlab gitlab-rails runner -e production "puts Gitlab::CurrentSettings.current_application_settings.runners_registration_token")"

# if shared runner token is not 20 chars, means error
if [ "${#RUNNER_REGISTRATION_TOKEN}" -ne 20 ]; then
  echo -e "[ERROR] Failed to get shared runner token, response: \n$RUNNER_REGISTRATION_TOKEN"
  exit 1
fi

echo "[INFO] Shared runner token retrieved, token is: $RUNNER_REGISTRATION_TOKEN"
echo "[INFO] Registering shared runner"

docker compose exec runner gitlab-runner register -n \
  --url "http://gitlab:32080/" \
  --registration-token "$RUNNER_REGISTRATION_TOKEN" \
  --executor "docker" \
  --docker-image alpine:latest \
  --description "shared-runner" \
  --tag-list "shared-runner" \
  --run-untagged="true" \
  --locked="false" \
  --access-level="not_protected"

echo "[INFO] Shared runner registered"
echo "[INFO] Gitlab setup complete"

echo "[INFO] Waiting redmine startup"

# shellcheck disable=SC2034
for i in {1..300}; do
  set +e # Disable exit on error
  STATUS_CODE="$(docker compose exec redmine curl -s -k -q --max-time 5 -w '%{http_code}' -o /dev/null http://localhost:3000)"
  set -e # Enable exit on error

  if [ "$STATUS_CODE" -eq 200 ]; then
    echo -e "\n[INFO] Redmine startup complete"
    break
  fi
  echo -n "."
  sleep 1
done

docker compose exec rm-database psql -U postgres -d redmine_database -f /tmp/redmine.sql


## Sonarqube 
echo "[INFO] Waiting sonarqube startup"
chk_key='API_SERVER'

cmd_msg=$(curl --request POST "http://localhost:$SQ_PORT/api/user_tokens/generate" -H 'Authorization: Basic YWRtaW46YWRtaW4=' --form 'name="API_SERVER"' --form 'login="admin"')
if echo "$cmd_msg" | grep -q 'already exists'; then
    curl --request POST "http://localhost:$SQ_PORT/api/user_tokens/revoke" -H 'Authorization: Basic YWRtaW46YWRtaW4=' --form 'name="API_SERVER"' --form 'login="admin"'
    sleep 1
    cmd_msg=$(curl --request POST "http://localhost:$SQ_PORT/api/user_tokens/generate" -H 'Authorization: Basic YWRtaW46YWRtaW4=' --form 'name="API_SERVER"' --form 'login="admin"')
fi

key=$(echo "$cmd_msg" | jq -r '.name')
if [ "$key" = "$chk_key" ]; then
    sonarqube_admin_token=$(echo "$cmd_msg" | jq -r '.token')
fi
echo $sonarqube_admin_token

# Wait 3 Secs
sleep 3

# Find default_template
cmd_msg=$(curl --request GET "http://localhost:$SQ_PORT/api/permissions/search_templates" -H 'Authorization: Basic YWRtaW46YWRtaW4=')
if ! echo "$cmd_msg" | grep -q 'templateId'; then
    echo "get default_template Error : $cmd_msg"
    exit 1
fi
templateId=$(echo "$cmd_msg" | jq -r '.defaultTemplates[0].templateId')
echo "get default_template ID : $templateId"

# Setting default sonarqube group template permission ( admin, codeviewer, issueadmin, securityhotspotadmin, scan, user ) 
permission_str='admin,codeviewer,issueadmin,securityhotspotadmin,scan,user'
for permission in $(echo "$permission_str" | tr ',' ' '); do
    cmd_msg=$(curl --request POST "http://localhost:$SQ_PORT/api/permissions/add_group_to_template" \
        --form 'templateId="'$templateId'"' --form 'groupName="sonar-administrators"' --form 'permission="'$permission'"' -H 'Authorization: Basic YWRtaW46YWRtaW4=')
    if [ "$cmd_msg" != "" ]; then
        echo "Add group sonar-administrators $permission permission Error : $cmd_msg"
    else
        echo "Add group sonar-administrators $permission permission OK!"
    fi
    
    cmd_msg=$(curl --request POST "http://localhost:$SQ_PORT/api/permissions/remove_group_from_template" \
        --form 'templateId="'$templateId'"' --form 'groupName="sonar-users"' --form 'permission="'$permission'"' -H 'Authorization: Basic YWRtaW46YWRtaW4=')
    if [ "$cmd_msg" != "" ]; then
        echo "Remove group sonar-users $permission permission Error : $cmd_msg"
    else
        echo "Remove group sonar-users $permission permission OK!"
    fi
done

# Update admin password
cmd_msg=$(curl --request POST "http://localhost:$SQ_PORT/api/users/change_password" \
        --form 'login="admin"' --form 'password="'$SQ_AM_PASSWORD'"' --form 'previousPassword="admin"' -H 'Authorization: Basic YWRtaW46YWRtaW4=')
if [ -n "$cmd_msg" ]; then
  echo "update admin password Error : $cmd_msg \n"
  exit 1
fi