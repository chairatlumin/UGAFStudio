from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pytest

from qa_framework.gameplay_agent.actions import Action
from scripts.live_gameplay_agent import _fmv_action_grounded, _menu_keyword_matches, ocr_menu_region


def test_menu_ocr_uses_normalized_crop_and_returns_frame_coordinates() -> None:
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    data = {
        "text": ["", "SETTINGS"],
        "conf": ["-1", "95"],
        "left": [0, 30],
        "top": [0, 60],
        "width": [0, 180],
        "height": [0, 30],
    }
    with patch("scripts.live_gameplay_agent.pytesseract.image_to_data", return_value=data) as ocr:
        words = ocr_menu_region(frame, (0.1, 0.2, 0.5, 0.5))
    assert words == [{"text": "SETTINGS", "x": 30, "y": 40, "w": 60, "h": 10}]
    assert ocr.call_args.kwargs["config"].startswith("--psm 6")


@pytest.mark.parametrize("region", [(-0.1, 0.2, 0.5, 0.5), (0.8, 0.2, 0.5, 0.5), (0, 0, 0, 0.5)])
def test_menu_ocr_rejects_invalid_regions(region) -> None:
    with pytest.raises(ValueError, match="normalized menu region"):
        ocr_menu_region(np.zeros((100, 200, 3), dtype=np.uint8), region)


def test_menu_keyword_matches_merged_label_with_ocr_spaces_removed() -> None:
    assert _menu_keyword_matches("NEWGAME", "new game")
    assert not _menu_keyword_matches("started", "start")


def test_fmv_blocks_clicks_on_subtitle_even_if_words_resemble_menu_cues() -> None:
    words = [{"text": "started teaching here", "x": 400, "y": 900, "w": 400, "h": 40}]
    action = Action("click", {"x": 600, "y": 920, "button": "left"})
    assert not _fmv_action_grounded(action, words, [], frozenset({"start", "new"}))


def test_fmv_allows_click_grounded_on_visible_choice_and_blocks_subtitle() -> None:
    words = [
        {"text": "Take", "x": 695, "y": 873, "w": 69, "h": 25},
        {"text": "the", "x": 774, "y": 873, "w": 48, "h": 25},
        {"text": "Pill", "x": 834, "y": 873, "w": 38, "h": 25},
        {"text": "Everyone", "x": 427, "y": 945, "w": 136, "h": 26},
    ]
    choices = ["take the pill"]
    assert _fmv_action_grounded(
        Action("click", {"x": 790, "y": 885}), words, choices, frozenset()
    )
    assert not _fmv_action_grounded(
        Action("click", {"x": 490, "y": 957}), words, choices, frozenset()
    )


def test_fmv_coordinate_free_click_needs_exact_visible_menu_label() -> None:
    words = [{"text": "NEWGAME", "x": 120, "y": 500, "w": 220, "h": 40}]
    assert _fmv_action_grounded(Action("click", {}), words, [], frozenset({"new game"}))
    assert not _fmv_action_grounded(
        Action("click", {}), [{"text": "started", "x": 120, "y": 500, "w": 220, "h": 40}], [], frozenset({"start"})
    )
