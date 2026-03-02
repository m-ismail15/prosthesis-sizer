import json
import os
import uuid
from copy import deepcopy
from datetime import datetime, timezone

from app_paths import user_queue_dir

FIRESTORE_TIMEOUT_SECONDS = 10


# ---------------- STORAGE PRIMITIVES ---------------- #
class StorageError(Exception):
    pass


class RecordSnapshot:
    def __init__(self, record_id: str, data: dict):
        self.id = record_id
        self._data = deepcopy(data)

    def to_dict(self) -> dict:
        return deepcopy(self._data)

def default_local_store_path() -> str:
    return os.path.join(user_queue_dir(), "offline_records.json")


# ---------------- FIREBASE STORE ---------------- #
class FirebaseStore:
    mode_name = "online"

    def __init__(self):
        pass

    def _db(self):
        from firebase_config import get_firestore_client

        return get_firestore_client()

    def authenticate(self, email: str, password: str):
        users_ref = self._db().collection("Users")
        query = (
            users_ref.where("email", "==", email)
            .where("password", "==", password)
            .limit(1)
            .stream(timeout=FIRESTORE_TIMEOUT_SECONDS)
        )

        user_doc = next(query, None)
        if not user_doc:
            return None

        return user_doc.to_dict().get("role", "prosthetist")

    def save_record(self, payload: dict) -> str:
        from firebase_admin import firestore as fb_firestore

        record = dict(payload)
        record["created_at"] = fb_firestore.SERVER_TIMESTAMP
        record["updated_at"] = fb_firestore.SERVER_TIMESTAMP
        _, doc_ref = self._db().collection("prosthesis_records").add(
            record,
            timeout=FIRESTORE_TIMEOUT_SECONDS,
        )
        return doc_ref.id

    def list_records(self):
        return list(
            self._db().collection("prosthesis_records").stream(
                timeout=FIRESTORE_TIMEOUT_SECONDS
            )
        )

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

    def save_record(self, payload: dict) -> str:
        data = self._read_data()
        timestamp = datetime.now(timezone.utc).isoformat()

        record = dict(payload)
        # Keep the saved structure close to Firestore records so the UI stays simple.
        # This file acts as a pending-sync queue, not a permanent local archive.
        record_id = uuid.uuid4().hex
        record["id"] = record_id
        record["created_at"] = timestamp
        record["updated_at"] = timestamp

        data["prosthesis_records"].append(record)
        self._write_data(data)
        return record_id

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

    def sync_pending_records(self, online_store: FirebaseStore) -> dict:
        data = self._read_data()
        all_records = data["prosthesis_records"]
        pending_records = [
            record for record in all_records if not record.get("synced_to_online", False)
        ]

        result = {
            "pending_count": len(pending_records),
            "synced_count": 0,
            "failed_count": 0,
            "errors": [],
        }

        if not pending_records:
            if len(pending_records) != len(all_records):
                data["prosthesis_records"] = pending_records
                self._write_data(data)
            return result

        remaining_records = []

        for record in all_records:
            if record.get("synced_to_online", False):
                # Clean up legacy entries created by the previous "mark as synced" approach.
                continue

            try:
                online_store.save_record(self._build_online_payload(record))
            except Exception as exc:
                result["failed_count"] += 1
                result["errors"].append(f"{record.get('name', 'Unknown')}: {exc}")
                remaining_records.append(record)
                continue

            # Successfully synced records are removed from the local queue.
            result["synced_count"] += 1

        data["prosthesis_records"] = remaining_records
        self._write_data(data)
        return result

    def _build_online_payload(self, record: dict) -> dict:
        return {
            "name": record.get("name", ""),
            "name_lower": record.get("name_lower", ""),
            "bicep_circ": record.get("bicep_circ"),
            "forearm_circ": record.get("forearm_circ"),
            "humerus_len": record.get("humerus_len"),
            "residuum_len": record.get("residuum_len"),
            "width_size": record.get("width_size"),
            "humeral_length": record.get("humeral_length"),
            "radial_length": record.get("radial_length"),
            "sizing_note": record.get("sizing_note", ""),
            "source_mode": "offline_sync",
            "offline_record_id": record.get("id"),
            "offline_created_at": record.get("created_at"),
            "offline_updated_at": record.get("updated_at"),
        }

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
