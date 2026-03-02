import os
import sys

import firebase_admin
from firebase_admin import credentials, firestore
from app_paths import install_base_dir, user_config_dir


# ---------------- FIREBASE DISCOVERY ---------------- #
def find_service_account_key() -> str:
    """
    Portable-first key detection:
    1) Same folder as EXE
    2) config/ subfolder next to EXE
    3) FIREBASE_KEY_PATH environment variable
    4) Same folder as source code
    """

    paths = []

    if getattr(sys, "frozen", False):
        exe_dir = install_base_dir()
        paths.extend(
            [
                os.path.join(exe_dir, "serviceAccountKey.json"),
                os.path.join(exe_dir, "config", "serviceAccountKey.json"),
            ]
        )

    paths.append(os.path.join(user_config_dir(), "serviceAccountKey.json"))

    env_path = os.getenv("FIREBASE_KEY_PATH")
    if env_path:
        paths.append(env_path)

    src_dir = os.path.dirname(os.path.abspath(__file__))
    paths.append(os.path.join(src_dir, "serviceAccountKey.json"))

    for path in paths:
        if path and os.path.exists(path):
            return path

    raise FileNotFoundError(
        "Firebase key not found.\n\n"
        "Portable setup:\n"
        "- Place serviceAccountKey.json in the same folder as app.exe, OR\n"
        "- Place it in a subfolder called config\\ next to app.exe.\n"
    )


# ---------------- FIREBASE ACCESS ---------------- #
def initialize_firebase() -> None:
    if firebase_admin._apps:
        return

    key_path = find_service_account_key()
    cred = credentials.Certificate(key_path)
    firebase_admin.initialize_app(cred)


def get_firestore_client():
    initialize_firebase()
    return firestore.client()


def is_firebase_configured() -> bool:
    try:
        find_service_account_key()
        return True
    except FileNotFoundError:
        return False
