# Desktop GUI
import sys
import os
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QStackedWidget, QTableWidget,
    QTableWidgetItem, QMessageBox, QScrollArea, QAbstractItemView, QHeaderView
)
from PyQt6.QtGui import QPixmap, QDoubleValidator
from google.protobuf.timestamp_pb2 import Timestamp
from firebase_config import db
from firebase_admin import firestore as fb_firestore
from sizing import compute_prosthesis_size

# ---------------- LOGIN PAGE ---------------- #
class LoginWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Login")
        self.setGeometry(300, 200, 400, 200)

        layout = QVBoxLayout()

        layout.addWidget(QLabel("Email:"))
        self.email_input = QLineEdit()
        layout.addWidget(self.email_input)

        layout.addWidget(QLabel("Password:"))
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.password_input)

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        login_btn = QPushButton("Login")
        login_btn.clicked.connect(self.login)
        layout.addWidget(login_btn)

        self.setLayout(layout)

    def login(self):
        email = self.email_input.text().strip().lower()
        password = self.password_input.text().strip()

        if not email or not password:
            self.status_label.setText("⚠ Please enter email and password")
            return

        try:
            users_ref = db.collection("Users")
            query = users_ref.where(filter=("email", "==", email))\
                             .where(filter=("password", "==", password)).stream()
            user_doc = next(query, None)

            if user_doc:
                role = user_doc.to_dict().get("role", "prosthetist")
                self.hide()
                self.main_app = ProsthesisApp(role=role)
                self.main_app.show()
            else:
                self.status_label.setText("❌ Invalid credentials")

        except Exception as e:
            self.status_label.setText(f"Error: {e}")


# ---------------- MAIN APP ---------------- #

class ProsthesisApp(QMainWindow):
    def __init__(self, role="prosthetist"):
        super().__init__()
        self.role = role
        self.setWindowTitle(f"Prosthesis Sizing App - Role: {self.role}")
        self.setGeometry(100, 100, 900, 600)

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.home_page = self.build_home()
        self.records_page = self.build_records()
        self.guide_page = self.build_measurement_guide()

        self.stack.addWidget(self.home_page)
        self.stack.addWidget(self.records_page)
        self.stack.addWidget(self.guide_page)

        # Navigation
        nav = QWidget()
        nav_layout = QHBoxLayout()
        nav.setLayout(nav_layout)

        home_btn = QPushButton("🏠 Home")
        records_btn = QPushButton("📋 Records")
        guide_btn = QPushButton("📖 Measurement Guide")

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
        for field in [self.bicep_input, self.forearm_input, self.humerus_input, self.residuum_input]:
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
            "created_at": fb_firestore.SERVER_TIMESTAMP,
            "updated_at": fb_firestore.SERVER_TIMESTAMP
        }

        db.collection("prosthesis_records").add(payload)

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
        self.table.setHorizontalHeaderLabels([
            "ID", "Name", "BC", "FC", "Width", "Hum Len", "Rad Len", "Note"
        ])
        self.table.setColumnHidden(0, True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        layout.addLayout(search_layout)
        layout.addWidget(self.table)
        page.setLayout(layout)
        return page

    def load_records(self):
        docs = list(db.collection("prosthesis_records").stream())
        self.display_records(docs)

    def search_records(self):
        text = self.search_input.text().strip().lower()
        if not text:
            self.load_records()
            return

        docs = list(db.collection("prosthesis_records").stream())
        filtered = [d for d in docs if text in d.to_dict().get("name_lower", "")]
        self.display_records(filtered)

    def display_records(self, records):
        self.table.setRowCount(0)
        for i, rec in enumerate(records):
            data = rec.to_dict()
            self.table.insertRow(i)
            self.table.setItem(i, 0, QTableWidgetItem(rec.id))
            self.table.setItem(i, 1, QTableWidgetItem(data.get("name", "")))
            self.table.setItem(i, 2, QTableWidgetItem(str(data.get("bicep_circ", ""))))
            self.table.setItem(i, 3, QTableWidgetItem(str(data.get("forearm_circ", ""))))
            self.table.setItem(i, 4, QTableWidgetItem(str(data.get("width_size", ""))))
            self.table.setItem(i, 5, QTableWidgetItem(str(data.get("humeral_length", ""))))
            self.table.setItem(i, 6, QTableWidgetItem(str(data.get("radial_length", ""))))
            self.table.setItem(i, 7, QTableWidgetItem(data.get("sizing_note", "")))

    # ---------------- GUIDE PAGE ---------------- #
    def build_measurement_guide(self):
        scroll = QScrollArea()
        layout = QVBoxLayout()

        guide = [
            ("Bicep Circumference", "Measure max circumference while flexed.", "images/bicep.png"),
            ("Forearm Circumference", "Measure 1/3 distal forearm.", "images/forearm.png"),
        ]

        for title, desc, path in guide:
            layout.addWidget(QLabel(f"<b>{title}</b>"))
            layout.addWidget(QLabel(desc))
            if os.path.exists(path):
                pixmap = QPixmap(path)
                label = QLabel()
                label.setPixmap(pixmap.scaledToWidth(300))
                layout.addWidget(label)

        container = QWidget()
        container.setLayout(layout)
        scroll.setWidget(container)
        scroll.setWidgetResizable(True)
        return scroll


# ---------------- RUN APP ---------------- #
if __name__ == "__main__":
    app = QApplication(sys.argv)
    login = LoginWindow()
    login.show()
    sys.exit(app.exec())
