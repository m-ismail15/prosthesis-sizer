# Desktop GUI
import os
import sys

from PyQt6.QtCore import QObject, QElapsedTimer, QThread, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QDoubleValidator, QFont, QLinearGradient, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (QAbstractItemView, QApplication, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPushButton, QScrollArea, QSplashScreen, QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
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
    invalid_credentials = pyqtSignal()
    error = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, email: str, password: str):
        super().__init__()
        self.email = email
        self.password = password

    def run(self):
        try:
            self.progress.emit("Signing in...")
            # Create the Firebase client inside the worker thread to avoid
            # cross-thread use of network-bound client objects.
            online_store = FirebaseStore()
            role = online_store.authenticate(self.email, self.password)
            if not role:
                self.invalid_credentials.emit()
                return

            self.finished.emit(role)
        except Exception as exc:
            self.error.emit(str(exc))


class OfflineSyncWorker(QObject):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, offline_store):
        super().__init__()
        self.offline_store = offline_store

    def run(self):
        try:
            online_store = FirebaseStore()
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
        self.offline_store = LocalJsonStore(default_local_store_path())
        self.login_thread = None
        self.login_worker = None

        self._try_enable_online_mode()
        self._build_ui()

    def _try_enable_online_mode(self):
        preferred_mode = os.getenv("PROSTHESIS_APP_MODE", "auto").strip().lower()
        if preferred_mode == "offline":
            self.online_error = "Offline mode forced by PROSTHESIS_APP_MODE=offline."
            return

        if is_firebase_configured():
            # Delay Firestore client creation until the user actually signs in.
            self.online_store = FirebaseStore()
        else:
            self.online_error = "Firebase key not found."

    def _build_ui(self):
        layout = QVBoxLayout()

        layout.addWidget(QLabel("Email:"))
        self.email_input = QLineEdit()
        self.email_input.returnPressed.connect(self.login_online)
        layout.addWidget(self.email_input)

        layout.addWidget(QLabel("Password:"))
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.returnPressed.connect(self.login_online)
        layout.addWidget(self.password_input)

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
                "Online mode is available. Continue Offline keeps records in a temporary local queue until they are synced online."
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
        self.login_worker.invalid_credentials.connect(
            lambda: self._handle_login_invalid()
        )
        self.login_worker.error.connect(self._handle_login_error)
        self.login_worker.finished.connect(self._handle_login_success)
        self.login_worker.finished.connect(self.login_thread.quit)
        self.login_worker.invalid_credentials.connect(self.login_thread.quit)
        self.login_worker.error.connect(self.login_thread.quit)
        self.login_thread.finished.connect(self._cleanup_login_thread)

        self.login_thread.start()

    def open_offline_mode(self):
        try:
            self.open_main_app(self.offline_store, "prosthetist")
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
        if message:
            self.status_label.setText(message)

    def _handle_login_invalid(self):
        self._set_busy_state(False, "Invalid credentials.")

    def _handle_login_error(self, error_message: str):
        self._set_busy_state(
            False,
            "Could not log in online. Use Continue Offline to queue records locally.\n\n"
            f"Reason: {error_message}",
        )

    def _handle_login_success(self, role: str):
        self._set_busy_state(False)
        self.open_main_app(self.online_store, role)
        QTimer.singleShot(0, self.main_app.start_offline_sync)

    def _cleanup_login_thread(self):
        if self.login_worker is not None:
            self.login_worker.deleteLater()
        if self.login_thread is not None:
            self.login_thread.deleteLater()
        self.login_worker = None
        self.login_thread = None

    def open_main_app(self, store, role: str):
        self.hide()
        self.main_app = ProsthesisApp(store=store, role=role)
        self.main_app.show()


