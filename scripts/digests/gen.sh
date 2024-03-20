#!/bin/bash

# openai Generated code
# Convert from https://gitlab.com/gitlab-org/gitlab/-/blob/master/config/weak_password_digests.yml?ref_type=heads#L15-27

set -eup pipefail

echo "Downloading password list..."

# Check if password.txt exist
if [ ! -f password.txt ]; then
  echo "password.txt not found"
  curl -sS "https://raw.githubusercontent.com/danielmiessler/SecLists/master/Passwords/Common-Credentials/10-million-password-list-top-1000000.txt" >password.txt
else
  echo "password.txt found"
fi

echo "Processing passwords..."

awk 'length >= 8 && length <= 16 { print $0 }' password.txt | while IFS= read -r weak_password; do
  # 轉換密碼為小寫
  weak_password=$(echo "$weak_password" | tr '[:upper:]' '[:lower:]')
  hashed_pwd=$(echo -n "$weak_password" | sha256sum | awk '{print $1}')
  # 取得哈希值的首字母
  first_char=$(echo "$hashed_pwd" | cut -c 1)
  # 將密碼分發到不同檔案中
  echo "$hashed_pwd" >>"digests_${first_char}.txt"
done

echo "Password list processed successfully!"
