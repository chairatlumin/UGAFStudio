from PySide6.QtWidgets import QTextEdit


class LoggerWidget(QTextEdit):
    """Widget used to display log messages."""

    def __init__(self) -> None:
        super().__init__()

        self.setReadOnly(True)
        self.append("UGAF Studio Started")

    def info(self, text: str) -> None:
        self.append(f"[INFO] {text}")

    def warning(self, text: str) -> None:
        self.append(f"[WARNING] {text}")

    def error(self, text: str) -> None:
        self.append(f"[ERROR] {text}")
