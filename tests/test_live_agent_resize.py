from __future__ import annotations

from qa_framework.gameplay_agent.actions import Action
from unittest.mock import patch

import numpy as np

from scripts.live_gameplay_agent import (
    LiveGameplayAgent,
    _scale_decision_action,
    _scale_ocr_words,
    ocr_fmv_frame,
)


def test_scales_click_from_vlm_image_to_capture_pixels() -> None:
    action = _scale_decision_action(
        Action("click", {"x": 200, "y": 100, "button": "left"}),
        (540, 960, 3),
        (1080, 1920, 3),
    )
    assert action.params == {"x": 400, "y": 200, "button": "left"}


def test_does_not_change_noop_or_coordinate_free_click() -> None:
    noop = Action("noop", {})
    click = Action("click", {"button": "left"})
    assert _scale_decision_action(noop, (540, 960, 3), (1080, 1920, 3)) is noop
    assert _scale_decision_action(click, (540, 960, 3), (1080, 1920, 3)) is click


def test_live_gameplay_agent_exposes_step_runner() -> None:
    assert callable(getattr(LiveGameplayAgent, "step", None))


def test_scales_ocr_boxes_back_to_full_capture_pixels() -> None:
    words = [{"text": "Choice", "x": 100, "y": 200, "w": 50, "h": 20}]
    scaled = _scale_ocr_words(words, (720, 1280, 3), (1080, 1920, 3))
    assert scaled == [{"text": "Choice", "x": 150, "y": 300, "w": 75, "h": 30}]


def test_fmv_ocr_scans_full_resolution_choice_region_and_offsets_boxes() -> None:
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    with patch("scripts.live_gameplay_agent.ocr_frame", return_value=[{"text": "Choice", "x": 60, "y": 70, "w": 40, "h": 18}]) as ocr:
        words = ocr_fmv_frame(frame)
    assert ocr.call_args.args[0].shape == (382, 1616, 3)
    assert ocr.call_args.kwargs["psm"] == 6
    assert words == [{"text": "Choice", "x": 212, "y": 732, "w": 40, "h": 18}]
