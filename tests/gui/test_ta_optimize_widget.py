from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.gui.widgets.ta_optimize_widget import (  # noqa: E402
    PerformanceGraph,
    TAOptimizeWidget,
)


def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_ta_optimize_renders_frame_time_analysis() -> None:
    app()
    widget = TAOptimizeWidget()
    widget._latest_events = [
        {
            "payload": {
                "sequence": index,
                "build_id": "fake-fixture",
                "event_type": "performance_sample",
                "emitted_at_utc": f"2026-11-04T12:00:{index:02d}+00:00",
                "state": {
                    "scene_id": "fixture-level",
                    "performance": {
                        "scenario_id": "steady-state",
                        "phase": "steady",
                        "metrics": {"frame_time_ms": value, "gpu_ms": 7.0},
                    },
                },
            }
        }
        for index, value in enumerate((12.0, 18.0, 40.0), start=1)
    ]
    try:
        widget._render_report()
        assert widget._latest_report is not None
        assert widget._latest_report["sample_count"] == 3
        assert widget._graph.metric_key == "frame_time_ms"
        assert widget._graph.samples
        assert widget._diagnosis.count() > 0
        assert "UNASSERTED" in widget._status.text()
        widget.resize(900, 700)
        widget.show()
        app().processEvents()
        assert not widget.grab().isNull()
    finally:
        widget.close()


def test_performance_graph_marks_stress_phases() -> None:
    app()
    graph = PerformanceGraph()
    graph.resize(900, 300)
    phases = ("warmup", "warmup", "steady", "steady", "spike", "spike", "recovery", "recovery")
    graph.set_data(
        [
            {"phase": phase, "metrics": {"frame_time_ms": value}}
            for phase, value in zip(phases, (20, 18, 16, 15, 45, 38, 24, 19), strict=True)
        ],
        "frame_time_ms",
        1000 / 60,
    )
    graph.show()
    app().processEvents()
    image = graph.grab().toImage()
    assert not image.isNull()
    phase_fill = QColor("#563b24").rgb()
    assert sum(
        image.pixel(x, y) == phase_fill
        for x in range(image.width())
        for y in range(image.height())
    ) > 100
    graph.close()
