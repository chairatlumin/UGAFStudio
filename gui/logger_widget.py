from PySide6.QtWidgets import QTextEdit


class LoggerWidget(QTextEdit):

    def __init__(self):

        super().__init__()

        self.setReadOnly(True)

        self.append("UGAF Studio Started")

    def info(self, text: str):

        self.append(f"[INFO] {text}")

    def warning(self, text: str):

        self.append(f"[WARNING] {text}")

    def error(self, text: str):

        self.append(f"[ERROR] {text}")