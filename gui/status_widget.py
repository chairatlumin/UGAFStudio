from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel


class StatusWidget(QLabel):

    def __init__(self):

        super().__init__()

        self.setAlignment(Qt.AlignLeft)

        self.setText(
            "FPS : 0\n"
            "Mouse : 0,0\n"
            "Pixel : -,-,-"
        )

    def update_mouse(self, x, y):

        lines = self.text().split("\n")

        lines[1] = f"Mouse : {x},{y}"

        self.setText("\n".join(lines))