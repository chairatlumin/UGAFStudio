"""HSB input mapping check: letterbox offset + ref coords land on the same pixel."""

from __future__ import annotations

import numpy as np

import scripts.hsb_flow as hsb


def test_frame_to_screen_centre_agrees(monkeypatch) -> None:
    monkeypatch.setattr(hsb, "get_window_rect", lambda hwnd: (100, 50, 2020, 1130))
    monkeypatch.setattr(hsb, "content_rect", lambda frame: (192, 108, 1536, 864))
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    assert hsb.frame_to_screen(1, frame, (960, 540)) == (1060, 590)
    assert hsb.frame_to_screen(1, frame, (768, 432), hsb.REF_1536x864) == (1060, 590)
    assert hsb.frame_to_screen(1, frame, (0, 0), hsb.REF_1536x864) == (292, 158)
