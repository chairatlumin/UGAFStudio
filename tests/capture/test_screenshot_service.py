from __future__ import annotations

from pathlib import Path

import numpy as np

from app.capture.screenshot_service import ScreenshotService


def test_save_writes_png(tmp_path: Path) -> None:
    frame = np.zeros((10, 10, 4), dtype=np.uint8)
    service = ScreenshotService(output_dir=tmp_path)

    path = service.save(frame, name="test")

    assert path.exists()
    assert path.suffix == ".png"
    assert path.name.startswith("test_")


def test_save_creates_output_directory(tmp_path: Path) -> None:
    frame = np.zeros((4, 4, 4), dtype=np.uint8)
    target = tmp_path / "nested" / "shots"

    service = ScreenshotService(output_dir=target)

    path = service.save(frame)

    assert target.exists()
    assert path.exists()


def test_save_generates_unique_names(tmp_path: Path) -> None:
    frame = np.zeros((4, 4, 4), dtype=np.uint8)
    service = ScreenshotService(output_dir=tmp_path)

    first = service.save(frame)
    second = service.save(frame)

    assert first != second
