from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from app.core.application import UGAFApplication


def main() -> None:
    """Application entry point."""

    app = QApplication(sys.argv)

    application = UGAFApplication(app)

    application.start()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
