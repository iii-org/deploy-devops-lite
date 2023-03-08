#!/usr/bin/env bash

set -eu

# Load common functions
base_dir="$(cd "$(dirname "$0")" && pwd)"
source "$base_dir"/common.sh

GITHUB_TEMPLATE_USER="iiidevops-templates" # https://github.com/iiidevops-templates
GITLAB_URL=gitlab:${GITLAB_PORT}
GITLAB_INIT_TOKEN=""
GITLAB_RUNNER="docker compose exec runner"

# Check if GitLab is running
if ! $GITLAB_RUNNER curl -s -k "http://$GITLAB_URL/api/v4/version" >/dev/null; then
  ERROR "GitLab is not running, please run \e[97m${project_dir:?}/setup.sh\e[0m to start project"
  exit 1
fi

gitlab_parse_error() {
  message_check="$(echo "$1" | jq -r 'if type == "object" then .message elif type == "array" then "" else .[] end')"

  if [ -n "$message_check" ] && [ "$message_check" != "null" ]; then
    # If message has value, and message is not null

    # Check if message start with 2xx, 3xx, if yes, skip
    if [[ "$message_check" =~ ^[2-3][0-9][0-9] ]]; then
      return
    fi

    ERROR "Message: $message_check"
    exit 1
  elif [ -n "$message_check" ]; then
    # If message has value, and is an array
    ERROR "Unknown error, response: \n$1"
    exit 1
  fi
}

gitlab_get_id_or_path() {
  id_or_path="$1"

  if [[ ! $id_or_path =~ ^[0-9]+$ ]]; then
    id_or_path="$(url_encode "$id_or_path")"
  fi

  echo "$id_or_path"
}

gitlab_get_group_id() {
  GITLAB_RESPONSE=$(
    $GITLAB_RUNNER curl -s -k \
      --request GET "http://gitlab:$GITLAB_PORT/api/v4/groups?search=$1" \
      --header "PRIVATE-TOKEN: $GITLAB_INIT_TOKEN"
  )

  gitlab_parse_error "$GITLAB_RESPONSE"

  # TODO: Fix if empty array
  echo "$GITLAB_RESPONSE" | jq -r '.[0].id'
}

gitlab_get_project_id() {
  GITLAB_RESPONSE=$(
    $GITLAB_RUNNER curl -s -k \
      --request GET "http://gitlab:$GITLAB_PORT/api/v4/projects?search=$1" \
      --header "PRIVATE-TOKEN: $GITLAB_INIT_TOKEN"
  )

  gitlab_parse_error "$GITLAB_RESPONSE"

  # TODO: Fix if empty array
  echo "$GITLAB_RESPONSE" | jq -r '.[0].id'
}

gitlab_get_group_projects() {
  id_or_path="$(gitlab_get_id_or_path "$1")"

  GITLAB_RESPONSE=$(
    $GITLAB_RUNNER curl -s -k \
      --request GET "http://gitlab:$GITLAB_PORT/api/v4/groups/$id_or_path/projects?per_page=100" \
      --header "PRIVATE-TOKEN: $GITLAB_INIT_TOKEN" \
      --header "Content-Type: application/json"
  )

  gitlab_parse_error "$GITLAB_RESPONSE"

  echo "$GITLAB_RESPONSE"
}

gitlab_create_group() {
  data="{\"name\": \"$1\", \"path\": \"$1\", \"visibility\": \"public\"}"
  GITLAB_RESPONSE=$(
    $GITLAB_RUNNER curl -s -k \
      --request POST "http://gitlab:$GITLAB_PORT/api/v4/groups" \
      --header "PRIVATE-TOKEN: $GITLAB_INIT_TOKEN" \
      --header "Content-Type: application/json" \
      --data "$data"
  )

  # Check response, if already exist, skip
  # Example string: {"message":"Failed to save group {:path=>[\"has already been taken\"]}"}
  if [[ "$GITLAB_RESPONSE" =~ "has already been taken" ]]; then
    INFO "Group \e[97m$1\e[0m already exist, skip"
    return
  fi

  # If response not a success response, raise Error
  # Example string: {"id":4,"web_url":"http://10.20.0.94:32080/groups/local-templates","name":"local-templates","path":"local-templates","description":"","visibility":"public","share_with_group_lock":false,"require_two_factor_authentication":false,"two_factor_grace_period":48,"project_creation_level":"developer","auto_devops_enabled":null,"subgroup_creation_level":"maintainer","emails_disabled":null,"mentions_disabled":null,"lfs_enabled":true,"default_branch_protection":2,"avatar_url":null,"request_access_enabled":true,"full_name":"local-templates","full_path":"local-templates","created_at":"2023-03-07T02:34:33.678Z","parent_id":null,"shared_with_groups":[],"projects":[],"shared_projects":[]}
  r_id="$(echo "$GITLAB_RESPONSE" | jq -r '.id')"
  if [ -n "$r_id" ] && [ "$r_id" != "null" ]; then
    INFO "Group \e[97m$1\e[0m created"
  else
    gitlab_parse_error "$GITLAB_RESPONSE"
  fi
}

