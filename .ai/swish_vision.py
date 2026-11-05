"""Vision-based button locator for SHINEBRINGERS flow.

Finds buttons by reading the screen (cua-driver screenshot) + OCR every time,
so layout changes don't break the flow.

Usage:
    python .ai/swish_vision.py click_text "Play Showcase"   # find+click by text
    python .ai/swish_vision.py read                          # dump visible words
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import sys
import time

import cv2
import numpy as np
import pytesseract

TESS = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
pytesseract.pytesseract.tesseract_cmd = TESS

OUT = r"C:\Users\Admin\UGAFStudio\screenshots\swishflow"
os.makedirs(OUT, exist_ok=True)

GAME_PID = 65912  # refreshed by find_game_pid()
user32 = ctypes.windll.user32


def find_game_pid(exe_part: str = "SwishAndFlickDemo-Win64") -> int | None:
    out = subprocess.run(["tasklist"], capture_output=True, text=True).stdout.lower()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and exe_part.lower() in parts[0]:
            try:
                return int(parts[1])
            except ValueError:
                continue
    return None


def game_window() -> tuple[int, int] | None:
    pid = find_game_pid()
    if not pid:
        return None
    res: list[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(h, _):
        p = wt.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid and user32.IsWindowVisible(h):
            buf = ctypes.create_unicode_buffer(64)
            user32.GetWindowTextW(h, buf, 64)
            if "Swish" in buf.value or "Unreal" in buf.value:
                res.append(h)
        return True

    user32.EnumWindows(cb, 0)
    return (pid, res[0]) if res else None


def grab_screen() -> tuple[np.ndarray, tuple[int, int, int, int]]:
    """Screenshot the game window region; returns (img, window_rect)."""
    rect = window_rect_of_game()
    return _fallback_mss(rect), rect


def _fallback_mss(rect):
    import mss
    l, t, w, h = rect
    with mss.MSS() as s:
        img = cv2.cvtColor(
            np.array(s.grab({"left": l, "top": t, "width": w, "height": h})),
            cv2.COLOR_BGRA2BGR,
        )
    return img


def words_on(img: np.ndarray) -> list[dict]:
    """OCR with boxes on the raw image."""
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    d = pytesseract.image_to_data(g, config="--psm 11", output_type=pytesseract.Output.DICT)
    words = []
    for i, t in enumerate(d["text"]):
        tt = t.strip()
        conf = float(d["conf"][i]) if d["conf"][i] not in ("-1", "") else -1
        if tt and conf >= 40:
            words.append({
                "text": tt, "conf": conf,
                "x": int(d["left"][i]), "y": int(d["top"][i]),
                "w": int(d["width"][i]), "h": int(d["height"][i]),
            })
    return words


def group_words_to_phrases(words: list[dict], y_tol: float = 0.6) -> list[dict]:
    """Merge same-line words into phrases so multi-word buttons are one target."""
    phrases: list[list[dict]] = []
    for w in sorted(words, key=lambda w: (w["y"], w["x"])):
        placed = False
        for ph in phrases:
            ref = ph[-1]
            same_line = abs(w["y"] - ref["y"]) <= max(ref["h"], w["h"]) * y_tol
            adjacent = 0 < w["x"] - (ref["x"] + ref["w"]) < 60
            if same_line and adjacent:
                ph.append(w)
                placed = True
                break
        if not placed:
            phrases.append([w])
    out = []
    for ph in phrases:
        x0 = min(w["x"] for w in ph); y0 = min(w["y"] for w in ph)
        x1 = max(w["x"] + w["w"] for w in ph); y1 = max(w["y"] + w["h"] for w in ph)
        out.append({"text": " ".join(w["text"] for w in ph),
                    "x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0})
    return out


def find_phrase(img: np.ndarray, needle: str):
    """Locate a phrase containing `needle` (case-insensitive). Returns box dict."""
    low = needle.lower()
    for ph in group_words_to_phrases(words_on(img)):
        if low in ph["text"].lower():
            return ph
    # fallback: single word match
    for w in words_on(img):
        if low in w["text"].lower():
            return w
    return None


def click_phrase(needle: str, settle: float = 10.0, double: bool = False) -> bool:
    """Find phrase on screen then foreground-click it. Returns True if found."""
    img = _fallback_mss(window_rect_of_game())
    save_img(img, f"find_{needle.replace(' ', '_')}.png")
    ph = find_phrase(img, needle)
    if not ph:
        print(f"NOT FOUND: {needle}")
        return False
    cx = ph["x"] + ph["w"] // 2
    cy = ph["y"] + ph["h"] // 2
    l, t, _, _ = window_rect_of_game()
    sx, sy = l + cx, t + cy
    print(f"found {ph['text']!r} at screen ({sx},{sy}) — clicking")
    ensure_foreground()
    user32.SetCursorPos(sx, sy)
    time.sleep(0.6)
    flags_seq = (0x0002, 0x0004)
    if double:
        flags_seq = (0x0002, 0x0004, 0x0002, 0x0004)
    for fl in flags_seq:
        i = _INPUT(type=0)
        i.u.mi = _MI(0, 0, 0, fl, 0, None)
        user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(_INPUT))
        time.sleep(0.12)
    time.sleep(settle)
    return True


# ---- input plumbing (same SendInput approach as swishflow.py)

class _MI(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_uint32), ("dwFlags", ctypes.c_uint32),
                ("time", ctypes.c_uint32), ("extra", ctypes.POINTER(ctypes.c_ulong))]


class _KI(ctypes.Structure):
    _fields_ = [("vk", ctypes.c_ushort), ("scan", ctypes.c_ushort),
                ("flags", ctypes.c_uint32), ("time", ctypes.c_uint32),
                ("extra", ctypes.POINTER(ctypes.c_ulong))]


class _INPUT(ctypes.Structure):
    class U(ctypes.Union):
        _fields_ = [("mi", _MI), ("ki", _KI)]
    _fields_ = [("type", ctypes.c_uint32), ("u", U)]


SCAN = {"w": 0x11, "a": 0x1E, "s": 0x1F, "d": 0x20, "e": 0x12, "f": 0x21,
        "enter": 0x1C, "esc": 0x01, "space": 0x39}


def ensure_foreground():
    gw = game_window()
    if gw:
        hwnd = gw[1]
        if user32.GetForegroundWindow() != hwnd:
            fg = user32.GetForegroundWindow()
            t1 = user32.GetWindowThreadProcessId(fg, None)
            t2 = user32.GetWindowThreadProcessId(hwnd, None)
            user32.AttachThreadInput(t1, t2, True)
            user32.SetForegroundWindow(hwnd)
            user32.AttachThreadInput(t1, t2, False)
            time.sleep(0.3)


def press_key(name: str, hold: float = 0.15):
    ensure_foreground()
    scan = SCAN[name]
    i = _INPUT(type=1)
    i.u.ki = _KI(0, scan, 8, 0, None)
    user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(_INPUT))
    time.sleep(hold)
    i = _INPUT(type=1)
    i.u.ki = _KI(0, scan, 8 | 2, 0, None)
    user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(_INPUT))


def window_rect_of_game():
    gw = game_window()
    if not gw:
        raise RuntimeError("game gone")
    r = wt.RECT()
    user32.GetWindowRect(gw[1], ctypes.byref(r))
    return r.left, r.top, r.right - r.left, r.bottom - r.left


def save_img(img, name):
    cv2.imwrite(os.path.join(OUT, name), img)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "read"
    if cmd == "read":
        img = _fallback_mss(window_rect_of_game())
        save_img(img, "vision_read.png")
        for ph in group_words_to_phrases(words_on(img)):
            print(ph["text"], (ph["x"], ph["y"], ph["w"], ph["h"]))
    elif cmd == "click_text":
        ok = click_phrase(sys.argv[2],
                          settle=float(sys.argv[3]) if len(sys.argv) > 3 else 10.0,
                          double="--double" in sys.argv)
        sys.exit(0 if ok else 2)
