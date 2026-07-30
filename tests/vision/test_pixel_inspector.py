from __future__ import annotations

import numpy as np

from app.vision.pixel_inspector import PixelInspector


def test_inspect_reads_rgb_and_hex_from_bgra_frame() -> None:
    frame = np.zeros((2, 2, 4), dtype=np.uint8)
    frame[1, 0] = [17, 34, 51, 255]

    pixel = PixelInspector().inspect(frame, x=0, y=1)

    assert pixel is not None
    assert pixel.rgb == (51, 34, 17)
    assert pixel.hex == "#332211"


def test_inspect_returns_none_outside_frame() -> None:
    frame = np.zeros((2, 2, 4), dtype=np.uint8)

    pixel = PixelInspector().inspect(frame, x=2, y=0)

    assert pixel is None