gitlab_create_project() {
  GITLAB_RESPONSE=$(
    $GITLAB_RUNNER curl -s -k \
      --request POST "http://gitlab:$GITLAB_PORT/api/v4/projects" \
      --header "PRIVATE-TOKEN: $GITLAB_INIT_TOKEN" \
      --header "Content-Type: application/json" \
      --data '{"name": "'"$1"'", "namespace_id": "'"$2"'", "visibility": "public"}'
  )

  if [[ "$GITLAB_RESPONSE" =~ "has already been taken" ]]; then
    INFO "Project \e[97m$1\e[0m already exist, skip"
    return
  fi

  r_id="$(echo "$GITLAB_RESPONSE" | jq -r '.id')"
  if [ -n "$r_id" ] && [ "$r_id" != "null" ]; then
    INFO "Project \e[97m$1\e[0m created"
  else
    gitlab_parse_error "$GITLAB_RESPONSE"
  fi
}

gitlab_delete_project() {
  id_or_path="$(gitlab_get_id_or_path "$1")"

  GITLAB_RESPONSE=$(
    $GITLAB_RUNNER curl -s -k \
      --request DELETE "http://gitlab:$GITLAB_PORT/api/v4/projects/$id_or_path" \
      --header "PRIVATE-TOKEN: $GITLAB_INIT_TOKEN"
  )

  gitlab_parse_error "$GITLAB_RESPONSE"
}

usage() {
  echo "Add GitLab templates."
  echo
  echo "Usage: $(basename "$0") [OPTIONS]... [GITLAB_INIT_TOKEN]"
  echo
  echo "Options:"
  echo "  -h,  --help    print this help"
  exit 21
}

main() {
  MSG="http://root:$(url_encode "$GITLAB_ROOT_PASSWORD")@$GITLAB_URL"

  $GITLAB_RUNNER sh -c "if [ -f ~/.git-credentials ]; then \
    if grep -q \"$MSG\" ~/.git-credentials; then \
      echo \"$MSG\" >>~/.git-credentials; \
    fi; \
  else \
    echo \"$MSG\" >>~/.git-credentials; \
  fi"

  $GITLAB_RUNNER git config --global credential.helper store

  gitlab_create_group "local-templates"
  gitlab_create_group "$GITHUB_TEMPLATE_USER"

  response_json="$(gitlab_get_group_projects "$GITHUB_TEMPLATE_USER")"

  # Filtered response
  echo "$response_json" | jq -cr '[.[] | {id: .id, name: .path_with_namespace}]' | while read -r filterd; do
    for i in $(echo "$filterd" | jq -cr '.[]'); do
      INFO "Deleting $(echo "$i" | jq -r '.name')"
      gitlab_delete_project "$(echo "$i" | jq -r '.id')"
      INFO "Deleted $(echo "$i" | jq -r '.name')"
    done
  done

  # For each directory in template directory
  for _dir in templates/*; do
    if [ -d "$_dir" ]; then
      RUNNER_COMMANDS=""

      # Get directory name
      dir_name="$(basename "$_dir")"
      RUNNER_COMMANDS+="cd /templates/$dir_name; "

      # Create project by directory name
      gitlab_create_project "$dir_name" "$(gitlab_get_group_id "$GITHUB_TEMPLATE_USER")"

      # cd to directory and check if .git folder exist
      cd "$_dir" || ERROR "Cannot cd to $_dir"
      RUNNER_COMMANDS+="git config --global user.name \"Administrator\"; "
      RUNNER_COMMANDS+="git config --global user.email \"admin@example.com\"; "

      if [ ! -d .git ]; then
        # If not exist, init git
        RUNNER_COMMANDS+="git init; "
        RUNNER_COMMANDS+="git remote add origin http://$GITLAB_URL/$GITHUB_TEMPLATE_USER/$dir_name.git; "
        RUNNER_COMMANDS+="git add .; "
        RUNNER_COMMANDS+="git commit -m \"Initial commit\"; "
        RUNNER_COMMANDS+="git push -u origin master; "
      else
        # If exist, change remote url
        RUNNER_COMMANDS+="git remote rename origin old-origin; "
        RUNNER_COMMANDS+="git remote add origin http://$GITLAB_URL/$GITHUB_TEMPLATE_USER/$dir_name.git; "
        RUNNER_COMMANDS+="git push -u origin --all; "
        RUNNER_COMMANDS+="git push -u origin --tags; "
      fi

      echo "[RUNNER] $RUNNER_COMMANDS" >>"$project_dir"/.executed_to_runner.log

      # Execute commands in runner
      $GITLAB_RUNNER sh -c "$RUNNER_COMMANDS" >>"$project_dir"/.executed_to_runner.log

      INFO "Imported template: $dir_name to $GITHUB_TEMPLATE_USER completed!"

      # Return to root directory
      cd "$project_dir" || ERROR "Cannot cd to $project_dir"
    fi
  done

  INFO "Import templates done!"
}

# If no arguments passed, print help
if [[ "$#" -eq 0 ]]; then
  usage
fi

while [[ "$#" -gt 0 ]]; do
  case $1 in
  -h | --help) usage ;;
  *)
    GITLAB_INIT_TOKEN=$1
    main
    shift
    ;;
  esac
done
