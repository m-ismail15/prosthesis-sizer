import os
import sys
from firebase_admin import credentials, initialize_app, firestore

def get_base_path():
    """Get base path for PyInstaller or normal run."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def find_service_key():
    base_path = get_base_path()

    possible_paths = [
        os.path.join(base_path, "serviceAccountKey.json"),
        os.path.join(base_path, "config", "serviceAccountKey.json"),
        os.path.join(os.getenv("APPDATA", ""), "ProsthesisSizer", "serviceAccountKey.json"),
        os.getenv("FIREBASE_KEY_PATH")
    ]

    for path in possible_paths:
        if path and os.path.exists(path):
            return path

    raise FileNotFoundError(
        "Firebase key not found.\n"
        "Place serviceAccountKey.json next to the EXE or in config folder."
    )

# 🔹 Load Firebase
key_path = find_service_key()
cred = credentials.Certificate(key_path)
initialize_app(cred)

db = firestore.client()