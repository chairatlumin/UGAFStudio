from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QMainWindow, QSplitter,
                               QStatusBar, QVBoxLayout, QWidget)

from gui.logger_widget import LoggerWidget
from gui.status_widget import StatusWidget
from gui.style import STYLE


class MainWindow(QMainWindow):

    def __init__(self):

        super().__init__()

        self.setWindowTitle("UGAF Studio v0.0.1")

        self.resize(1400, 900)

        self.setStyleSheet(STYLE)

        self.init_ui()

    def init_ui(self):

        central = QWidget()

        self.setCentralWidget(central)

        layout = QVBoxLayout()

        central.setLayout(layout)

        title = QLabel("Universal Game QA Framework")

        title.setAlignment(Qt.AlignCenter)

        layout.addWidget(title)

        preview = QLabel("Live Preview")

        preview.setMinimumHeight(600)

        preview.setAlignment(Qt.AlignCenter)

        preview.setStyleSheet("""
            background:#3c3f41;
            border:2px solid #555;
        """)

        layout.addWidget(preview)

        status = QStatusBar()

        status.showMessage("Ready")

        self.setStatusBar(status)