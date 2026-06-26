import os
import json
from config import TOKEN_FILE

_PROFILE_FILE = "user_profile.json"


def save_token(access_token: str, user_id: str = ""):
    with open(TOKEN_FILE, "w") as f:
        f.write(access_token.strip())
    if user_id:
        with open(_PROFILE_FILE, "w") as f:
            json.dump({"user_id": user_id}, f)


def load_token() -> str | None:
    if not os.path.exists(TOKEN_FILE):
        return None
    with open(TOKEN_FILE) as f:
        token = f.read().strip()
    return token or None


def load_user_id() -> str:
    if not os.path.exists(_PROFILE_FILE):
        return ""
    with open(_PROFILE_FILE) as f:
        return json.load(f).get("user_id", "")


def clear_token():
    if os.path.exists(TOKEN_FILE):
        os.remove(TOKEN_FILE)
