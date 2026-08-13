from __future__ import annotations

import os
from typing import cast

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QRect  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.capture.monitor import MonitorInfo  # noqa: E402
from app.gui.widgets.region_selector import RegionSelector  # noqa: E402


@pytest.fixture(scope="module")
def app() -> QApplication:
    return cast(QApplication, QApplication.instance() or QApplication([]))


def make_selector(geometry: QRect) -> RegionSelector:
    selector = RegionSelector()
    selector.setGeometry(geometry)
    return selector


def test_region_from_points_normalizes_coordinates(app: QApplication) -> None:
    selector = make_selector(QRect(0, 0, 1920, 1080))

    region = selector._region_from_points(QPoint(1920, 1080), QPoint(0, 0))

    assert region == MonitorInfo(0, 0, 1921, 1081)


def test_region_from_points_supports_negative_origin(app: QApplication) -> None:
    selector = make_selector(QRect(-1920, 0, 4480, 1440))

    region = selector._region_from_points(QPoint(-1920, 0), QPoint(-100, 500))

    assert region == MonitorInfo(-1920, 0, 1821, 501)


def test_selection_rect_is_identity_when_overlay_at_origin(app: QApplication) -> None:
    selector = make_selector(QRect(0, 0, 1920, 1080))

    rect = selector._selection_rect(MonitorInfo(100, 100, 501, 301))

    assert rect == QRect(100, 100, 501, 301)


def test_selection_rect_offset_for_negative_origin_overlay(app: QApplication) -> None:
    selector = make_selector(QRect(-1920, 0, 4480, 1440))

    rect = selector._selection_rect(MonitorInfo(0, 100, 1001, 501))

    assert rect == QRect(1920, 100, 1001, 501)
