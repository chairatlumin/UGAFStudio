from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from scripts.hsb_flow import (
    content_rect,
    find_choice_buttons,
    find_label,
    group_labels,
    normalize,
    start_new_game,
)


def _words() -> list[dict[str, Any]]:
    return [
        {"text": "Try", "x": 40, "y": 100, "w": 60, "h": 24},
        {"text": "It", "x": 105, "y": 103, "w": 25, "h": 24},
        {"text": "Don't", "x": 400, "y": 100, "w": 70, "h": 24},
        {"text": "Try", "x": 475, "y": 100, "w": 60, "h": 24},
        {"text": "It", "x": 540, "y": 100, "w": 25, "h": 24},
    ]


def test_group_labels_splits_buttons_on_the_same_line() -> None:
    labels = group_labels(_words())
    assert [label["text"] for label in labels] == ["Try It", "Don't Try It"]


def test_group_labels_returns_button_centre() -> None:
    first = group_labels(_words())[0]
    assert (first["cx"], first["cy"]) == (85, 113)


def test_find_label_prefers_exact_over_contains() -> None:
    labels = group_labels(_words())
    assert find_label(labels, "Try It") == labels[0]
    assert find_label(labels, "Don't Try It") == labels[1]


def test_normalize_ignores_case_and_apostrophe_glyphs() -> None:
    assert normalize("  Don\u2019t Try  It ") == normalize("don't try it")


def test_content_rect_finds_the_letterboxed_game_image() -> None:
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    frame[20:850, 0:1536] = 200
    assert content_rect(frame) == (0, 20, 1536, 830)


def test_content_rect_falls_back_to_the_whole_frame_when_all_black() -> None:
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    assert content_rect(frame) == (0, 0, 1920, 1080)


def _choice_screen() -> np.ndarray:
    """A 1920x1080 window holding a 1536x864 game image with two choice buttons."""
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    frame[0:864, 0:1536] = 150
    for left in (500, 1000):
        frame[675:745, left : left + 250] = 10
        frame[700:720, left + 100 : left + 160] = 240
    return frame


def test_find_choice_buttons_finds_both_buttons_left_to_right() -> None:
    boxes = find_choice_buttons(_choice_screen())
    assert [box["cx"] for box in boxes] == [630, 1130]


def test_find_choice_buttons_ignores_a_frame_without_choices() -> None:
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    frame[0:864, 0:1536] = 150
    assert find_choice_buttons(frame) == []


def test_find_choice_buttons_ignores_a_lone_centred_bright_line() -> None:
    """One centred blob in the band is the subtitle line, not a one-button choice."""
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    frame[0:864, 0:1536] = 150
    frame[800:830, 600:940] = 240
    assert find_choice_buttons(frame) == []


def test_find_choice_buttons_ignores_bright_video_detail() -> None:
    """A bright patch with bright surroundings is the video, not a button label."""
    frame = _choice_screen()
    frame[800:840, 200:400] = 240
    assert [box["cx"] for box in find_choice_buttons(frame)] == [630, 1130]


def test_start_new_game_refuses_to_move_or_overwrite_an_existing_save(
    tmp_path: Path, monkeypatch
) -> None:
    import scripts.hsb_flow as hsb

    save = tmp_path / "CFA_DATA.sav"
    save.write_bytes(b"user save")
    monkeypatch.setattr(hsb, "SAVE_GAME", save)
    monkeypatch.setattr(
        hsb, "open_main_menu", lambda _hwnd: pytest.fail("must stop before game input")
    )

    assert start_new_game(1, tmp_path) == 1
    assert save.read_bytes() == b"user save"
    assert not list(tmp_path.glob("*.stashed"))

