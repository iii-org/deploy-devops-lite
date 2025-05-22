# https://gitlab.com/gitlab-org/gitlab/-/blob/master/lib/security/weak_passwords.rb
# Convert by ChatGPT
import argparse
import base64
import hashlib
import re

FORBIDDEN_WORDS = {"gitlab", "devops"}
MINIMUM_SUBSTRING_SIZE = 4
PASSWORD_SUBSTRING_CHECK_MAX_LENGTH = 64

# 假設的弱密碼 SHA256 Base64 digest 清單（模擬資料）
# 實際部署時需從配置或資料庫載入
WEAK_PASSWORDS_DIGEST_SET = {
    base64.b64encode(hashlib.sha256(b"123456").digest()).decode(),
    base64.b64encode(hashlib.sha256(b"password").digest()).decode(),
}


def is_blank(s):
    return s is None or s.strip() == ""


def contains_predictable_substring(password, substrings):
    if len(password) >= PASSWORD_SUBSTRING_CHECK_MAX_LENGTH:
        return False

    password = password.lower()
    filtered = [s.lower() for s in substrings if len(s) >= MINIMUM_SUBSTRING_SIZE]

    return any(sub in password for sub in filtered)


def forbidden_word_appears(password):
    return contains_predictable_substring(password, FORBIDDEN_WORDS)


def password_on_weak_list(password):
    digest = hashlib.sha256(password.lower().encode()).digest()
    base64_digest = base64.b64encode(digest).decode()
    return base64_digest in WEAK_PASSWORDS_DIGEST_SET


def name_appears(password, name):
    if is_blank(name):
        return False
    substrings = [name] + re.split(r"[^\w]", name)
    return contains_predictable_substring(password, substrings)


def username_appears(password, username):
    if is_blank(username):
        return False
    substrings = [username] + re.split(r"[^\w]", username)
    return contains_predictable_substring(password, substrings)


def email_appears(password, email):
    if is_blank(email):
        return False
    parts = [email] + email.split("@") + re.split(r"[^\w]", email)
    return contains_predictable_substring(password, parts)


def user_info_in_password(password, name, username, email):
    return name_appears(password, name) or username_appears(password, username) or email_appears(password, email)


def common_phrases_in_password(password):
    return forbidden_word_appears(password) or password_on_weak_list(password)


def weak_for_user(password, name, username, email):
    if user_info_in_password(password, name, username, email):
        print("❌ Password contains user information")

    return user_info_in_password(password, name, username, email) or common_phrases_in_password(password)


def main():
    parser = argparse.ArgumentParser(description="Check if a password is weak based on user info and known patterns.")
    parser.add_argument("password", help="The password to check.")
    parser.add_argument("--name", default="", help="Full name of the user.")
    parser.add_argument("--username", default="", help="Username of the user.")
    parser.add_argument("--email", default="", help="Email of the user.")

    args = parser.parse_args()
    is_weak = weak_for_user(args.password, args.name, args.username, args.email)

    if is_weak:
        print("❌ Password does not meet security standards (too weak)")
        exit(2)
    else:
        print("✅ Password meets minimal security standards, continue...")


if __name__ == "__main__":
    main()
