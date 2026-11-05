from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core.paths import writable_path
from app.database.database import QADatabase
from qa_framework.performance_lab import (
    STRESS_PROFILES,
    analyze_performance_events,
    compare_performance_reports,
    export_performance_report,
)


class PerformanceGraph(QWidget):
    """Unreal-style frame-time track with a target-budget line."""

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumHeight(280)
        self.samples: list[dict[str, Any]] = []
        self.metric_key = "frame_time_ms"
        self.budget = 16.667
        self._phase_colors = {
            "warmup": QColor("#233b49"),
            "steady": QColor("#173f3b"),
            "spike": QColor("#563b24"),
            "recovery": QColor("#293750"),
            "soak": QColor("#43334f"),
            "unknown": QColor("#173f3b"),
        }

    def set_data(self, samples: list[dict[str, Any]], metric: str, budget_ms: float) -> None:
        self.samples = samples
        self.metric_key = metric
        self.budget = budget_ms
        self.update()

    def paintEvent(self, _event: object) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#101820"))
        plot = self.rect().adjusted(62, 28, -18, -42)
        painter.setPen(QPen(QColor("#30434d"), 1))
        for index in range(5):
            y = plot.top() + index * plot.height() / 4
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
        plotted_samples = [
            sample for sample in self.samples
            if self.metric_key in sample.get("metrics", {})
        ]
        values = [float(sample["metrics"][self.metric_key]) for sample in plotted_samples]
        painter.setPen(QColor("#a9bbc4"))
        painter.drawText(8, 18, f"{self.metric_key.replace('_', ' ')}  ·  {len(values)} samples")
        painter.drawText(8, self.height() - 10, "sample sequence")
        if not values:
            painter.setPen(QColor("#91a3ad"))
            painter.drawText(plot, Qt.AlignmentFlag.AlignCenter, "No Unreal performance samples yet")
            painter.end()
            return

        maximum = max(max(values) * 1.12, self.budget * 1.2 if self.metric_key == "frame_time_ms" else 1.0)
        # Subtle vertical bands show the actual stress phase carried by each
        # Unreal sample; phase changes are not inferred from timing or value.
        phase_runs: list[tuple[int, int, str]] = []
        for index, sample in enumerate(plotted_samples):
            phase = str(sample.get("phase", "unknown"))
            if phase_runs and phase_runs[-1][2] == phase:
                phase_runs[-1] = (phase_runs[-1][0], index, phase)
            else:
                phase_runs.append((index, index, phase))
        for start, end, phase in phase_runs:
            x_start = plot.left() + (start / max(1, len(values) - 1)) * plot.width()
            x_end = plot.left() + (end / max(1, len(values) - 1)) * plot.width()
            if end == start:
                band_width = plot.width() / max(1, len(values) - 1)
                x_start = max(plot.left(), x_start - band_width / 2)
                x_end = min(plot.right(), x_end + band_width / 2)
            band = self._phase_colors.get(phase, self._phase_colors["unknown"])
            painter.fillRect(
                int(x_start), plot.top(), max(2, int(x_end - x_start)), plot.height(), band
            )
            if end > start:
                painter.setPen(QColor("#a9bbc4"))
                painter.drawText(int(x_start) + 4, plot.top() + 14, phase)
        if self.metric_key == "frame_time_ms":
            budget_y = plot.bottom() - (self.budget / maximum) * plot.height()
            painter.setPen(QPen(QColor("#f2b84b"), 2, Qt.PenStyle.DashLine))
            painter.drawLine(QPointF(plot.left(), budget_y), QPointF(plot.right(), budget_y))
            painter.drawText(plot.right() - 112, budget_y - 5, f"{self.budget:.1f} ms budget")
        count = len(values)
        points: list[QPointF] = []
        for index, value in enumerate(values):
            x = plot.left() + (index / max(1, count - 1)) * plot.width()
            y = plot.bottom() - min(value / maximum, 1.0) * plot.height()
            points.append(QPointF(x, y))
        for index in range(1, len(points)):
            phase = str(plotted_samples[index].get("phase", "unknown"))
            color = QColor("#f29b54") if phase == "spike" else QColor("#56d6bd")
            painter.setPen(QPen(color, 2))
            painter.drawLine(points[index - 1], points[index])
        painter.setPen(QPen(QColor("#56d6bd"), 1))
        painter.setBrush(QColor("#56d6bd"))
        for point in points:
            painter.drawEllipse(point, 2.5, 2.5)
        painter.setPen(QColor("#a9bbc4"))
        for index in range(5):
            value = maximum * (1 - index / 4)
            painter.drawText(8, int(plot.top() + index * plot.height() / 4 + 4), f"{value:.0f}")
        painter.end()


