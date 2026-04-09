# Desktop GUI
import os
import sys
from datetime import datetime

from auth_client import is_firebase_auth_configured
from PyQt6.QtCore import QObject, QElapsedTimer, QRegularExpression, QThread, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen, QPixmap, QRegularExpressionValidator
from PyQt6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPushButton, QScrollArea, QSizePolicy, QSplashScreen, QStackedWidget, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from app_paths import install_base_dir, user_config_dir
from app_version import APP_VERSION
from firebase_config import is_firebase_configured
from sizing import compute_prosthesis_size
from storage import FirebaseStore, LocalJsonStore, StorageError, default_local_store_path


# ---------------- RESOURCE HELPERS ---------------- #
def resource_base_dir() -> str:
    """Base folder for resources in dev and in the packaged EXE."""
    return install_base_dir()


def resource_path(relative_path: str) -> str:
    return os.path.join(resource_base_dir(), relative_path)


# ---------------- SPLASH SCREEN ---------------- #
def create_splash_pixmap() -> QPixmap:
    """Create a branded splash image using the packaged background asset."""
    width = 720
    height = 420
    pixmap = QPixmap(width, height)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    splash_bg_color = QColor("#cce5ff")
    painter.fillRect(pixmap.rect(), splash_bg_color)

    bg_path = resource_path("MedTechBG.png")
    bg_logo = QPixmap(bg_path)
    if not bg_logo.isNull():
        scaled_logo = bg_logo.scaled(
            width - 56,
            height - 56,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        bg_left = (width - scaled_logo.width()) // 2
        bg_top = (height - scaled_logo.height()) // 2
        painter.drawPixmap(bg_left, bg_top, scaled_logo)

    overlay = QLinearGradient(0, 0, 0, height)
    overlay.setColorAt(0.0, QColor(255, 255, 255, 55))
    overlay.setColorAt(0.45, QColor(255, 255, 255, 85))
    overlay.setColorAt(1.0, QColor(255, 255, 255, 125))
    painter.fillRect(pixmap.rect(), overlay)

    panel_left = 34
    panel_top = 18
    panel_width = width - 68
    panel_height = height - 36

    panel_color = QColor(248, 252, 255, 226)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(panel_color)
    painter.drawRoundedRect(panel_left, panel_top, panel_width, panel_height, 28, 28)

    title_font = QFont("Segoe UI", 24, QFont.Weight.Bold)
    subtitle_font = QFont("Segoe UI", 18, QFont.Weight.DemiBold)
    version_font = QFont("Segoe UI", 10, QFont.Weight.DemiBold)

    title_top = panel_top + 110
    subtitle_top = title_top + 40
    divider_y = subtitle_top + 50

    painter.setPen(QColor("#1A1930"))
    painter.setFont(title_font)
    painter.drawText(
        panel_left,
        title_top,
        panel_width,
        36,
        int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter),
        "UCT MedTech",
    )

    painter.setFont(subtitle_font)
    painter.setPen(QColor("#353C5C"))
    painter.drawText(
        panel_left,
        subtitle_top,
        panel_width,
        32,
        int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter),
        "Prosthesis Sizing Application",
    )

    painter.setPen(QPen(QColor("#8ea8a8"), 2))
    painter.drawLine(panel_left + 42, divider_y, width - panel_left - 42, divider_y)

    painter.setFont(version_font)
    painter.setPen(QColor("#56412f"))
    painter.drawText(
        panel_left,
        panel_top + panel_height - 74,
        panel_width,
        24,
        int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter),
        f"Version {APP_VERSION}",
    )

    painter.end()
    return pixmap


class OnlineLoginWorker(QObject):
    finished = pyqtSignal(str)
    invalid_credentials = pyqtSignal(str)
    error = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, email: str, password: str):
        super().__init__()
        self.email = email
        self.password = password
        self.auth_context = {}

    def run(self):
        try:
            self.progress.emit("Signing in...")
            # Create the Firebase client inside the worker thread to avoid
            # cross-thread use of network-bound client objects.
            online_store = FirebaseStore()
            role = online_store.authenticate(self.email, self.password)
            self.auth_context = online_store.get_authenticated_context()
            self.finished.emit(role)
        except StorageError as exc:
            if str(exc) == "Invalid email or password.":
                self.invalid_credentials.emit(str(exc))
                return
            self.error.emit(str(exc))
        except Exception as exc:
            self.error.emit(str(exc))


class OfflineSyncWorker(QObject):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, offline_store, auth_context: dict | None = None):
        super().__init__()
        self.offline_store = offline_store
        self.auth_context = auth_context or {}

    def run(self):
        try:
            online_store = FirebaseStore()
            online_store.apply_authenticated_context(self.auth_context)
            sync_result = self.offline_store.sync_pending_records(online_store)
            self.finished.emit(sync_result)
        except Exception as exc:
            self.error.emit(str(exc))


