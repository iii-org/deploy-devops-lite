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
# watch -n 0.5 "curl -s -I http://gitlab:32080/users/sign_in"
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
