from __future__ import annotations

from app.capture.monitor import MonitorInfo


def test_origin_and_size() -> None:
    monitor = MonitorInfo(left=-1920, top=0, width=1920, height=1080)

    assert monitor.origin == (-1920, 0)
    assert monitor.size == (1920, 1080)
    assert monitor.right == 0
    assert monitor.bottom == 1080


def test_contains() -> None:
    monitor = MonitorInfo(left=0, top=0, width=1920, height=1080)

    assert monitor.contains(0, 0)
    assert monitor.contains(1919, 1079)
    assert not monitor.contains(1920, 1080)
    assert not monitor.contains(-1, 0)


def test_to_local_and_to_global() -> None:
    monitor = MonitorInfo(left=0, top=0, width=1920, height=1080)

    assert monitor.to_local(100, 200) == (100, 200)
    assert monitor.to_global(100, 200) == (100, 200)


def test_to_local_with_negative_origin() -> None:
    monitor = MonitorInfo(left=-1920, top=0, width=1920, height=1080)

    assert monitor.to_local(-1000, 500) == (920, 500)
    assert monitor.to_global(920, 500) == (-1000, 500)