# ---------------- LOGIN WINDOW ---------------- #
class LoginWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Login")
        self.setGeometry(300, 200, 420, 240)

        self.online_store = None
        self.online_error = ""
        self.last_online_context = {}
        self.offline_store = LocalJsonStore(
            default_local_store_path(),
            clinic_id=None,
        )
        self.offline_store.apply_authenticated_context(self.last_online_context)
        self.login_thread = None
        self.login_worker = None

        self._try_enable_online_mode()
        self._build_ui()

    def _try_enable_online_mode(self):
        preferred_mode = os.getenv("PROSTHESIS_APP_MODE", "auto").strip().lower()
        if preferred_mode == "offline":
            self.online_error = "Offline mode forced by PROSTHESIS_APP_MODE=offline."
            return

        if not is_firebase_configured():
            self.online_error = "Firebase service account key not found."
            return

        if is_firebase_auth_configured():
            # Delay Firestore client creation until the user actually signs in.
            self.online_store = FirebaseStore()
        else:
            self.online_error = (
                "FIREBASE_WEB_API_KEY is not set for Firebase Authentication."
            )

    def _build_ui(self):
        layout = QVBoxLayout()

        layout.addWidget(QLabel("Email:"))
        self.email_input = QLineEdit()
        self.email_input.returnPressed.connect(self.login_online)
        layout.addWidget(self.email_input)

        layout.addWidget(QLabel("Password:"))
        password_row = QHBoxLayout()
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.returnPressed.connect(self.login_online)
        password_row.addWidget(self.password_input)

        self.password_visibility_btn = QPushButton("Show")
        self.password_visibility_btn.pressed.connect(
            self.show_login_password
        )
        self.password_visibility_btn.released.connect(
            self.hide_login_password
        )
        password_row.addWidget(self.password_visibility_btn)
        layout.addLayout(password_row)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.login_btn = QPushButton("Login Online")
        self.login_btn.clicked.connect(self.login_online)
        layout.addWidget(self.login_btn)

        self.offline_btn = QPushButton("Continue Offline")
        self.offline_btn.clicked.connect(self.open_offline_mode)
        layout.addWidget(self.offline_btn)

        if self.online_store is not None:
            self.status_label.setText(
                "Online mode is available. Continue Offline keeps records in a temporary local queue until they are synced online. "
                "Enter a clinic ID when saving an offline record."
            )
        else:
            self.status_label.setText(
                "Online mode is unavailable. Continue Offline will store records in a temporary local queue until online sync is available.\n"
                f"Online mode can use a Firebase key from {user_config_dir()}.\n\n"
                f"Reason: {self.online_error}"
            )

        self.setLayout(layout)

    def login_online(self):
        if self.online_store is None:
            self.status_label.setText(
                "Online mode is unavailable. Use Continue Offline to queue records locally."
            )
            return

        email = self.email_input.text().strip().lower()
        password = self.password_input.text().strip()

        if not email or not password:
            self.status_label.setText("Please enter email and password.")
            return

        if self.login_thread is not None:
            return

        self._set_busy_state(True, "Signing in...")
        self.login_thread = QThread(self)
        self.login_worker = OnlineLoginWorker(email, password)
        self.login_worker.moveToThread(self.login_thread)

        self.login_thread.started.connect(self.login_worker.run)
        self.login_worker.progress.connect(self.status_label.setText)
        self.login_worker.invalid_credentials.connect(self._handle_login_invalid)
        self.login_worker.error.connect(self._handle_login_error)
        self.login_worker.finished.connect(self._handle_login_success)
        self.login_worker.finished.connect(self.login_thread.quit)
        self.login_worker.invalid_credentials.connect(self.login_thread.quit)
        self.login_worker.error.connect(self.login_thread.quit)
        self.login_thread.finished.connect(self._cleanup_login_thread)

        self.login_thread.start()

    def open_offline_mode(self):
        try:
            clinic_id = getattr(self.offline_store, "current_clinic_id", None)
            self.open_main_app(self.offline_store, "prosthetist", clinic_id=clinic_id)
        except StorageError as exc:
            QMessageBox.critical(self, "Offline Mode Error", str(exc))

    def sync_offline_records(self) -> dict | None:
        try:
            return self.offline_store.sync_pending_records(self.online_store)
        except StorageError as exc:
            return {
                "pending_count": 0,
                "synced_count": 0,
                "failed_count": 1,
                "errors": [str(exc)],
            }

    def show_sync_result(self, sync_result: dict | None):
        if not sync_result:
            return

        if sync_result["pending_count"] == 0:
            return

        if sync_result["failed_count"] == 0:
            QMessageBox.information(
                self.main_app,
                "Offline Sync Complete",
                f"Synced {sync_result['synced_count']} offline record(s) to online storage and cleared them from the local queue.",
            )
            return

        error_text = "\n".join(sync_result["errors"][:3])
        if len(sync_result["errors"]) > 3:
            error_text += "\n..."

        QMessageBox.warning(
            self.main_app,
            "Offline Sync Incomplete",
            f"Synced {sync_result['synced_count']} of {sync_result['pending_count']} "
            f"offline record(s). Unsynced records remain in the local queue.\n\n{error_text}",
        )

    def _set_busy_state(self, busy: bool, message: str = ""):
        self.login_btn.setEnabled(not busy)
        self.offline_btn.setEnabled(not busy)
        self.email_input.setEnabled(not busy)
        self.password_input.setEnabled(not busy)
        self.password_visibility_btn.setEnabled(not busy)
        if message:
            self.status_label.setText(message)

    def show_login_password(self):
        self.password_input.setEchoMode(QLineEdit.EchoMode.Normal)

    def hide_login_password(self):
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)

    def _handle_login_invalid(self, error_message: str):
        self._set_busy_state(False, error_message)

    def _handle_login_error(self, error_message: str):
        self._set_busy_state(
            False,
            "Could not log in online. Use Continue Offline to queue records locally.\n\n"
            f"Reason: {error_message}",
        )

    def _handle_login_success(self, role: str):
        self._set_busy_state(False)
        authenticated_store = FirebaseStore()
        authenticated_store.apply_authenticated_context(self.login_worker.auth_context)
        self.online_store = authenticated_store
        self.last_online_context = self.online_store.get_authenticated_context()
        self.offline_store.apply_authenticated_context(self.last_online_context)
        self.open_main_app(
            self.online_store,
            role,
            clinic_id=self.last_online_context.get("clinic_id"),
        )
        if self.online_store.last_auth_warning:
            QMessageBox.warning(
                self.main_app,
                "User Profile Warning",
                self.online_store.last_auth_warning,
            )
        QTimer.singleShot(0, self.main_app.start_offline_sync)

    def _cleanup_login_thread(self):
        if self.login_worker is not None:
            self.login_worker.deleteLater()
        if self.login_thread is not None:
            self.login_thread.deleteLater()
        self.login_worker = None
        self.login_thread = None

    def open_main_app(self, store, role: str, clinic_id: str | None = None):
        self.hide()
        self.main_app = ProsthesisApp(
            store=store,
            role=role,
            clinic_id=clinic_id,
            login_window=self,
        )
        self.main_app.show()