class TAOptimizeWidget(QWidget):
    """Inspect Unreal stress telemetry and save an evidence-linked analysis."""

    def __init__(self) -> None:
        super().__init__()
        self._profile = QLineEdit("highschoolblood-demo")
        self._session = QLineEdit()
        self._session.setPlaceholderText("candidate stress session ID")
        self._baseline = QLineEdit()
        self._baseline.setPlaceholderText("optional baseline session for before/after comparison")
        self._stress = QComboBox()
        for item in STRESS_PROFILES:
            self._stress.addItem(item["name"], item)
        self._metric = QComboBox()
        self._metric.addItem("Frame time (ms)", "frame_time_ms")
        self._metric.addItem("GPU time (ms)", "gpu_ms")
        self._metric.addItem("Game thread (ms)", "game_thread_ms")
        self._metric.addItem("Render thread (ms)", "render_thread_ms")
        self._metric.addItem("Memory (MB)", "memory_mb")
        self._target_fps = QComboBox()
        for fps in (30, 60, 90, 120, 144):
            self._target_fps.addItem(str(fps), fps)
        self._target_fps.setCurrentIndex(self._target_fps.findData(60))
        self._status = QLabel("Import or receive performance_sample events from an instrumented Unreal build.")
        self._status.setWordWrap(True)
        self._metrics = QLabel("No session loaded")
        self._metrics.setWordWrap(True)
        self._graph = PerformanceGraph()
        self._diagnosis = QListWidget()
        self._latest_report: dict[str, Any] | None = None
        self._baseline_report: dict[str, Any] | None = None
        self._latest_events: list[dict[str, Any]] = []
        self._event_source = "unreal_telemetry_events"
        self._build_ui()
        self._metric.currentIndexChanged.connect(self._refresh_graph)
        self._target_fps.currentIndexChanged.connect(self._reload)
        self._stress.currentIndexChanged.connect(self._show_stress_description)
        self._show_stress_description()

    def _build_ui(self) -> None:
        form = QGridLayout()
        form.addWidget(QLabel("Game profile"), 0, 0)
        form.addWidget(self._profile, 0, 1)
        form.addWidget(QLabel("Stress scenario"), 0, 2)
        form.addWidget(self._stress, 0, 3)
        form.addWidget(QLabel("Session"), 1, 0)
        form.addWidget(self._session, 1, 1)
        form.addWidget(QLabel("Target FPS"), 1, 2)
        form.addWidget(self._target_fps, 1, 3)
        form.addWidget(QLabel("Baseline session"), 2, 0)
        form.addWidget(self._baseline, 2, 1, 1, 3)
        self._stress_note = QLabel()
        self._stress_note.setWordWrap(True)

        actions = QHBoxLayout()
        for label, callback in (
            ("Load Unreal telemetry", self._reload),
            ("Import telemetry JSON", self._import_json),
            ("Save analysis report", self._save_report),
        ):
            button = QPushButton(label)
            button.clicked.connect(callback)
            actions.addWidget(button)
        self._metric.setMinimumWidth(180)
        actions.addWidget(QLabel("Graph"))
        actions.addWidget(self._metric)
        actions.addStretch()

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._stress_note)
        layout.addWidget(self._status)
        layout.addLayout(actions)
        layout.addWidget(self._graph, 2)
        layout.addWidget(self._metrics)
        layout.addWidget(QLabel("Optimization hypotheses"))
        layout.addWidget(self._diagnosis, 1)
        self.setStyleSheet(
            "QWidget{background:#17232b;color:#dce7eb} QLineEdit,QComboBox,QListWidget{"
            "background:#101820;border:1px solid #344a55;padding:6px;color:#dce7eb}"
            "QPushButton{background:#245a59;border:1px solid #3a8880;padding:7px 10px}"
            "QPushButton:hover{background:#2e706c}"
        )

    def _show_stress_description(self, *_args: object) -> None:
        profile = self._stress.currentData()
        if not profile:
            return
        signals = ", ".join(profile["signals"])
        self._stress_note.setText(
            f"{profile['purpose']} Collect: {signals}. Choose this same scenario in the Unreal-side harness and use the matching scenario ID."
        )

    def _reload(self, *_args: object) -> None:
        profile = self._profile.text().strip()
        session_id = self._session.text().strip()
        if not profile or not session_id:
            self._show_error("Enter a game profile key and candidate session ID to keep runs separate.")
            return
        try:
            db = QADatabase.for_profile(profile)
            self._latest_events = db.list_unreal_telemetry_events(
                profile, session_id, 1000
            )
            self._event_source = "unreal_telemetry_events"
            self._baseline_report = None
            baseline_id = self._baseline.text().strip()
            if baseline_id:
                baseline_events = db.list_unreal_telemetry_events(profile, baseline_id, 1000)
                self._baseline_report = analyze_performance_events(
                    baseline_events,
                    profile=profile,
                    session_id=baseline_id,
                    target_fps=float(self._target_fps.currentData()),
                    scenario_id=str(self._stress.currentData()["id"]),
                )
            self._render_report()
        except (OSError, ValueError, RuntimeError) as exc:
            self._show_error(str(exc))

    def _import_json(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "Import Unreal telemetry", "", "JSON (*.json)")
        if not filename:
            return
        try:
            value = json.loads(Path(filename).read_text(encoding="utf-8"))
            events = value.get("events", value) if isinstance(value, dict) else value
            if not isinstance(events, list) or not all(isinstance(row, dict) for row in events):
                raise ValueError("JSON must contain an event list or an object with an events list.")
            self._latest_events = events
            self._event_source = "imported_telemetry_json"
            self._baseline_report = None
            self._session.setText(str(value.get("session_id", "imported")) if isinstance(value, dict) else "imported")
            self._render_report()
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            self._show_error(str(exc))

    def _render_report(self) -> None:
        profile = self._profile.text().strip()
        session = self._session.text().strip()
        self._latest_report = analyze_performance_events(
            self._latest_events,
            profile=profile,
            session_id=session,
            target_fps=float(self._target_fps.currentData()),
            scenario_id=str(self._stress.currentData()["id"]),
        )
        self._latest_report["source"] = self._event_source if self._latest_events else "none"
        if self._baseline_report is not None:
            self._latest_report["comparison"] = compare_performance_reports(
                self._baseline_report, self._latest_report
            )
        self._status.setText(
            f"{self._latest_report['sample_count']} samples · "
            f"{self._latest_report['scenario_id']} · source: {self._latest_report['source']} · "
            "read-only analysis; QA status remains UNASSERTED"
        )
        frame = self._latest_report["metrics"].get("frame_time_ms", {})
        p95_text = f"{self._latest_report['p95_frame_time_ms']:.2f}" if frame else "—"
        mean_text = f"{self._latest_report['mean_frame_time_ms']:.2f}" if frame else "—"
        self._metrics.setText(
            f"P95 frame time: {p95_text} ms   "
            f"Mean: {mean_text} ms   "
            f"Hitches (>2× budget): {self._latest_report['hitch_count_over_2x_budget']}   "
            f"Budget: {self._latest_report['frame_budget_ms']:.2f} ms"
        )
        self._diagnosis.clear()
        for finding in self._latest_report["diagnosis"]:
            self._diagnosis.addItem(f"{finding['kind']}: {finding['finding']}\nNext: {finding['next_step']}")
        comparison = self._latest_report.get("comparison")
        if comparison is not None:
            self._diagnosis.addItem(
                f"Comparison: {comparison['observation']} · "
                f"p95 Δ {comparison['p95_frame_time_delta_ms']} ms · QA UNASSERTED"
            )
        self._refresh_graph()

    def _refresh_graph(self, *_args: object) -> None:
        if not self._latest_report:
            return
        self._graph.set_data(
            self._latest_report["samples"],
            str(self._metric.currentData()),
            float(self._latest_report["frame_budget_ms"]),
        )

    def _save_report(self) -> None:
        if self._latest_report is None:
            self._render_report()
        if self._latest_report is None:
            return
        folder = writable_path("reports/performance")
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save performance analysis", str(folder / "unreal-performance.json"), "JSON (*.json)"
        )
        if not filename:
            return
        try:
            path = export_performance_report(self._latest_report, Path(filename))
            self._status.setText(f"Report saved: {path} · QA status UNASSERTED")
        except (OSError, ValueError) as exc:
            self._show_error(str(exc))

    def _show_error(self, message: str) -> None:
        QMessageBox.warning(self, "TA Optimize", message)
