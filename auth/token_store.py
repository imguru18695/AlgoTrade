import os
import json
from config import TOKEN_FILE

_PROFILE_FILE = "user_profile.json"


def save_token(access_token: str, user_id: str = ""):
    # Write atomically: open() truncates immediately, so a SIGKILL between
    # truncation and write would leave an empty file → false logout with open
    # positions. Write to a .tmp file first, then rename atomically.
    tmp = TOKEN_FILE + ".tmp"
    with open(tmp, "w") as f:
        f.write(access_token.strip())
    os.replace(tmp, TOKEN_FILE)
    if user_id:
        tmp_p = _PROFILE_FILE + ".tmp"
        with open(tmp_p, "w") as f:
            json.dump({"user_id": user_id}, f)
        os.replace(tmp_p, _PROFILE_FILE)


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