# ---------------- MAIN APPLICATION ---------------- #
class ProsthesisApp(QMainWindow):
    def __init__(
        self,
        store,
        role: str = "prosthetist",
        clinic_id: str | None = None,
        login_window=None,
    ):
        super().__init__()
        self.store = store
        self.role = role
        self.clinic_id = clinic_id or getattr(self.store, "current_clinic_id", None)
        self.login_window = login_window
        self.is_admin = self.role == "admin"
        self.sync_thread = None
        self.sync_worker = None
        self.current_record_id = None
        self.record_lookup = {}
        self.user_lookup = {}
        self._refresh_window_title()
        self.setGeometry(100, 100, 900, 600)

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.home_page = self.build_home()
        self.profile_page = self.build_profile_page()
        self.records_page = self.build_records()
        self.guide_page = self.build_measurement_guide()
        self.admin_page = self.build_admin_panel() if self.is_admin else None

        self.stack.addWidget(self.home_page)
        self.stack.addWidget(self.profile_page)
        self.stack.addWidget(self.records_page)
        self.stack.addWidget(self.guide_page)
        if self.admin_page is not None:
            self.stack.addWidget(self.admin_page)

        nav = QWidget()
        nav_layout = QHBoxLayout()
        nav.setLayout(nav_layout)

        home_btn = QPushButton("Home")
        profile_btn = QPushButton("Profile")
        records_btn = QPushButton("Records")
        guide_btn = QPushButton("Measurement Guide")
        admin_btn = QPushButton("Admin Panel") if self.admin_page is not None else None
        self.toolbar_logout_btn = QPushButton("Log Out")
        self.toolbar_logout_btn.clicked.connect(self.log_out)

        home_btn.clicked.connect(lambda: self.stack.setCurrentWidget(self.home_page))
        profile_btn.clicked.connect(self.show_profile_page)

        def show_records():
            self.stack.setCurrentWidget(self.records_page)
            self.load_records()

        records_btn.clicked.connect(show_records)
        guide_btn.clicked.connect(lambda: self.stack.setCurrentWidget(self.guide_page))
        if admin_btn is not None:
            admin_btn.clicked.connect(self.show_admin_panel)

        nav_layout.addWidget(home_btn)
        nav_layout.addWidget(profile_btn)
        nav_layout.addWidget(records_btn)
        nav_layout.addWidget(guide_btn)
        if admin_btn is not None:
            nav_layout.addWidget(admin_btn)
        spacer = QWidget()
        spacer.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        nav_layout.addWidget(spacer)
        nav_layout.addWidget(self.toolbar_logout_btn)
        self.addToolBar("Navigation").addWidget(nav)

        self.statusBar().showMessage(self._mode_status_message())

    def _refresh_window_title(self):
        self.setWindowTitle(
            f"Prosthesis Sizing App v{APP_VERSION} - {self.store.mode_name.title()} Mode "
            f"- Role: {self.role} - Clinic: {self.clinic_id or 'Unassigned'}"
        )

    def _mode_status_message(self) -> str:
        message = f"Running in {self.store.mode_name} mode."
        if self.store.mode_name == "offline":
            message += (
                " Pending records stay in a temporary local queue until they are synced online."
                f" Queue file: {default_local_store_path()}"
            )
        else:
            message += f" Firebase key search includes: {user_config_dir()}"
        message += f" Current clinic: {self.clinic_id or 'Unassigned'}."
        return message

    def _profile_summary_text(self) -> str:
        email = getattr(self.store, "current_email", "") or "Offline user"
        return (
            f"Signed in as: {email}\nRole: {self.role}\n"
            f"Clinic: {self.clinic_id or 'Unassigned'}\nMode: {self.store.mode_name.title()}"
        )

    def _set_clinic_context(self, clinic_id: str | None) -> None:
        normalized = (clinic_id or "").strip() or None
        self.clinic_id = normalized
        if hasattr(self.store, "current_clinic_id"):
            self.store.current_clinic_id = normalized

        self._refresh_window_title()
        self.statusBar().showMessage(self._mode_status_message())
        if hasattr(self, "profile_summary_label"):
            self.profile_summary_label.setText(self._profile_summary_text())
        if (
            self.store.mode_name == "offline"
            and hasattr(self, "offline_clinic_input")
            and normalized
        ):
            self.offline_clinic_input.setText(normalized)
            # Once chosen offline, keep session clinic stable to avoid mixed-clinic queues.
            self.offline_clinic_input.setReadOnly(True)

    def start_offline_sync(self):
        if self.store.mode_name != "online" or self.sync_thread is not None:
            return

        self.statusBar().showMessage("Checking for queued offline records to sync...")
        self.sync_thread = QThread(self)
        auth_context = (
            self.store.get_authenticated_context()
            if hasattr(self.store, "get_authenticated_context")
            else {}
        )
        self.sync_worker = OfflineSyncWorker(
            LocalJsonStore(default_local_store_path()),
            auth_context=auth_context,
        )
        self.sync_worker.moveToThread(self.sync_thread)

        self.sync_thread.started.connect(self.sync_worker.run)
        self.sync_worker.finished.connect(self._handle_sync_finished)
        self.sync_worker.error.connect(self._handle_sync_error)
        self.sync_worker.finished.connect(self.sync_thread.quit)
        self.sync_worker.error.connect(self.sync_thread.quit)
        self.sync_thread.finished.connect(self._cleanup_sync_thread)

        self.sync_thread.start()

    def _handle_sync_finished(self, sync_result: dict | None):
        if not sync_result or sync_result["pending_count"] == 0:
            self.statusBar().showMessage("Online mode ready.")
            return

        if sync_result["failed_count"] == 0:
            self.statusBar().showMessage(
                f"Synced {sync_result['synced_count']} offline record(s)."
            )
            return

        error_text = "\n".join(sync_result["errors"][:3])
        if len(sync_result["errors"]) > 3:
            error_text += "\n..."

        QMessageBox.warning(
            self,
            "Offline Sync Incomplete",
            f"Synced {sync_result['synced_count']} of {sync_result['pending_count']} offline record(s).\n\n"
            f"Skipped records:\n{error_text}",
        )
        self.statusBar().showMessage(
            f"Synced {sync_result['synced_count']} of {sync_result['pending_count']} offline record(s)."
        )

    def _handle_sync_error(self, error_message: str):
        self.statusBar().showMessage(f"Offline sync failed: {error_message}")

    def _cleanup_sync_thread(self):
        if self.sync_worker is not None:
            self.sync_worker.deleteLater()
        if self.sync_thread is not None:
            self.sync_thread.deleteLater()
        self.sync_worker = None
        self.sync_thread = None

    # ---------------- HOME PAGE ---------------- #
    def build_home(self):
        page = QWidget()
        layout = QVBoxLayout()

        layout.addWidget(QLabel("Enter Patient Measurements:"))

        self.clear_fields_btn = QPushButton("Clear All Fields")
        self.clear_fields_btn.clicked.connect(self.reset_form)
        layout.addWidget(self.clear_fields_btn)

        self.name_input = QLineEdit()
        layout.addWidget(QLabel("Patient Name:"))
        layout.addWidget(self.name_input)

        self.offline_clinic_label = QLabel("Clinic ID (required offline):")
        self.offline_clinic_input = QLineEdit()
        self.offline_clinic_input.setPlaceholderText("Enter clinic ID")
        if self.store.mode_name == "online":
            self.offline_clinic_label.setVisible(False)
            self.offline_clinic_input.setVisible(False)
        else:
            if self.clinic_id:
                self.offline_clinic_input.setText(self.clinic_id)
                self.offline_clinic_input.setReadOnly(True)
        layout.addWidget(self.offline_clinic_label)
        layout.addWidget(self.offline_clinic_input)

        self.bicep_input = QLineEdit()
        self.forearm_input = QLineEdit()
        self.humerus_input = QLineEdit()
        self.residuum_input = QLineEdit()

        # Allow up to one decimal place using either "." or ",".
        validator = QRegularExpressionValidator(
            QRegularExpression(r"^\d{0,5}(?:[.,]\d{0,1})?$"),
            self,
        )
        for field in [
            self.bicep_input,
            self.forearm_input,
            self.humerus_input,
            self.residuum_input,
        ]:
            field.setValidator(validator)

        layout.addWidget(QLabel("Flexed Bicep Circumference (mm):"))
        layout.addWidget(self.bicep_input)

        layout.addWidget(QLabel("Flexed Forearm Circumference (mm):"))
        layout.addWidget(self.forearm_input)

        layout.addWidget(QLabel("AcromioRadiale Length (mm):"))
        layout.addWidget(self.humerus_input)

        layout.addWidget(QLabel("RadialeStylion Length (mm):"))
        layout.addWidget(self.residuum_input)

        button_row = QHBoxLayout()
        self.submit_btn = QPushButton("Calculate")
        self.submit_btn.clicked.connect(self.calculate_patient_data)
        button_row.addWidget(self.submit_btn)

        self.cancel_edit_btn = QPushButton("Cancel Edit")
        self.cancel_edit_btn.clicked.connect(self.reset_form)
        self.cancel_edit_btn.setVisible(False)
        button_row.addWidget(self.cancel_edit_btn)

        layout.addLayout(button_row)

        page.setLayout(layout)
        return page

    def build_profile_page(self):
        page = QWidget()
        layout = QVBoxLayout()

        layout.addWidget(QLabel("User Profile"))

        self.profile_summary_label = QLabel(self._profile_summary_text())
        self.profile_summary_label.setWordWrap(True)
        layout.addWidget(self.profile_summary_label)

        self.profile_status_label = QLabel("")
        self.profile_status_label.setWordWrap(True)
        layout.addWidget(self.profile_status_label)

        layout.addWidget(QLabel("<b>Create New Password</b>"))

        layout.addWidget(QLabel("New Password:"))
        password_row = QHBoxLayout()
        self.profile_password_input = QLineEdit()
        self.profile_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        password_row.addWidget(self.profile_password_input)

        self.profile_password_visibility_btn = QPushButton("Show")
        self.profile_password_visibility_btn.pressed.connect(
            self.show_profile_passwords
        )
        self.profile_password_visibility_btn.released.connect(
            self.hide_profile_passwords
        )
        password_row.addWidget(self.profile_password_visibility_btn)
        layout.addLayout(password_row)

        layout.addWidget(QLabel("Confirm Password:"))
        self.profile_confirm_password_input = QLineEdit()
        self.profile_confirm_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.profile_confirm_password_input)

        self.profile_change_password_btn = QPushButton("Change Password")
        self.profile_change_password_btn.clicked.connect(self.change_password)
        layout.addWidget(self.profile_change_password_btn)

        if self.store.mode_name != "online":
            self.profile_status_label.setText(
                "Password changes are only available in online mode."
            )
            self.profile_password_input.setEnabled(False)
            self.profile_confirm_password_input.setEnabled(False)
            self.profile_password_visibility_btn.setEnabled(False)
            self.profile_change_password_btn.setEnabled(False)

        page.setLayout(layout)
        return page

    def show_profile_page(self):
        self.profile_summary_label.setText(self._profile_summary_text())
        self.stack.setCurrentWidget(self.profile_page)

    def _parse_measurement_value(self, text: str, label: str) -> float:
        normalized = text.strip().replace(",", ".")
        if not normalized:
            raise ValueError(f"{label} is required.")
        if normalized.count(".") > 1:
            raise ValueError(f"{label} must be a valid number.")
        if "." in normalized and len(normalized.split(".", 1)[1]) > 1:
            raise ValueError(f"{label} may have at most one decimal place.")

        try:
            value = float(normalized)
        except ValueError as exc:
            raise ValueError(f"{label} must be a valid number.") from exc

        if value < 0 or value > 10000:
            raise ValueError(f"{label} must be between 0 and 10000.")

        return value

    def calculate_patient_data(self):
        clinic_id = self.clinic_id
        if self.store.mode_name == "offline":
            entered_clinic_id = self.offline_clinic_input.text().strip()
            if entered_clinic_id:
                clinic_id = entered_clinic_id
            if self.clinic_id and clinic_id != self.clinic_id:
                QMessageBox.warning(
                    self,
                    "Clinic Locked",
                    f"Offline session is using clinic '{self.clinic_id}'. "
                    "Start a new session to use a different clinic.",
                )
                return
            if not clinic_id:
                QMessageBox.warning(
                    self,
                    "Clinic Required",
                    "Enter a clinic ID before saving an offline record.",
                )
                return
            if clinic_id != self.clinic_id:
                self._set_clinic_context(clinic_id)
        elif not clinic_id:
            QMessageBox.warning(
                self,
                "Clinic Required",
                "This session has no clinic assignment, so records cannot be saved.",
            )
            return

        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Missing Name", "Please enter the patient name.")
            return

        try:
            bc = self._parse_measurement_value(
                self.bicep_input.text(), "Flexed Bicep Circumference"
            )
            fc = self._parse_measurement_value(
                self.forearm_input.text(), "Flexed Forearm Circumference"
            )
            ar = self._parse_measurement_value(
                self.humerus_input.text(), "AcromioRadiale Length"
            )
            rs = self._parse_measurement_value(
                self.residuum_input.text(), "RadialeStylion Length"
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Input", str(exc))
            return

        result = compute_prosthesis_size(bc, fc, ar, rs)

        payload = {
            "name": name,
            "name_lower": name.lower(),
            "clinic_id": clinic_id,
            "bicep_circ": bc,
            "forearm_circ": fc,
            "humerus_len": ar,
            "residuum_len": rs,
            "width_size": result["width"],
            "humeral_length": result["humeral_length"],
            "radial_length": result["radial_length"],
            "sizing_note": result["message"],
        }

        dialog = QMessageBox(self)
        dialog.setWindowTitle("Sizing Result")
        dialog.setIcon(QMessageBox.Icon.Information)
        dialog.setText(
            f"Width: {result['width']}\n"
            f"Humeral Length: {result['humeral_length']}\n"
            f"Radial Length: {result['radial_length']}\n\n"
            f"{result['message']}\n\n"
            "Save this result?"
        )
        save_button = dialog.addButton("Save", QMessageBox.ButtonRole.AcceptRole)
        dialog.addButton("Don't Save", QMessageBox.ButtonRole.RejectRole)
        dialog.exec()

        if dialog.clickedButton() is not save_button:
            return

        try:
            if self.current_record_id is not None:
                if not self._require_admin(
                    "Only admins can update existing patient records."
                ):
                    return
                self.store.update_record(self.current_record_id, payload)
            else:
                self.store.save_record(payload)
        except Exception as exc:
            QMessageBox.critical(self, "Save Failed", str(exc))
            return

        self.reset_form()
        if self.stack.currentWidget() == self.records_page:
            self.load_records()

    def reset_form(self):
        self.current_record_id = None
        self.name_input.clear()
        self.bicep_input.clear()
        self.forearm_input.clear()
        self.humerus_input.clear()
        self.residuum_input.clear()
        self.submit_btn.setText("Calculate")
        self.cancel_edit_btn.setVisible(False)

    def log_out(self):
        confirm = QMessageBox.question(
            self,
            "Log Out",
            "Log out and return to the login screen?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        self.reset_form()
        if self.login_window is not None:
            self.login_window.email_input.clear()
            self.login_window.password_input.clear()
            self.login_window.status_label.setText("")
            self.login_window.show()
            self.login_window.raise_()
            self.login_window.activateWindow()
            self.login_window.main_app = None
            self.login_window.hide_login_password()
        self.close()

    def show_profile_passwords(self):
        echo_mode = QLineEdit.EchoMode.Normal
        self.profile_password_input.setEchoMode(echo_mode)
        self.profile_confirm_password_input.setEchoMode(echo_mode)

    def hide_profile_passwords(self):
        echo_mode = QLineEdit.EchoMode.Password
        self.profile_password_input.setEchoMode(echo_mode)
        self.profile_confirm_password_input.setEchoMode(echo_mode)

    def change_password(self):
        if self.store.mode_name != "online":
            QMessageBox.warning(
                self,
                "Unavailable Offline",
                "Password changes are only available in online mode.",
            )
            return

        new_password = self.profile_password_input.text().strip()
        confirm_password = self.profile_confirm_password_input.text().strip()

        if len(new_password) < 8:
            QMessageBox.warning(
                self,
                "Invalid Password",
                "New password must be at least 8 characters long.",
            )
            return

        if new_password != confirm_password:
            QMessageBox.warning(
                self,
                "Password Mismatch",
                "The password confirmation does not match.",
            )
            return

        try:
            self.store.change_current_user_password(new_password)
        except Exception as exc:
            QMessageBox.critical(self, "Password Change Failed", str(exc))
            return

        self.profile_password_input.clear()
        self.profile_confirm_password_input.clear()
        self.hide_profile_passwords()
        self.profile_status_label.setText("Password updated successfully.")
        QMessageBox.information(
            self,
            "Password Updated",
            "Your password has been updated successfully.",
        )

    def _load_record_into_form(self, record_id: str):
        record = self.record_lookup.get(record_id)
        if not record:
            QMessageBox.warning(self, "Record Missing", "The selected record could not be loaded.")
            return

        self.current_record_id = record_id
        self.name_input.setText(record.get("name", ""))
        self.bicep_input.setText(str(record.get("bicep_circ", "")))
        self.forearm_input.setText(str(record.get("forearm_circ", "")))
        self.humerus_input.setText(str(record.get("humerus_len", "")))
        self.residuum_input.setText(str(record.get("residuum_len", "")))
        self.submit_btn.setText("Update Record")
        self.cancel_edit_btn.setVisible(True)
        self.stack.setCurrentWidget(self.home_page)

    # ---------------- RECORDS PAGE ---------------- #
    def build_records(self):
        page = QWidget()
        layout = QVBoxLayout()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search patient...")
        self.search_input.returnPressed.connect(self.search_records)

        search_btn = QPushButton("Search")
        search_btn.clicked.connect(self.search_records)

        search_layout = QHBoxLayout()
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(search_btn)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.load_records)
        search_layout.addWidget(refresh_btn)

        self.table = QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Name", "BC", "FC", "Width", "Hum Len", "Rad Len", "Created/Updated", "Note"]
        )
        self.table.setColumnHidden(0, True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        layout.addLayout(search_layout)
        layout.addWidget(self.table)

        admin_actions = QHBoxLayout()
        self.edit_record_btn = QPushButton("Edit Selected")
        self.edit_record_btn.clicked.connect(self.edit_selected_record)
        self.delete_record_btn = QPushButton("Delete Selected")
        self.delete_record_btn.clicked.connect(self.delete_selected_record)
        self.edit_record_btn.setVisible(self.is_admin)
        self.delete_record_btn.setVisible(self.is_admin)
        admin_actions.addWidget(self.edit_record_btn)
        admin_actions.addWidget(self.delete_record_btn)
        layout.addLayout(admin_actions)

        page.setLayout(layout)
        return page

    def load_records(self):
        try:
            self.display_records(self.store.list_records())
        except Exception as exc:
            QMessageBox.critical(self, "Load Failed", str(exc))

    def search_records(self):
        text = self.search_input.text().strip().lower()
        try:
            records = self.store.search_records(text)
            self.display_records(records)
        except Exception as exc:
            QMessageBox.critical(self, "Search Failed", str(exc))

    def display_records(self, records):
        self.table.setRowCount(0)
        self.record_lookup = {}
        for row_index, record in enumerate(records):
            data = record.to_dict()
            self.record_lookup[record.id] = data
            self.table.insertRow(row_index)
            self.table.setItem(row_index, 0, QTableWidgetItem(record.id))
            self.table.setItem(row_index, 1, QTableWidgetItem(data.get("name", "")))
            self.table.setItem(
                row_index, 2, QTableWidgetItem(str(data.get("bicep_circ", "")))
            )
            self.table.setItem(
                row_index, 3, QTableWidgetItem(str(data.get("forearm_circ", "")))
            )
            self.table.setItem(
                row_index, 4, QTableWidgetItem(str(data.get("width_size", "")))
            )
            self.table.setItem(
                row_index, 5, QTableWidgetItem(str(data.get("humeral_length", "")))
            )
            self.table.setItem(
                row_index, 6, QTableWidgetItem(str(data.get("radial_length", "")))
            )
            self.table.setItem(
                row_index, 7, QTableWidgetItem(self._format_record_timestamp(data))
            )
            note_value = data.get("sizing_note")
            note_text = str(note_value).strip() if note_value is not None else ""
            if not note_text:
                note_text = "None"
            self.table.setItem(
                row_index, 8, QTableWidgetItem(note_text)
            )

    def _format_record_timestamp(self, data: dict) -> str:
        timestamp_value = data.get("updated_at") or data.get("created_at")
        if timestamp_value is None:
            return "N/A"

        if hasattr(timestamp_value, "to_pydatetime"):
            try:
                timestamp_value = timestamp_value.to_pydatetime()
            except Exception:
                pass

        if isinstance(timestamp_value, datetime):
            return timestamp_value.strftime("%Y-%m-%d %H:%M")

        timestamp_text = str(timestamp_value).strip()
        if not timestamp_text:
            return "N/A"

        try:
            parsed = datetime.fromisoformat(timestamp_text.replace("Z", "+00:00"))
            return parsed.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return timestamp_text

    def _selected_table_id(self, table: QTableWidget) -> str | None:
        row_index = table.currentRow()
        if row_index < 0:
            return None

        item = table.item(row_index, 0)
        if item is None:
            return None
        return item.text()

    def _require_admin(self, message: str) -> bool:
        if self.is_admin:
            return True

        QMessageBox.warning(self, "Access Denied", message)
        return False

    def edit_selected_record(self):
        if not self._require_admin("Only admins can edit patient records."):
            return

        record_id = self._selected_table_id(self.table)
        if not record_id:
            QMessageBox.information(self, "Select Record", "Select a record to edit.")
            return

        self._load_record_into_form(record_id)

    def delete_selected_record(self):
        if not self._require_admin("Only admins can delete patient records."):
            return

        record_id = self._selected_table_id(self.table)
        if not record_id:
            QMessageBox.information(self, "Select Record", "Select a record to delete.")
            return

        confirm = QMessageBox.question(
            self,
            "Delete Record",
            "Delete the selected patient record?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            self.store.delete_record(record_id)
        except Exception as exc:
            QMessageBox.critical(self, "Delete Failed", str(exc))
            return

        if self.current_record_id == record_id:
            self.reset_form()
        self.load_records()

    # ---------------- ADMIN PAGE ---------------- #
    def build_admin_panel(self):
        page = QWidget()
        layout = QVBoxLayout()

        layout.addWidget(QLabel("Provision Firebase Authentication users and RBAC profiles."))

        layout.addWidget(QLabel("Email:"))
        self.admin_email_input = QLineEdit()
        layout.addWidget(self.admin_email_input)

        layout.addWidget(QLabel("Temporary Password:"))
        self.admin_password_input = QLineEdit()
        self.admin_password_input.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.admin_password_input)

        layout.addWidget(QLabel("Role:"))
        self.admin_role_input = QComboBox()
        self.admin_role_input.addItems(["user", "admin"])
        layout.addWidget(self.admin_role_input)

        layout.addWidget(QLabel("Clinic ID:"))
        self.admin_clinic_input = QLineEdit()
        self.admin_clinic_input.setPlaceholderText("e.g. ti-clinic")
        layout.addWidget(self.admin_clinic_input)

        self.admin_active_checkbox = QCheckBox("Active")
        self.admin_active_checkbox.setChecked(True)
        layout.addWidget(self.admin_active_checkbox)

        create_user_btn = QPushButton("Create User")
        create_user_btn.clicked.connect(self.create_admin_user)
        layout.addWidget(create_user_btn)

        layout.addWidget(QLabel("Existing User Profiles:"))
        self.user_table = QTableWidget()
        self.user_table.setColumnCount(5)
        self.user_table.setHorizontalHeaderLabels(
            ["UID", "Email", "Role", "Active", "Clinic ID"]
        )
        self.user_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.user_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.user_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.user_table)

        refresh_users_btn = QPushButton("Refresh Users")
        refresh_users_btn.clicked.connect(self.refresh_user_profiles)
        layout.addWidget(refresh_users_btn)

        page.setLayout(layout)
        return page

    def show_admin_panel(self):
        if not self._require_admin("Only admins can open the Admin Panel."):
            return

        self.stack.setCurrentWidget(self.admin_page)
        self.refresh_user_profiles()

    def create_admin_user(self):
        if not self._require_admin("Only admins can create users."):
            return

        email = self.admin_email_input.text().strip().lower()
        password = self.admin_password_input.text().strip()
        role = self.admin_role_input.currentText()
        clinic_id = self.admin_clinic_input.text().strip()
        active = self.admin_active_checkbox.isChecked()

        if "@" not in email:
            QMessageBox.warning(self, "Invalid Email", "Enter a valid email address.")
            return

        if len(password) < 8:
            QMessageBox.warning(
                self,
                "Invalid Password",
                "Temporary password must be at least 8 characters long.",
            )
            return

        if not clinic_id:
            QMessageBox.warning(self, "Missing Clinic", "Enter a clinic ID.")
            return

        try:
            uid = self.store.create_user_account(email, password, role, clinic_id, active)
        except Exception as exc:
            QMessageBox.critical(self, "Create User Failed", str(exc))
            return

        QMessageBox.information(
            self,
            "User Created",
            f"Created Firebase user {email} with UID {uid}.",
        )
        self.admin_email_input.clear()
        self.admin_password_input.clear()
        self.admin_role_input.setCurrentText("user")
        self.admin_clinic_input.clear()
        self.admin_active_checkbox.setChecked(True)
        self.reset_form()
        self.refresh_user_profiles()

    def refresh_user_profiles(self):
        if not self._require_admin("Only admins can manage user profiles."):
            return

        try:
            profiles = self.store.list_user_profiles()
        except Exception as exc:
            QMessageBox.critical(self, "Load Users Failed", str(exc))
            return

        self.user_lookup = {profile["uid"]: profile for profile in profiles}
        self.user_table.setRowCount(0)
        for row_index, profile in enumerate(profiles):
            self.user_table.insertRow(row_index)
            self.user_table.setItem(row_index, 0, QTableWidgetItem(profile["uid"]))
            self.user_table.setItem(row_index, 1, QTableWidgetItem(profile["email"]))
            self.user_table.setItem(row_index, 2, QTableWidgetItem(profile["role"]))
            self.user_table.setItem(
                row_index,
                3,
                QTableWidgetItem("Yes" if profile["active"] else "No"),
            )
            self.user_table.setItem(
                row_index, 4, QTableWidgetItem(profile.get("clinic_id", ""))
            )

    # ---------------- GUIDE PAGE ---------------- #
    def build_measurement_guide(self):
        scroll = QScrollArea()
        layout = QVBoxLayout()

        guide = [
            (
                "Acromion-radiale (AR) Length",
                "Measure length from acromion to radial head.",
                "images/ARLength.png",
            ),
            (
                "Bicep Circumference",
                "Measure max circumference while flexed.",
                "images/BCFlexed.png",
            ),
            (
                "Radiale-Stylion (RS) Length",
                "Measure length from radial head to styloid process.",
                "images/RSLength.png",
            ),
            (
                "Forearm Circumference",
                "Measure 1/3 distal forearm.",
                "images/FCFlexed.png",
            ),
        ]

        for title, desc, rel_path in guide:
            layout.addWidget(QLabel(f"<b>{title}</b>"))
            layout.addWidget(QLabel(desc))

            abs_path = resource_path(rel_path)
            if os.path.exists(abs_path):
                pixmap = QPixmap(abs_path)
                if not pixmap.isNull():
                    label = QLabel()
                    label.setPixmap(pixmap.scaledToWidth(300))
                    layout.addWidget(label)
                else:
                    layout.addWidget(QLabel(f"Could not load image: {rel_path}"))
            else:
                layout.addWidget(QLabel(f"Image not found: {rel_path}"))

        container = QWidget()
        container.setLayout(layout)
        scroll.setWidget(container)
        scroll.setWidgetResizable(True)
        return scroll


# ---------------- APPLICATION ENTRY POINT ---------------- #
if __name__ == "__main__":
    app = QApplication(sys.argv)
    splash_timer = QElapsedTimer()
    splash_timer.start()

    splash = QSplashScreen(create_splash_pixmap())
    splash.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    splash.show()
    splash.showMessage(
        "Loading application...",
        Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
        QColor("#1f3b2f"),
    )
    app.processEvents()

    splash.showMessage(
        "Checking local resources and online mode...",
        Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
        QColor("#1f3b2f"),
    )
    app.processEvents()

    login = LoginWindow()

    def show_login():
        login.show()
        splash.finish(login)

    remaining_ms = max(0, 4000 - splash_timer.elapsed())
    QTimer.singleShot(remaining_ms, show_login)
    sys.exit(app.exec())
