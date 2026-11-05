"""Bounded flow control for the High School Blood demo.

Reads the on-screen choice labels, waits for a named one, clicks it, and keeps
evidence frames.  The demo must run maximised: this process is per-monitor DPI
aware, otherwise Windows reports a 1536x864 window for a 1920x1080 one and every
capture/click lands 20% off.

Never skips, seeks, saves or quits: it only clicks a choice the caller names.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ctypes.windll.shcore.SetProcessDpiAwareness(2)  # must precede any window call

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_reconfigure = getattr(sys.stdout, "reconfigure", None)  # labels can hold «» and Thai
if _reconfigure is not None:
    _reconfigure(encoding="utf-8", errors="replace")

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from scripts.live_gameplay_agent import (  # noqa: E402
    find_game_hwnd,
    focus_game_window,
    get_window_rect,
    grab_frame,
    ocr_frame,
)

WINDOW_TITLE = "High School Blood"
REF_1536x864 = (1536, 864)
BAND_TOP = 0.70  # choice buttons sit in the bottom 30% of the frame
GAP_TOLERANCE = 30  # px; a wider gap on the same line means a different button

# Settings menu geometry, in the 1536x864 image the demo renders.
SETTINGS_TABS = {
    "gameplay": (230, 187),
    "graphics": (222, 297),
    "audio": (196, 407),
    "language": (230, 517),
    "back": (190, 796),
}
SETTINGS_TAB_MARKERS = {
    "gameplay": "DIFFICULTY",
    "graphics": "RESOLUTION",
    "audio": "MASTER",
    "language": "SUBTITLE LANGUAGE",
    "back": "HIGH SCHOOL BLOOD",
    "ingame": "ST. ALENGAR SCHOOL",
}
LANGUAGE_ROWS = {"game": 270, "subtitle": 377, "choice": 484}
TOGGLE_ROWS = {
    "protagonist_voice": 335,
    "subtitles": 407,
    "visual_choice": 484,
    "timer": 559,
    "camera_sway": 637,
    "content_filter": 713,
}
ARROW_LEFT_X, VALUE_X, ARROW_RIGHT_X, TOGGLE_X = 875, 1039, 1205, 1165
LANGUAGES = {"thai": "THAI", "english": "ENGLISH"}


def content_rect(frame: np.ndarray) -> tuple[int, int, int, int]:
    """Return (x, y, w, h) of the game image inside the window.

    The demo renders a 1536x864 image inside whatever client it is given and
    still spreads mouse input over the whole client, so coordinates read off a
    capture have to be scaled up to the window before they are clicked.  The
    letterbox area is exactly 0 while the image's own dark vignette is not, so
    a column or row counts as letterbox only when it is almost all zeros.
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    background = gray == 0
    cols = np.flatnonzero(background.mean(axis=0) < 0.9)
    rows = np.flatnonzero(background.mean(axis=1) < 0.9)
    if cols.size == 0 or rows.size == 0:
        return 0, 0, frame.shape[1], frame.shape[0]
    return int(cols[0]), int(rows[0]), int(cols[-1] - cols[0] + 1), int(rows[-1] - rows[0] + 1)


BUTTON_ROW = (650, 940)  # y band, in game-image px, where choice button text sits


def _in_dark_slab(gray: np.ndarray, x: int, y: int, w: int, h: int) -> bool:
    """True when a bright text blob has dark pixels on all four sides.

    Without this, a bright pillar or a white shirt in the video reads as a button
    and the playthrough clicks the video surface instead of a choice.
    """
    height, width = gray.shape
    above = gray[max(0, y - 12) : y, x : x + w]
    below = gray[min(height, y + h + 2) - 8 : min(height, y + h + 10), x : x + w]
    left = gray[y : y + h, max(0, x - 28) : x]
    right = gray[y : y + h, x + w : min(width, x + w + 28)]
    if min(above.size, below.size, left.size, right.size) == 0:
        return False
    return all(float((part < 70).mean()) > 0.7 for part in (above, below, left, right))


