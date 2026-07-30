from __future__ import annotations

from PySide6.QtWidgets import QApplication

from app.core.config import Config
from app.core.logger import get_logger
from app.gui.main_window import MainWindow


class UGAFApplication:
    """Application bootstrap."""

    def __init__(self, app: QApplication) -> None:
        self.app = app

        self.logger = get_logger()

        self.config = Config()
        self.config.load()

        self.window = MainWindow()

    def start(self) -> None:
        """Start application."""

        self.logger.info("UGAF Studio started")

        self.window.show()
