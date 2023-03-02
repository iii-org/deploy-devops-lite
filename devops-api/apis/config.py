import json
import os
from pathlib import Path

FIXED = {
    # API versions
    "GITLAB_API_VERSION": "v4",
    "RANCHER_API_VERSION": "v3",
    "LOGGER_NAME": "devops.api",
    "DEBUG": False,
    "USE_RELOADER": False,
    "DEFAULT_TRACE_ORDER": ["Epic", "Feature", "Test Plan"],
    "DOCUMENT_LEVEL": "public",
    "REDIS_BASE_URL": "devops-redis-service:6379",
}

in_file = {}
JSON_FILE: Path = Path(__file__).parent.parent / "environments.json"
if os.path.isfile(JSON_FILE):
    with open(JSON_FILE, "r") as f:
        in_file = json.load(f)


def get(key):
    env = os.getenv(key)
    if env is not None:
        return env
    return in_file.get(key, FIXED.get(key, None))
