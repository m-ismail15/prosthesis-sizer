from PyQt6.QtWidgets import QApplication, QLabel
import sys

app = QApplication(sys.argv)
label = QLabel("It works!")
label.show()
sys.exit(app.exec())
