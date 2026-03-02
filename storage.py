import json
import os
import sys
import uuid
from copy import deepcopy
from datetime import datetime, timezone


# ---------------- STORAGE PRIMITIVES ---------------- #
class StorageError(Exception):
    pass


class RecordSnapshot:
    def __init__(self, record_id: str, data: dict):
        self.id = record_id
        self._data = deepcopy(data)

    def to_dict(self) -> dict:
        return deepcopy(self._data)


def app_base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def default_local_store_path() -> str:
    return os.path.join(app_base_dir(), "data", "offline_records.json")


# ---------------- FIREBASE STORE ---------------- #
class FirebaseStore:
    mode_name = "online"

    def __init__(self):
        from firebase_config import get_firestore_client

        self.db = get_firestore_client()

    def authenticate(self, email: str, password: str):
        users_ref = self.db.collection("Users")
        query = (
            users_ref.where("email", "==", email)
            .where("password", "==", password)
            .limit(1)
            .stream()
        )

        user_doc = next(query, None)
        if not user_doc:
            return None

        return user_doc.to_dict().get("role", "prosthetist")

    def save_record(self, payload: dict) -> None:
        from firebase_admin import firestore as fb_firestore

        record = dict(payload)
        record["created_at"] = fb_firestore.SERVER_TIMESTAMP
        record["updated_at"] = fb_firestore.SERVER_TIMESTAMP
        self.db.collection("prosthesis_records").add(record)

    def list_records(self):
        return list(self.db.collection("prosthesis_records").stream())

    def search_records(self, text: str):
        text = text.strip().lower()
        if not text:
            return self.list_records()

        records = self.list_records()
        return [record for record in records if text in record.to_dict().get("name_lower", "")]


# ---------------- LOCAL OFFLINE STORE ---------------- #
class LocalJsonStore:
    mode_name = "offline"

    def __init__(self, file_path: str | None = None):
        self.file_path = file_path or default_local_store_path()

    def authenticate(self, email: str, password: str):
        # Offline mode is intentionally credential-free.
        return "prosthetist"

    def save_record(self, payload: dict) -> None:
        data = self._read_data()
        timestamp = datetime.now(timezone.utc).isoformat()

        record = dict(payload)
        # Keep the saved structure close to Firestore records so the UI stays simple.
        record_id = uuid.uuid4().hex
        record["id"] = record_id
        record["created_at"] = timestamp
        record["updated_at"] = timestamp

        data["prosthesis_records"].append(record)
        self._write_data(data)

    def list_records(self):
        data = self._read_data()
        records = sorted(
            data["prosthesis_records"],
            key=lambda record: record.get("updated_at", ""),
            reverse=True,
        )
        return [RecordSnapshot(record["id"], record) for record in records]

    def search_records(self, text: str):
        text = text.strip().lower()
        if not text:
            return self.list_records()

        return [
            record
            for record in self.list_records()
            if text in record.to_dict().get("name_lower", "")
        ]

    def _read_data(self) -> dict:
        if not os.path.exists(self.file_path):
            return {"prosthesis_records": []}

        try:
            with open(self.file_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except json.JSONDecodeError as exc:
            raise StorageError(
                f"Offline data file is not valid JSON: {self.file_path}"
            ) from exc
        except OSError as exc:
            raise StorageError(
                f"Could not read offline data file: {self.file_path}"
            ) from exc

        if "prosthesis_records" not in data or not isinstance(
            data["prosthesis_records"], list
        ):
            raise StorageError(
                f"Offline data file has an unexpected format: {self.file_path}"
            )

        return data

    def _write_data(self, data: dict) -> None:
        try:
            os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
            with open(self.file_path, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2)
        except OSError as exc:
            raise StorageError(
                f"Could not write offline data file: {self.file_path}"
            ) from exc
