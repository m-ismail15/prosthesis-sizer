import json
import os
import uuid
from copy import deepcopy
from datetime import datetime, timezone

from app_paths import user_queue_dir
from auth_client import AuthClientError, sign_in_email_password

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
        self.current_uid = None
        self.current_email = None
        self.current_role = None
        self.current_clinic_id = None
        self.current_id_token = None
        self.last_auth_warning = None

    def _db(self):
        from firebase_config import get_firestore_client

        return get_firestore_client()

    def _clinic_data_from_registry(self, clinic_id: str) -> dict | None:
        clinics = self._db().collection("clinics")

        # Preferred lookup: clinic_id as document ID.
        clinic_doc = clinics.document(clinic_id).get(timeout=FIRESTORE_TIMEOUT_SECONDS)
        if clinic_doc.exists:
            return clinic_doc.to_dict() or {}

        # Compatibility lookup: clinic_id stored as a field on the clinic doc.
        field_matches = list(
            clinics.where("clinic_id", "==", clinic_id)
            .limit(1)
            .stream(timeout=FIRESTORE_TIMEOUT_SECONDS)
        )
        if field_matches:
            return field_matches[0].to_dict() or {}

        return None

    def _clinic_exists_in_legacy_data(self, clinic_id: str) -> bool:
        # Backward compatibility: allow existing deployments that did not yet
        # populate a dedicated `clinics` registry.
        users_match = list(
            self._db()
            .collection("users")
            .where("clinic_id", "==", clinic_id)
            .limit(1)
            .stream(timeout=FIRESTORE_TIMEOUT_SECONDS)
        )
        if users_match:
            return True

        records_match = list(
            self._db()
            .collection("prosthesis_records")
            .where("clinic_id", "==", clinic_id)
            .limit(1)
            .stream(timeout=FIRESTORE_TIMEOUT_SECONDS)
        )
        return bool(records_match)

    def _validate_clinic_id_or_raise(self, clinic_id: str, context: str) -> str:
        normalized = (clinic_id or "").strip()
        if not normalized:
            raise StorageError(f"{context}: clinic_id is required.")

        registry_error = None
        try:
            clinic_data = self._clinic_data_from_registry(normalized)
        except Exception as exc:
            clinic_data = None
            registry_error = exc

        if clinic_data is None:
            try:
                if self._clinic_exists_in_legacy_data(normalized):
                    return normalized
            except Exception as exc:
                if registry_error is not None:
                    raise StorageError(
                        f"Could not validate clinic '{normalized}': "
                        f"registry lookup failed ({registry_error}); "
                        f"legacy lookup failed ({exc})."
                    ) from exc
                raise StorageError(
                    f"Could not validate clinic '{normalized}': {exc}"
                ) from exc

            if registry_error is not None:
                raise StorageError(
                    f"Could not validate clinic '{normalized}' from clinics registry "
                    f"({registry_error}), and no matching clinic_id was found in users or records."
                ) from registry_error
            raise StorageError(
                f"Clinic '{normalized}' does not exist. Contact an administrator."
            )

        if clinic_data.get("active", True) is False:
            raise StorageError(
                f"Clinic '{normalized}' is inactive. Contact an administrator."
            )

        return normalized

    def clinic_exists(self, clinic_id: str, require_active: bool = True) -> bool:
        normalized = (clinic_id or "").strip()
        if not normalized:
            return False

        registry_error = None
        try:
            clinic_data = self._clinic_data_from_registry(normalized)
        except Exception as exc:
            clinic_data = None
            registry_error = exc

        if clinic_data is None:
            try:
                return self._clinic_exists_in_legacy_data(normalized)
            except Exception:
                if registry_error is not None:
                    return False
                return False

        if not require_active:
            return True

        return clinic_data.get("active", True) is not False

    def _current_actor(self) -> dict | None:
        if not self.current_uid and not self.current_email:
            return None

        return {
            "uid": self.current_uid,
            "email": self.current_email,
        }

    def get_authenticated_context(self) -> dict:
        return {
            "uid": self.current_uid,
            "email": self.current_email,
            "role": self.current_role,
            "clinic_id": self.current_clinic_id,
            "id_token": self.current_id_token,
            "warning": self.last_auth_warning,
        }

    def apply_authenticated_context(self, context: dict | None) -> None:
        context = context or {}
        self.current_uid = context.get("uid")
        self.current_email = context.get("email")
        self.current_role = context.get("role")
        self.current_clinic_id = context.get("clinic_id")
        self.current_id_token = context.get("id_token")
        self.last_auth_warning = context.get("warning")

    def authenticate(self, email: str, password: str):
        try:
            auth_result = sign_in_email_password(email, password)
        except AuthClientError as exc:
            raise StorageError(str(exc)) from exc

        self.current_uid = auth_result["uid"]
        self.current_email = auth_result["email"]
        self.current_id_token = auth_result["id_token"]
        self.last_auth_warning = None

        user_doc = (
            self._db()
            .collection("users")
            .document(self.current_uid)
            .get(timeout=FIRESTORE_TIMEOUT_SECONDS)
        )

        role = "prosthetist"
        if user_doc.exists:
            profile = user_doc.to_dict() or {}
            role = profile.get("role", "prosthetist") or "prosthetist"
            if profile.get("active", True) is False:
                raise StorageError(
                    "This user account has been deactivated. Contact an administrator."
                )
            clinic_id = (profile.get("clinic_id") or "").strip()
        else:
            clinic_id = ""

        if not clinic_id:
            raise StorageError(
                "This user is not assigned to a clinic. Please contact an administrator."
            )
        clinic_id = self._validate_clinic_id_or_raise(
            clinic_id,
            "User profile validation failed",
        )

        self.current_role = role
        self.current_clinic_id = clinic_id
        return role

    def save_record(self, payload: dict) -> str:
        from firebase_admin import firestore as fb_firestore

        record = dict(payload)
        clinic_id = self._validate_clinic_id_or_raise(
            (record.get("clinic_id") or self.current_clinic_id or "").strip(),
            "Cannot save record",
        )
        record["clinic_id"] = clinic_id
        record["created_at"] = fb_firestore.SERVER_TIMESTAMP
        record["updated_at"] = fb_firestore.SERVER_TIMESTAMP
        actor = self._current_actor()
        if actor:
            record["created_by"] = actor
            record["updated_by"] = actor
        _, doc_ref = self._db().collection("prosthesis_records").add(
            record,
            timeout=FIRESTORE_TIMEOUT_SECONDS,
        )
        return doc_ref.id

    def update_record(self, record_id: str, payload: dict) -> None:
        from firebase_admin import firestore as fb_firestore

        record = dict(payload)
        clinic_id = self._validate_clinic_id_or_raise(
            (record.get("clinic_id") or self.current_clinic_id or "").strip(),
            "Cannot update record",
        )
        if self.current_clinic_id and clinic_id != self.current_clinic_id:
            raise StorageError("Cannot move a record to a different clinic.")
        record["clinic_id"] = clinic_id
        record["updated_at"] = fb_firestore.SERVER_TIMESTAMP
        actor = self._current_actor()
        if actor:
            record["updated_by"] = actor

        self._db().collection("prosthesis_records").document(record_id).update(
            record,
            timeout=FIRESTORE_TIMEOUT_SECONDS,
        )

    def delete_record(self, record_id: str) -> None:
        self._db().collection("prosthesis_records").document(record_id).delete(
            timeout=FIRESTORE_TIMEOUT_SECONDS
        )

    def list_records(self):
        if not self.current_clinic_id:
            raise StorageError("No clinic is set for the current online session.")

        return list(
            self._db()
            .collection("prosthesis_records")
            .where("clinic_id", "==", self.current_clinic_id)
            .stream(
                timeout=FIRESTORE_TIMEOUT_SECONDS
            )
        )

    def search_records(self, text: str):
        text = text.strip().lower()
        if not text:
            return self.list_records()

        records = self.list_records()
        return [
            record
            for record in records
            if text in record.to_dict().get("name_lower", "")
        ]

    def create_user_account(
        self, email: str, password: str, role: str, clinic_id: str, active: bool = True
    ) -> str:
        from firebase_admin import auth as firebase_auth
        from firebase_admin import firestore as fb_firestore

        normalized_clinic_id = (clinic_id or "").strip()
        normalized_clinic_id = self._validate_clinic_id_or_raise(
            normalized_clinic_id,
            "Cannot create user",
        )

        try:
            user_record = firebase_auth.create_user(email=email, password=password)
        except Exception as exc:
            if type(exc).__name__ == "EmailAlreadyExistsError":
                raise StorageError(
                    "A Firebase Auth user with this email already exists."
                ) from exc
            raise StorageError(f"Could not create Firebase Auth user: {exc}") from exc

        profile = {
            "email": email,
            "email_lower": email.lower(),
            "role": role,
            "active": active,
            "clinic_id": normalized_clinic_id,
            "created_at": fb_firestore.SERVER_TIMESTAMP,
        }
        actor = self._current_actor()
        if actor:
            profile["created_by"] = actor

        try:
            self._db().collection("users").document(user_record.uid).set(
                profile,
                timeout=FIRESTORE_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            rollback_error = None
            try:
                firebase_auth.delete_user(user_record.uid)
            except Exception as rollback_exc:
                rollback_error = str(rollback_exc)

            if rollback_error:
                raise StorageError(
                    "Could not create Firestore user profile and rollback failed: "
                    f"{rollback_error}"
                ) from exc

            raise StorageError(
                "Could not create Firestore user profile. The Firebase Auth user was rolled back."
            ) from exc

        return user_record.uid

    def list_user_profiles(self) -> list[dict]:
        docs = self._db().collection("users").stream(timeout=FIRESTORE_TIMEOUT_SECONDS)
        profiles = []
        for doc in docs:
            data = doc.to_dict() or {}
            stored_role = data.get("role", "user") or "user"
            profiles.append(
                {
                    "uid": doc.id,
                    "email": data.get("email", ""),
                    "role": "admin" if stored_role == "admin" else "user",
                    "active": bool(data.get("active", True)),
                    "clinic_id": (data.get("clinic_id") or "").strip(),
                }
            )

        profiles.sort(key=lambda item: item["email"].lower())
        return profiles

    def update_user_profile(self, uid: str, role: str, active: bool) -> None:
        from firebase_admin import firestore as fb_firestore

        updates = {
            "role": role,
            "active": active,
            "updated_at": fb_firestore.SERVER_TIMESTAMP,
        }
        actor = self._current_actor()
        if actor:
            updates["updated_by"] = actor

        self._db().collection("users").document(uid).set(
            updates,
            merge=True,
            timeout=FIRESTORE_TIMEOUT_SECONDS,
        )

    def change_current_user_password(self, new_password: str) -> None:
        from firebase_admin import auth as firebase_auth

        if not self.current_uid:
            raise StorageError("No authenticated Firebase user is available.")

        try:
            firebase_auth.update_user(self.current_uid, password=new_password)
        except Exception as exc:
            raise StorageError(f"Could not update password: {exc}") from exc


# ---------------- LOCAL OFFLINE STORE ---------------- #
class LocalJsonStore:
    mode_name = "offline"

    def __init__(self, file_path: str | None = None, clinic_id: str | None = None):
        self.file_path = file_path or default_local_store_path()
        self.current_uid = None
        self.current_email = None
        self.current_role = "prosthetist"
        self.current_clinic_id = self._normalize_clinic_id(clinic_id)

    def authenticate(self, email: str, password: str):
        # Offline mode is intentionally credential-free.
        return "prosthetist"

    def get_authenticated_context(self) -> dict:
        return {
            "uid": self.current_uid,
            "email": self.current_email,
            "role": self.current_role,
            "clinic_id": self.current_clinic_id,
        }

    def apply_authenticated_context(self, context: dict | None) -> None:
        context = context or {}
        self.current_uid = context.get("uid")
        self.current_email = context.get("email")
        self.current_role = context.get("role") or "prosthetist"
        self.current_clinic_id = self._normalize_clinic_id(context.get("clinic_id"))

    def change_current_user_password(self, new_password: str) -> None:
        raise StorageError("Password changes are only available in online mode.")

    def save_record(self, payload: dict) -> str:
        data = self._read_data()
        timestamp = datetime.now(timezone.utc).isoformat()

        record = dict(payload)
        clinic_id = self._normalize_clinic_id(
            record.get("clinic_id") or self.current_clinic_id
        )
        if not clinic_id:
            raise StorageError(
                "Offline records require a clinic ID. Enter a clinic ID before saving."
            )
        if self.current_clinic_id and clinic_id != self.current_clinic_id:
            raise StorageError("Offline session is locked to a different clinic.")
        if not self.current_clinic_id:
            self.current_clinic_id = clinic_id
        # Keep the saved structure close to Firestore records so the UI stays simple.
        # This file acts as a pending-sync queue, not a permanent local archive.
        record_id = uuid.uuid4().hex
        record["id"] = record_id
        record["clinic_id"] = clinic_id
        record["created_at"] = timestamp
        record["updated_at"] = timestamp

        data["prosthesis_records"].append(record)
        self._write_data(data)
        return record_id

    def list_records(self):
        data = self._read_data()
        records = sorted(
            [
                record
                for record in data["prosthesis_records"]
                if self._record_visible_to_current_clinic(record)
            ],
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

    def update_record(self, record_id: str, payload: dict) -> None:
        data = self._read_data()
        timestamp = datetime.now(timezone.utc).isoformat()

        for index, record in enumerate(data["prosthesis_records"]):
            if record.get("id") != record_id:
                continue
            existing_clinic_id = self._normalize_clinic_id(record.get("clinic_id"))
            if self.current_clinic_id and existing_clinic_id != self.current_clinic_id:
                raise StorageError("Record belongs to a different clinic.")

            updated_record = dict(payload)
            updated_clinic_id = self._normalize_clinic_id(
                updated_record.get("clinic_id")
                or existing_clinic_id
                or self.current_clinic_id
            )
            if not updated_clinic_id:
                raise StorageError(
                    "Cannot update an offline record without a clinic assignment."
                )
            if self.current_clinic_id and updated_clinic_id != self.current_clinic_id:
                raise StorageError("Record belongs to a different clinic.")
            updated_record["id"] = record_id
            updated_record["clinic_id"] = updated_clinic_id
            updated_record["created_at"] = record.get("created_at", timestamp)
            updated_record["updated_at"] = timestamp
            data["prosthesis_records"][index] = updated_record
            self._write_data(data)
            return

        raise StorageError(f"Record not found: {record_id}")

    def delete_record(self, record_id: str) -> None:
        data = self._read_data()
        original_count = len(data["prosthesis_records"])
        data["prosthesis_records"] = [
            record
            for record in data["prosthesis_records"]
            if record.get("id") != record_id
        ]
        if len(data["prosthesis_records"]) == original_count:
            raise StorageError(f"Record not found: {record_id}")
        self._write_data(data)

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
        online_clinic_id = self._normalize_clinic_id(
            getattr(online_store, "current_clinic_id", None)
        )

        for record in all_records:
            if record.get("synced_to_online", False):
                # Clean up legacy entries created by the previous "mark as synced" approach.
                continue

            record_clinic_id = self._normalize_clinic_id(record.get("clinic_id"))
            if not record_clinic_id:
                result["failed_count"] += 1
                result["errors"].append(
                    f"{record.get('name', 'Unknown')}: Missing clinic_id. Record was not synced."
                )
                remaining_records.append(record)
                continue

            if not online_clinic_id:
                result["failed_count"] += 1
                result["errors"].append(
                    f"{record.get('name', 'Unknown')}: Online session has no clinic context."
                )
                remaining_records.append(record)
                continue

            if record_clinic_id != online_clinic_id:
                result["failed_count"] += 1
                result["errors"].append(
                    f"{record.get('name', 'Unknown')}: clinic_id mismatch "
                    f"(record: {record_clinic_id}, user: {online_clinic_id})."
                )
                remaining_records.append(record)
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
            "clinic_id": record.get("clinic_id"),
            "source_mode": "offline_sync",
            "offline_record_id": record.get("id"),
            "offline_created_at": record.get("created_at"),
            "offline_updated_at": record.get("updated_at"),
        }

    def _normalize_clinic_id(self, clinic_id: object) -> str | None:
        if clinic_id is None:
            return None
        normalized = str(clinic_id).strip()
        return normalized or None

    def _record_visible_to_current_clinic(self, record: dict) -> bool:
        if not self.current_clinic_id:
            return False
        return self._normalize_clinic_id(record.get("clinic_id")) == self.current_clinic_id

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
