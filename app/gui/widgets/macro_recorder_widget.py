"""PySide6 Macro Recorder Widget."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.automation.macro import MacroStep

if TYPE_CHECKING:
    from app.controllers.macro_controller import MacroController


class MacroRecorderWidget(QWidget):
    """Widget for recording, editing, saving, and replaying macros."""

    recording_started = Signal()
    recording_stopped = Signal()
    playback_started = Signal()
    playback_stopped = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._controller: MacroController | None = None
        self._steps: list[MacroStep] = []
        self._recording = False

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout()
        self.setLayout(layout)

        # Header row
        header = QHBoxLayout()
        self._name_label = QLabel("Macro: <untitled>")
        header.addWidget(self._name_label)
        header.addStretch()
        self._clear_btn = QPushButton("Clear")
        self._clear_btn.clicked.connect(self._on_clear)
        header.addWidget(self._clear_btn)
        layout.addLayout(header)

        # Button row
        btn_row = QHBoxLayout()
        self._record_btn = QPushButton("● Record")
        self._record_btn.setCheckable(True)
        self._record_btn.clicked.connect(self._on_record_toggle)
        btn_row.addWidget(self._record_btn)

        self._play_btn = QPushButton("▶ Play")
        self._play_btn.clicked.connect(self._on_play)
        btn_row.addWidget(self._play_btn)

        self._save_btn = QPushButton("Save")
        self._save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(self._save_btn)

        self._load_btn = QPushButton("Load")
        self._load_btn.clicked.connect(self._on_load)
        btn_row.addWidget(self._load_btn)

        btn_row.addStretch()

        # Speed
        btn_row.addWidget(QLabel("Speed:"))
        self._speed_spin = QSpinBox()
        self._speed_spin.setRange(1, 100)
        self._speed_spin.setValue(10)
        self._speed_spin.setSuffix("x")
        btn_row.addWidget(self._speed_spin)

        layout.addLayout(btn_row)

        # Steps list
        self._steps_list = QListWidget()
        layout.addWidget(self._steps_list)

        # Status
        self._status_label = QLabel("Ready")
        layout.addWidget(self._status_label)

    def set_controller(self, controller: MacroController) -> None:
        self._controller = controller

    def add_step(self, step: MacroStep) -> None:
        self._steps.append(step)
        idx = len(self._steps)
        params = self._format_params(step.params)
        delay = f"{step.delay_ms:.0f}"
        text = f"{idx}. {step.action}({params}) {delay}ms"
        self._steps_list.addItem(QListWidgetItem(text))

    def _format_params(self, params: dict) -> str:
        if not params:
            return ""
        parts = [f"{k}={v}" for k, v in params.items()]
        return ", ".join(parts)

    def _on_record_toggle(self) -> None:
        if self._record_btn.isChecked():
            self._start_recording()
        else:
            self._stop_recording()

    def _start_recording(self) -> None:
        self._recording = True
        self._steps.clear()
        self._steps_list.clear()
        self._record_btn.setText("■ Stop")
        self._status_label.setText("Recording... (Press keys / click to capture)")
        self.recording_started.emit()
        if self._controller is not None:
            self._controller.record()

    def _stop_recording(self) -> None:
        self._recording = False
        self._record_btn.setText("● Record")
        self._record_btn.setChecked(False)
        self._status_label.setText(f"Stopped. {len(self._steps)} steps captured.")
        self.recording_stopped.emit()
        if self._controller is not None:
            self._controller.stop()

    def _on_play(self) -> None:
        if not self._steps:
            self._status_label.setText("No macro to play.")
            return
        self.playback_started.emit()
        self._status_label.setText("Playing...")
        if self._controller is not None:
            speed = self._speed_spin.value() / 10.0
            self._controller.play(speed=speed)
        self.playback_stopped.emit()
        self._status_label.setText("Playback complete.")

    def _on_save(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Macro", str(Path.cwd()), "Macro JSON (*.json)"
        )
        if path:
            if self._controller is not None:
                self._controller.save(Path(path))
            self._name_label.setText(f"Macro: {Path(path).stem}")
            self._status_label.setText(f"Saved to {path}")

    def _on_load(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Macro", str(Path.cwd()), "Macro JSON (*.json)"
        )
        if path:
            if self._controller is not None:
                self._controller.load(Path(path))
            self._name_label.setText(f"Macro: {Path(path).stem}")

    def _on_clear(self) -> None:
        self._steps.clear()
        self._steps_list.clear()
        self._status_label.setText("Cleared.")
        if self._controller is not None:
            self._controller.clear()

    def set_steps(self, steps: list[MacroStep]) -> None:
        self._steps = steps
        self._steps_list.clear()
        for i, step in enumerate(steps, 1):
            text = f"{i}. {step.action}({self._format_params(step.params)}) {step.delay_ms:.0f}ms"
            self._steps_list.addItem(QListWidgetItem(text))
