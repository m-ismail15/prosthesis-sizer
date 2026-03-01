import os
import sys
import firebase_admin
from firebase_admin import credentials, firestore

def find_service_account_key():
    """
    Portable-first key detection:
    1) Same folder as EXE (portable deployment)
    2) config/ subfolder next to EXE
    3) Environment variable FIREBASE_KEY_PATH (optional advanced)
    4) Same folder as source code (development)
    """

    paths = []

    # If running as a packaged EXE
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        paths += [
            os.path.join(exe_dir, "serviceAccountKey.json"),
            os.path.join(exe_dir, "config", "serviceAccountKey.json"),
        ]

    # Optional: env var (advanced deployments)
    env_path = os.getenv("FIREBASE_KEY_PATH")
    if env_path:
        paths.append(env_path)

    # Development mode (running from Python)
    src_dir = os.path.dirname(os.path.abspath(__file__))
    paths.append(os.path.join(src_dir, "serviceAccountKey.json"))

    for p in paths:
        if p and os.path.exists(p):
            return p

    raise FileNotFoundError(
        "Firebase key not found.\n\n"
        "Portable setup:\n"
        "- Place serviceAccountKey.json in the same folder as app.exe, OR\n"
        "- Place it in a subfolder called config\\ next to app.exe.\n"
    )

key_path = find_service_account_key()
cred = credentials.Certificate(key_path)

if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

db = firestore.client()