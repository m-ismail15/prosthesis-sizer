import os
import sys
import firebase_admin
from firebase_admin import credentials, firestore

# --------------------------------------------------
# 🔐 Locate Firebase service account key
# --------------------------------------------------
def get_key_path():
    """
    Returns the correct path to serviceAccountKey.json
    Works for:
    ✔ Running as Python script
    ✔ Running as PyInstaller EXE
    """

    # If running as bundled EXE
    if getattr(sys, "frozen", False):
        base_path = os.path.dirname(sys.executable)
    else:
        # Running as normal Python script
        base_path = os.path.dirname(os.path.abspath(__file__))

    return os.path.join(base_path, "serviceAccountKey.json")


# --------------------------------------------------
# 🔎 Resolve key path
# --------------------------------------------------
key_path = get_key_path()

if not os.path.exists(key_path):
    raise FileNotFoundError(
        f"Firebase key not found.\n"
        f"Expected location:\n{key_path}\n\n"
        f"Make sure 'serviceAccountKey.json' is in the same folder as the EXE."
    )

# --------------------------------------------------
# 🚀 Initialize Firebase
# --------------------------------------------------
try:
    if not firebase_admin._apps:
        cred = credentials.Certificate(key_path)
        firebase_admin.initialize_app(cred)

    db = firestore.client()

except Exception as e:
    raise RuntimeError(f"Failed to initialize Firebase: {e}")
