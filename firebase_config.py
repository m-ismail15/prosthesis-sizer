# import os
# import sys
# from firebase_admin import credentials, initialize_app, firestore

# def get_base_path():
#     """Get base path for PyInstaller or normal run."""
#     if getattr(sys, 'frozen', False):
#         return os.path.dirname(sys.executable)
#     return os.path.dirname(os.path.abspath(__file__))

# def find_service_key():
#     base_path = get_base_path()

#     possible_paths = [
#         os.path.join(base_path, "serviceAccountKey.json"),
#         os.path.join(base_path, "config", "serviceAccountKey.json"),
#         os.path.join(os.getenv("APPDATA", ""), "ProsthesisSizer", "serviceAccountKey.json"),
#         os.getenv("FIREBASE_KEY_PATH")
#     ]

#     for path in possible_paths:
#         if path and os.path.exists(path):
#             return path

#     raise FileNotFoundError(
#         "Firebase key not found.\n"
#         "Place serviceAccountKey.json next to the EXE or in config folder."
#     )

# # 🔹 Load Firebase
# key_path = find_service_key()
# cred = credentials.Certificate(key_path)
# initialize_app(cred)

# db = firestore.client()

# firebase_config.py

import firebase_admin
from firebase_admin import credentials, firestore
import os
import sys

def get_firebase_key_path():
    """Search for Firebase key in multiple secure locations."""

    possible_paths = [
        # 1️⃣ Same folder as EXE (portable mode)
        os.path.join(os.path.dirname(sys.executable), "serviceAccountKey.json"),

        # 2️⃣ Project root (development mode)
        os.path.join(os.path.dirname(__file__), "serviceAccountKey.json"),

        # 3️⃣ Secure external location (your chosen path)
        r"C:\Projects\Firebase Key\serviceAccountKey.json",
    ]

    for path in possible_paths:
        if os.path.exists(path):
            return path

    raise FileNotFoundError(
        "Firebase key not found. Place serviceAccountKey.json in:\n"
        "- EXE folder\n"
        "- Project folder\n"
        "- C:\\Projects\\Firebase Key\\"
    )

# Load Firebase
try:
    key_path = get_firebase_key_path()
    cred = credentials.Certificate(key_path)
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    print(f"Firebase initialized using key at: {key_path}")

except Exception as e:
    raise RuntimeError(f"Firebase initialization failed: {e}")