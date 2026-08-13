from __future__ import annotations

from typing import Any

import mss
import numpy as np

from app.capture.capture_service import CaptureService
from app.capture.monitor import MonitorInfo

MONITORS = [
    {"left": -1920, "top": 0, "width": 1920, "height": 1080},
    {"left": 0, "top": 0, "width": 1920, "height": 1080},
    {"left": 1920, "top": 0, "width": 2560, "height": 1440},
]


class FakeScreenshot:
    def __init__(self, width: int, height: int) -> None:
        self._frame = np.zeros((height, width, 4), dtype=np.uint8)

    def __array__(self, dtype: Any = None) -> np.ndarray:
        return np.asarray(self._frame, dtype=dtype)


class FakeMSS:
    monitors = MONITORS

    def grab(self, region: dict[str, int]) -> FakeScreenshot:
        return FakeScreenshot(region["width"], region["height"])


def make_service(monkeypatch: Any) -> CaptureService:
    monkeypatch.setattr(mss, "MSS", lambda: FakeMSS())
    return CaptureService()


def test_defaults_to_virtual_desktop(monkeypatch: Any) -> None:
    service = make_service(monkeypatch)

    assert service.current_monitor() == MonitorInfo(-1920, 0, 1920, 1080)
    assert len(service.all_monitors()) == 3


def test_capture_uses_current_monitor_bounds(monkeypatch: Any) -> None:
    service = make_service(monkeypatch)

    frame = service.capture()

    assert frame.shape[:2] == (1080, 1920)


def test_set_monitor(monkeypatch: Any) -> None:
    service = make_service(monkeypatch)

    service.set_monitor(2)

    assert service.current_monitor() == MonitorInfo(1920, 0, 2560, 1440)

    frame = service.capture()

    assert frame.shape[:2] == (1440, 2560)


def test_set_monitor_ignores_invalid_index(monkeypatch: Any) -> None:
    service = make_service(monkeypatch)

    service.set_monitor(99)

    assert service.current_monitor() == MonitorInfo(-1920, 0, 1920, 1080)


def test_use_virtual_desktop_resets_region(monkeypatch: Any) -> None:
    service = make_service(monkeypatch)

    service.set_monitor(2)
    service.use_virtual_desktop()

    assert service.current_monitor() == MonitorInfo(-1920, 0, 1920, 1080)


def test_monitor_at_finds_containing_monitor(monkeypatch: Any) -> None:
    service = make_service(monkeypatch)

    assert service.monitor_at(1000, 500) == MonitorInfo(0, 0, 1920, 1080)
    assert service.monitor_at(3000, 500) == MonitorInfo(1920, 0, 2560, 1440)