# ---------------- MAIN APPLICATION ---------------- #
class ProsthesisApp(QMainWindow):
    def __init__(self, store, role: str = "prosthetist"):
        super().__init__()
        self.store = store
        self.role = role
        self.sync_thread = None
        self.sync_worker = None
        self.setWindowTitle(
            f"Prosthesis Sizing App v{APP_VERSION} - {self.store.mode_name.title()} Mode - Role: {self.role}"
        )
        self.setGeometry(100, 100, 900, 600)

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.home_page = self.build_home()
        self.records_page = self.build_records()
        self.guide_page = self.build_measurement_guide()

        self.stack.addWidget(self.home_page)
        self.stack.addWidget(self.records_page)
        self.stack.addWidget(self.guide_page)

        nav = QWidget()
        nav_layout = QHBoxLayout()
        nav.setLayout(nav_layout)

        home_btn = QPushButton("Home")
        records_btn = QPushButton("Records")
        guide_btn = QPushButton("Measurement Guide")

        home_btn.clicked.connect(lambda: self.stack.setCurrentWidget(self.home_page))

        def show_records():
            self.stack.setCurrentWidget(self.records_page)
            self.load_records()

        records_btn.clicked.connect(show_records)
        guide_btn.clicked.connect(lambda: self.stack.setCurrentWidget(self.guide_page))

        nav_layout.addWidget(home_btn)
        nav_layout.addWidget(records_btn)
        nav_layout.addWidget(guide_btn)
        self.addToolBar("Navigation").addWidget(nav)

        mode_message = f"Running in {self.store.mode_name} mode."
        if self.store.mode_name == "offline":
            mode_message += (
                " Pending records stay in a temporary local queue until they are synced online."
                f" Queue file: {default_local_store_path()}"
            )
        else:
            mode_message += f" Firebase key search includes: {user_config_dir()}"
        self.statusBar().showMessage(mode_message)

    def start_offline_sync(self):
        if self.store.mode_name != "online" or self.sync_thread is not None:
            return

        self.statusBar().showMessage("Checking for queued offline records to sync...")
        self.sync_thread = QThread(self)
        self.sync_worker = OfflineSyncWorker(LocalJsonStore(default_local_store_path()))
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

        self.name_input = QLineEdit()
        layout.addWidget(QLabel("Patient Name:"))
        layout.addWidget(self.name_input)

        self.bicep_input = QLineEdit()
        self.forearm_input = QLineEdit()
        self.humerus_input = QLineEdit()
        self.residuum_input = QLineEdit()

        validator = QDoubleValidator(0.0, 10000.0, 2, parent=self)
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

        submit_btn = QPushButton("Calculate Size & Save")
        submit_btn.clicked.connect(self.save_patient_data)
        layout.addWidget(submit_btn)

        page.setLayout(layout)
        return page

    def save_patient_data(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Missing Name", "Please enter the patient name.")
            return

        try:
            bc = float(self.bicep_input.text())
            fc = float(self.forearm_input.text())
            ar = float(self.humerus_input.text())
            rs = float(self.residuum_input.text())
        except ValueError:
            QMessageBox.warning(self, "Invalid Input", "Please enter valid measurements.")
            return

        result = compute_prosthesis_size(bc, fc, ar, rs)

        payload = {
            "name": name,
            "name_lower": name.lower(),
            "bicep_circ": bc,
            "forearm_circ": fc,
            "humerus_len": ar,
            "residuum_len": rs,
            "width_size": result["width"],
            "humeral_length": result["humeral_length"],
            "radial_length": result["radial_length"],
            "sizing_note": result["message"],
        }

        try:
            self.store.save_record(payload)
        except Exception as exc:
            QMessageBox.critical(self, "Save Failed", str(exc))
            return

        QMessageBox.information(
            self,
            "Sizing Result",
            f"Width: {result['width']}\n"
            f"Humeral Length: {result['humeral_length']}\n"
            f"Radial Length: {result['radial_length']}\n\n"
            f"{result['message']}"
        )

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

        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Name", "BC", "FC", "Width", "Hum Len", "Rad Len", "Note"]
        )
        self.table.setColumnHidden(0, True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        layout.addLayout(search_layout)
        layout.addWidget(self.table)
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
        for row_index, record in enumerate(records):
            data = record.to_dict()
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
                row_index, 7, QTableWidgetItem(data.get("sizing_note", ""))
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