def find_choice_buttons(frame: np.ndarray, band_top: float = BAND_TOP) -> list[dict[str, int]]:
    """Return the choice buttons in the bottom band, left to right, in frame px.

    Detects the bright label instead of reading it, so a Thai choice language
    works without the Thai Tesseract model, which is not installed.  A button is
    a bright text blob inside a dark slab in ``BUTTON_ROW``; clicking its centre
    lands on the button because the label sits inside the slab.
    """
    x0, y0, width, height = content_rect(frame)
    gray = cv2.cvtColor(frame[y0 : y0 + height, x0 : x0 + width], cv2.COLOR_BGR2GRAY)
    top = max(int(height * band_top), BUTTON_ROW[0])
    band = gray[top : min(BUTTON_ROW[1], height)]
    if band.size == 0:
        return []
    # 25px bridges the widest gap inside one label without merging the ~65px
    # gap between two buttons.
    merged = cv2.dilate(np.where(band > 200, np.uint8(1), np.uint8(0)), np.ones((3, 25), np.uint8))

    count, _, stats, _ = cv2.connectedComponentsWithStats(merged, connectivity=8)
    boxes: list[dict[str, int]] = []
    for index in range(1, count):
        bx, by, bw, bh = (int(v) for v in stats[index][:4])
        if 40 <= bw <= 420 and 8 <= bh <= 45 and _in_dark_slab(gray, bx, top + by, bw, bh):
            boxes.append({"cx": x0 + bx + bw // 2, "cy": y0 + top + by + bh // 2, "w": bw})
    return sorted(boxes, key=lambda box: box["cx"])


def frame_to_screen(
    hwnd: int,
    frame: np.ndarray,
    point: tuple[int, int],
    reference_size: tuple[int, int] | None = None,
) -> tuple[int, int]:
    """Map capture pixels or reference-game coordinates to screen pixels.

    Captured pixels scale directly with the window rectangle. Coordinates in
    ``reference_size`` are first projected into the detected rendered image.
    """
    left, top, right, bottom = get_window_rect(hwnd)
    fh, fw = frame.shape[:2]
    sx, sy = (right - left) / fw if fw else 1.0, (bottom - top) / fh if fh else 1.0
    if reference_size is None:
        return left + round(point[0] * sx), top + round(point[1] * sy)
    reference_w, reference_h = reference_size
    if reference_w <= 0 or reference_h <= 0:
        raise ValueError("reference_size dimensions must be positive")
    content_x, content_y, content_w, content_h = content_rect(frame)
    content_w = content_w or fw
    content_h = content_h or fh
    frame_x = content_x + point[0] * content_w / reference_w
    frame_y = content_y + point[1] * content_h / reference_h
    return left + round(frame_x * sx), top + round(frame_y * sy)


def click_at(
    hwnd: int,
    frame: np.ndarray,
    point: tuple[int, int],
    reference_size: tuple[int, int] | None = REF_1536x864,
) -> tuple[int, int]:
    """Click a point in the reference game canvas or capture pixels."""
    screen = frame_to_screen(hwnd, frame, point, reference_size)
    focus_game_window(hwnd)
    from app.input.mouse_service import MouseService

    MouseService().click(x=screen[0], y=screen[1])
    time.sleep(1.2)
    return screen


def read_setting_value(hwnd: int, y: int) -> str:
    """OCR the value box of a language row; *y* is a capture pixel."""
    frame = grab_frame(hwnd)
    top = max(0, y - 24)
    crop = frame[top : top + 48, VALUE_X - 130 : VALUE_X + 130]
    return " ".join(str(word["text"]) for word in ocr_frame(crop, top_n=6)).upper()


TOGGLE_ON = 213  # knob brightness: measured 199-205 off, 221-252 on across six switches


def read_toggle_state(hwnd: int, y: int) -> str:
    """Return "on" or "off" for a settings switch by the brightness of its knob."""
    frame = grab_frame(hwnd)
    top = max(0, y - 16)
    crop = frame[top : top + 32, TOGGLE_X - 40 : TOGGLE_X + 40]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    return "on" if float(np.percentile(gray, 99)) > TOGGLE_ON else "off"


def normalize(text: str) -> str:
    """Lowercase and drop apostrophe variants so labels match regardless of glyph."""
    return " ".join(text.replace("'", "").replace("\u2019", "").lower().split())


def _same_line(word: dict[str, Any], line: list[dict[str, Any]]) -> bool:
    """True when *word* vertically overlaps *line* by half of the smaller box."""
    top = min(w["y"] for w in line)
    bottom = max(w["y"] + w["h"] for w in line)
    overlap = min(bottom, word["y"] + word["h"]) - max(top, word["y"])
    return bool(overlap > 0.5 * min(word["h"], bottom - top))


def group_labels(words: list[dict[str, Any]], gap_tol: int = GAP_TOLERANCE) -> list[dict[str, Any]]:
    """Group OCR words into one label per button: one text line, no big gap.

    Words are merged by vertical overlap, not by a fixed y bucket: Tesseract
    reports the two words of "Try It" a few pixels apart, which is enough to
    split one button into two unmatchable labels.
    """
    lines: list[list[dict[str, Any]]] = []
    for word in sorted(words, key=lambda w: w["y"] + w["h"] / 2):
        for line in lines:
            if _same_line(word, line):
                line.append(word)
                break
        else:
            lines.append([word])

    groups: list[list[dict[str, Any]]] = []
    for line in lines:
        line.sort(key=lambda w: w["x"])
        current: list[dict[str, Any]] = []
        for word in line:
            if current and word["x"] - (current[-1]["x"] + current[-1]["w"]) > gap_tol:
                groups.append(current)
                current = []
            current.append(word)
        if current:
            groups.append(current)

    labels: list[dict[str, Any]] = []
    for group in groups:
        x0 = min(w["x"] for w in group)
        y0 = min(w["y"] for w in group)
        x1 = max(w["x"] + w["w"] for w in group)
        y1 = max(w["y"] + w["h"] for w in group)
        labels.append(
            {
                "text": " ".join(str(w["text"]) for w in group),
                "cx": (x0 + x1) // 2,
                "cy": (y0 + y1) // 2,
            }
        )
    return labels


def read_choices(frame: np.ndarray, band_top: float = BAND_TOP) -> list[dict[str, Any]]:
    """Return the labels visible in the bottom band of the game image.

    Coordinates are in *frame* space.  *band_top* is a fraction of the drawn
    image: 0.70 skips the video for choice buttons, 0.0 reads the whole image
    for menu items.
    """
    x0, y0, width, height = content_rect(frame)
    band = int(height * band_top)
    words = ocr_frame(frame[y0 + band : y0 + height, x0 : x0 + width], top_n=40)
    for word in words:
        word["x"] += x0
        word["y"] += y0 + band
    return group_labels(words)


def find_label(labels: list[dict[str, Any]], wanted: str) -> dict[str, Any] | None:
    """Match *wanted* against the visible labels, exact first.

    Exact-first matters: "Try It" is a substring of "Don't Try It", so a
    single contains-pass could click the wrong story branch.
    """
    needle = normalize(wanted)
    for label in labels:
        if normalize(str(label["text"])) == needle:
            return label
    for label in labels:
        if needle in normalize(str(label["text"])):
            return label
    return None


def game_hwnd() -> int:
    handles = find_game_hwnd(WINDOW_TITLE)
    if not handles:
        raise SystemExit(f"window {WINDOW_TITLE!r} not found; is the demo running and maximised?")
    return handles[0][0]


def go_borderless(hwnd: int) -> tuple[int, int, int, int]:
    """Drop the caption and fill the monitor, then return the new window rect.

    The demo renders 1536x864 inside whatever client it is given and does not
    scale with it, so a captioned window both shrinks the game and pushes the
    choice buttons into a capture band the OCR misses.
    """
    user32 = ctypes.windll.user32
    gwl_style = -16
    ws_caption, ws_thickframe, ws_sysmenu = 0x00C00000, 0x00040000, 0x00080000
    style = user32.GetWindowLongW(hwnd, gwl_style)
    user32.SetWindowLongW(hwnd, gwl_style, style & ~(ws_caption | ws_thickframe | ws_sysmenu))
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE, else MoveWindow is ignored
    time.sleep(0.4)
    screen = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    user32.MoveWindow(hwnd, 0, 0, screen[0], screen[1], True)
    time.sleep(1.5)
    return get_window_rect(hwnd)


def shot(hwnd: int, evidence: Path, tag: str) -> np.ndarray:
    evidence.mkdir(parents=True, exist_ok=True)
    frame = grab_frame(hwnd)
    cv2.imwrite(str(evidence / f"{tag}.png"), frame)
    return frame


def wait_for_label(
    hwnd: int,
    wanted: str,
    timeout: float,
    poll: float,
    band_top: float = BAND_TOP,
) -> dict[str, Any] | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        label = find_label(read_choices(grab_frame(hwnd), band_top), wanted)
        if label is not None:
            return label
        time.sleep(poll)
    return None


def frame_text(hwnd: int) -> str:
    """Upper-cased text of the whole game image, for checking which screen is up."""
    return " ".join(str(word["text"]) for word in read_choices(grab_frame(hwnd), 0.0)).upper()


def wait_for_words(
    hwnd: int,
    words: tuple[str, ...],
    timeout: float = 12.0,
    poll: float = 1.0,
    click: tuple[int, int] | None = None,
) -> bool:
    """Wait until every word is on screen, clicking *click* again on each pass.

    The demo swallows the first click after it takes focus and its menus fade
    in, so a single click is not a reliable way to change screen.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        text = frame_text(hwnd)
        if all(word.upper() in text for word in words):
            return True
        if click is not None:
            click_at(hwnd, grab_frame(hwnd), click)
        time.sleep(poll)
    return False


def open_settings_tab(hwnd: int, tab: str) -> bool:
    return wait_for_words(hwnd, (SETTINGS_TAB_MARKERS[tab],), click=SETTINGS_TABS[tab])


def set_language(hwnd: int, key: str, want: str) -> str:
    """Cycle a language row until it reads *want*; return what it ended up as."""
    y = LANGUAGE_ROWS[key]
    current = read_setting_value(hwnd, y)
    for _ in range(3):
        if current == want:
            break
        click_at(hwnd, grab_frame(hwnd), (ARROW_RIGHT_X, y))
        current = read_setting_value(hwnd, y)
    return current


def set_toggle(hwnd: int, key: str, want: str) -> str:
    """Click a switch until it reads *want*; return the final on/off state."""
    y = TOGGLE_ROWS[key]
    state = read_toggle_state(hwnd, y)
    for _ in range(3):
        if state == want:
            break
        click_at(hwnd, grab_frame(hwnd), (TOGGLE_X, y))
        state = read_toggle_state(hwnd, y)
    return state


SAVE_GAME = (
    Path(os.environ["LOCALAPPDATA"]) / "HighSchoolBlood" / "Saved" / "SaveGames" / "CFA_DATA.sav"
)
MENU_NEW_GAME = (257, 494)
MENU_SETTINGS = (246, 656)
INGAME_EXIT_GAME = (767, 719)
SETTINGS_BACK = SETTINGS_TABS["back"]


def press_key(hwnd: int, key: str) -> None:
    from app.input.keyboard_service import KeyboardService

    focus_game_window(hwnd)
    KeyboardService().press(key)
    time.sleep(1.0)


MAIN_MENU_MARKER = "DEMO"  # the build string top-right only renders on menus
SETTINGS_MARKER = "DIFFICULTY"  # only the main-menu settings has this row


MENU_SCREENS = ("DIFFICULTY", "SUBTITLE LANGUAGE", "ST. ALENGAR SCHOOL", MAIN_MENU_MARKER)


def open_main_menu(hwnd: int) -> bool:
    """Leave any screen and end up on the main menu; return whether we got there.

    ESC only opens the in-game panel, which has to be closed with its own Exit
    Game, while the main-menu settings needs BACK.  The main menu is confirmed
    by the build string it draws in the corner, which the FMV frames lack.
    """
    for _ in range(3):
        text = frame_text(hwnd)
        if any(marker in text for marker in MENU_SCREENS):
            break
        press_key(hwnd, "escape")
    text = frame_text(hwnd)
    in_settings_menu = "DIFFICULTY" in text or "SUBTITLE LANGUAGE" in text
    click_at(
        hwnd,
        grab_frame(hwnd),
        SETTINGS_BACK if in_settings_menu else INGAME_EXIT_GAME,
    )
    time.sleep(1.5)
    return MAIN_MENU_MARKER in frame_text(hwnd)


def start_new_game(hwnd: int, evidence: Path) -> int:
    """Start a new playthrough only when no existing save could be displaced."""
    if SAVE_GAME.is_file():
        print(
            f"refusing to start a new game while a save exists: {SAVE_GAME}; "
            "load an approved disposable test fixture or handle the save manually"
        )
        return 1
    if not open_main_menu(hwnd):
        print("could not reach the main menu")
        return 1
    before = shot(hwnd, evidence, "newgame_before")
    for _ in range(3):
        click_at(hwnd, grab_frame(hwnd), MENU_NEW_GAME)
        time.sleep(4.0)
        after = grab_frame(hwnd)
        if MAIN_MENU_MARKER not in frame_text(hwnd):
            break
    shot(hwnd, evidence, "newgame_after")
    if MAIN_MENU_MARKER in frame_text(hwnd):
        print("NEW GAME did not start; still on the main menu")
        return 1
    moved = float(np.mean(cv2.absdiff(before, after).max(axis=2) > 12))
    print(f"playthrough started; menu -> story changed {moved:.3f} of the frame")
    return 0


def apply_settings(hwnd: int, args: argparse.Namespace) -> int:
    """Set the language rows and switches the caller asked for, and report them."""
    wanted_languages: dict[str, str] = {}
    for key, value in (
        ("game", args.game_language),
        ("subtitle", args.subtitles),
        ("choice", args.choice),
    ):
        if value:
            wanted_languages[key] = LANGUAGES[value]

    applied: dict[str, str] = {}
    if not open_main_menu(hwnd):
        print("could not reach the main menu")
        return 1
    if not wait_for_words(hwnd, (SETTINGS_MARKER,), click=MENU_SETTINGS):
        print("could not open the settings screen")
        return 1
    if wanted_languages:
        if not open_settings_tab(hwnd, "language"):
            print("could not open the language tab")
            return 1
        for key, value in wanted_languages.items():
            applied[f"{key}_language"] = set_language(hwnd, key, value).lower()
    if args.visual_choice:
        if not open_settings_tab(hwnd, "gameplay"):
            print("could not open the gameplay tab")
            return 1
        applied["visual_choice"] = set_toggle(hwnd, "visual_choice", args.visual_choice)

    evidence = args.evidence / f"settings_{'_'.join(sorted(applied)) or 'none'}"
    shot(hwnd, evidence, "result")
    print(json.dumps(applied, ensure_ascii=False, indent=2))
    return 0 if all(applied.get(k) == v.lower() for k, v in wanted_languages.items()) else 1


def play_through(hwnd: int, args: argparse.Namespace) -> int:
    """Take the leftmost option at every choice until the story stops moving.

    Choices are found as button slabs, not text, so a Thai choice language plays
    the same way; the OCR text is recorded when the language is English.
    """
    run_dir = args.evidence
    blockers = [marker for marker in MENU_SCREENS if marker in frame_text(hwnd)]
    if blockers:
        print(f"not in the story, on a menu screen ({', '.join(blockers)}); run newgame first")
        return 1
    choices: list[dict[str, Any]] = []
    advances: list[dict[str, Any]] = []
    advance_keys = [key for key in args.advance_keys.split(",") if key]
    deadline = time.monotonic() + args.max_minutes * 60
    last_move = time.monotonic()
    previous = grab_frame(hwnd)

    while time.monotonic() < deadline:
        frame = grab_frame(hwnd)
        boxes = find_choice_buttons(frame)
        if boxes:
            texts = [str(label["text"]) for label in read_choices(frame, BAND_TOP)]
            index = len(choices)
            pick = boxes[min(args.pick - 1, len(boxes) - 1)]
            shot(hwnd, run_dir, f"choice_{index:03d}")
            click_at(hwnd, frame, (pick["cx"], pick["cy"]), reference_size=None)
            time.sleep(2.5)
            shot(hwnd, run_dir, f"choice_{index:03d}_after")
            choices.append(
                {
                    "index": index,
                    "options": len(boxes),
                    "texts": texts,
                    "picked_index": min(args.pick - 1, len(boxes) - 1),
                    "status": "NEEDS_REVIEW",
                    "evidence": [f"choice_{index:03d}.png", f"choice_{index:03d}_after.png"],
                }
            )
            print(f"choice {index}: {len(boxes)} options, texts={texts}")
            previous, last_move = grab_frame(hwnd), time.monotonic()
            continue

        moved = float(np.mean(cv2.absdiff(frame, previous).max(axis=2) > 12))
        previous = frame
        if moved > 0.01:
            last_move = time.monotonic()
        elif time.monotonic() - last_move > args.advance_seconds:
            # The FMV stopped on an in-video prompt (a left/right minigame shows
            # as text in the scene, not as a button), so drive it with keys.
            for key in advance_keys:
                press_key(hwnd, key)
                time.sleep(2.0)
                after = grab_frame(hwnd)
                if float(np.mean(cv2.absdiff(frame, after).max(axis=2) > 12)) > 0.01:
                    index = len(advances)
                    shot(hwnd, run_dir, f"advance_{index:03d}")
                    advances.append(
                        {
                            "index": index,
                            "key": key,
                            "status": "NEEDS_REVIEW",
                            "evidence": [f"advance_{index:03d}.png"],
                        }
                    )
                    print(f"advance {index}: {key!r} moved the story")
                    previous, last_move = after, time.monotonic()
                    break
        if time.monotonic() - last_move > args.idle_minutes * 60:
            shot(hwnd, run_dir, "stuck")
            print(f"no change for {args.idle_minutes} min; stopping")
            break
        time.sleep(args.poll)

    run_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "game": "High School Blood Demo",
        "profile": "highschoolblood-demo",
        "choices": choices,
        "choice_count": len(choices),
        "advances": advances,
        "advance_count": len(advances),
        "qa_status": "UNASSERTED",
        "finished_at_utc": datetime.now(UTC).isoformat(),
    }
    (run_dir / "playthrough.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"recorded {len(choices)} choices and {len(advances)} advances in {run_dir}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=["probe", "click", "key", "fullscreen", "settings", "play", "newgame"],
    )
    parser.add_argument("target", nargs="?", help="choice label to click, or key name")
    parser.add_argument("--evidence", type=Path, default=ROOT / "reports" / "fmv_harness" / "flow")
    parser.add_argument("--tag", default="frame")
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--poll", type=float, default=2.0)
    parser.add_argument(
        "--band-top",
        type=float,
        default=BAND_TOP,
        help="fraction of the frame to skip; 0.70 for choice buttons, 0.0 for menu items",
    )
    parser.add_argument("--x", type=int, help="frame x to click instead of matching a label")
    parser.add_argument("--y", type=int, help="frame y to click instead of matching a label")
    parser.add_argument("--subtitles", choices=["thai", "english"], help="subtitle language")
    parser.add_argument("--choice", choices=["thai", "english"], help="choice language")
    parser.add_argument("--game-language", choices=["thai", "english"], help="game language")
    parser.add_argument("--visual-choice", choices=["on", "off"], help="visual choice rendering")
    parser.add_argument("--pick", type=int, default=1, help="1-based option to take at a choice")
    parser.add_argument(
        "--advance-keys",
        default="left,space",
        help="keys tried, in order, when the story stops moving",
    )
    parser.add_argument(
        "--advance-seconds", type=float, default=10.0, help="stillness before trying a key"
    )
    parser.add_argument(
        "--idle-minutes", type=float, default=8.0, help="stop after this much stillness"
    )
    parser.add_argument("--max-minutes", type=float, default=60.0, help="playthrough budget")
    args = parser.parse_args(argv)

    hwnd = game_hwnd()

    if args.command == "fullscreen":
        print("window rect", go_borderless(hwnd))
        print("captured", grab_frame(hwnd).shape)
        return 0

    if args.command == "settings":
        return apply_settings(hwnd, args)

    if args.command == "newgame":
        return start_new_game(hwnd, args.evidence / "newgame")

    if args.command == "play":
        return play_through(hwnd, args)

    if args.command == "key":
        from app.input.keyboard_service import KeyboardService

        focus_game_window(hwnd)
        KeyboardService().press(str(args.target))
        time.sleep(1.0)
        shot(hwnd, args.evidence, f"{args.tag}")
        return 0

    if args.command == "probe":
        labels = read_choices(grab_frame(hwnd), args.band_top)
        shot(hwnd, args.evidence, args.tag)
        for label in labels:
            print(f"  {label['text']!r} at frame ({label['cx']},{label['cy']})")
        if not labels:
            print("  no labels in the scanned band")
        return 0

    if args.x is not None and args.y is not None:
        # Menu text sits on artwork, which the OCR threshold misses; use
        # coordinates read off a captured frame instead.
        frame = shot(hwnd, args.evidence, f"{args.tag}_before")
        target = (args.x, args.y)
    elif not args.target:
        parser.error("click needs a label or --x/--y")
    else:
        hit = wait_for_label(hwnd, args.target, args.timeout, args.poll, args.band_top)
        if hit is None:
            shot(hwnd, args.evidence, f"{args.tag}_timeout")
            print(f"TIMEOUT: {args.target!r} never appeared within {args.timeout}s")
            return 1
        frame = shot(hwnd, args.evidence, f"{args.tag}_choice")
        target = (int(hit["cx"]), int(hit["cy"]))

    # --x/--y and OCR labels are already in frame px (ref=None).
    point = frame_to_screen(hwnd, frame, target)

    focus_game_window(hwnd)
    from app.input.mouse_service import MouseService

    MouseService().click(x=point[0], y=point[1])
    print(f"clicked frame {target} -> screen {point}")
    time.sleep(3.0)
    shot(hwnd, args.evidence, f"{args.tag}_after")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
