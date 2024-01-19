#!/usr/bin/env bash

_variable_escape() {
  local str="$1"
  local result=""
  local i

  for ((i = 0; i < ${#str}; i++)); do
    local char="${str:$i:1}"
    if [[ "$char" == "\\" ]]; then
      result="$result\\\\"
    else
      result="$result$char"
    fi
  done

  echo "$result"
}

_variable_escape_single() {
  local str="$1"
  local result=""
  local i

  for ((i = 0; i < ${#str}; i++)); do
    local char="${str:$i:1}"
    if [[ "$char" == "'" ]]; then
      # Close single quote and add quoted single quote
      result="$result'\"'\"'"
    else
      result="$result$char"
    fi
  done

  echo "$result"
}

_variable_escape_double() {
  local str="$1"
  local result=""
  local i

  for ((i = 0; i < ${#str}; i++)); do
    local char="${str:$i:1}"
    if [[ "$char" == "\"" ]]; then
      result="$result\\\\\""
    elif [[ "$char" == "\\" ]]; then
      result="$result\\\\"
    elif [[ "$char" == "\$" ]]; then
      result="$result\\\\\$"
    elif [[ "$char" == "\`" ]]; then
      result="$result\\\\\`"
    else
      result="$result$char"
    fi
  done

  echo "$result"
}

variable_write() {
  local key="$1"
  local value="$2"
  local sensitive="${3:-false}"
  local extended="${4:-false}"
  local separator

  value="$(_variable_escape "$value")"

  if $extended; then
    value="$(_variable_escape_double "$value")"
    separator="\""
  else
    value="$(_variable_escape_single "$value")"
    separator="'"
  fi

  # Check if key is in .env file
  if ! grep -q "$key=" "${ENVIRONMENT_FILE:?}"; then
    INFO "$key not found in .env file, adding it"
    echo "$key=\"$value\"" >>"${ENVIRONMENT_FILE}"
  fi

  # Write back to .env file, replace the old key, using awk to escape special characters
  awk -v key="$key" -v value="$value" -v separator="$separator" \
    'BEGIN { FS=OFS="=" }
    { for(i=3; i<=NF; i++)
      {
        $2 = $2"="$i
      }
    }
    $1 == key {
      $2 = separator value separator
    }
    NF {
      if ($1 ~ /^#/) {
        NF = NF
      }
      else {
        NF = 2
      }
    } 1' "${ENVIRONMENT_FILE}" >"${ENVIRONMENT_FILE}.tmp"

  if $sensitive; then
    INFO "🔒 ${ORANGE}$key${NOFORMAT} set! (sensitive)"
  else
    INFO "✏️ ${ORANGE}$key${NOFORMAT} set to ${WHITE}$value${NOFORMAT}"
  fi

  # Replace the old file, we don't need the tmp file anymore
  mv "${ENVIRONMENT_FILE}.tmp" "${ENVIRONMENT_FILE}"
  load_env_file
}

variable_load() {
  { set -a; } 2>/dev/null
  # shellcheck source=/dev/null
  . "${ENVIRONMENT_FILE:?Environment file not set}"
  { set +a; } 2>/dev/null
}
