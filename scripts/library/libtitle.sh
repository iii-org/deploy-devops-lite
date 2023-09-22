#!/usr/bin/env bash

title_center() {
  local title=${1:?}
  local color=${2:-${YELLOW}}
  local padding_char=${3:-=}
  local width=${4:-40}
  local padding
  padding="$(printf '%0.1s' "$padding_char"{1..500})"

  local left="$(((width - 2 - ${#title}) / 2))"
  local right="$(((width - 1 - ${#title}) / 2))"

  printf '%*.*s %s %*.*s\n' 0 "$left" "$padding" "${color}${title}${NOFORMAT}" 0 "$right" "$padding"
}
