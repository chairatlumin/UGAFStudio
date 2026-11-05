"""Verification layer for UGAFStudio QA — explicit success/failure checkpoints."""

from __future__ import annotations

import time
from ctypes import windll
from dataclasses import dataclass, field
from typing import Callable

import cv2
import numpy as np
import psutil
import pytesseract
import win32gui
import win32ui

# Tesseract path for Windows
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


@dataclass
class Checkpoint:
    """A single verification checkpoint in a QA run."""

    name: str
    condition: Callable[[], bool]
    timeout: float = 30.0
    required: bool = True
    result: bool = False
    elapsed: float = 0.0

    def check(self) -> bool:
        """Evaluate condition, respecting timeout."""
        start = time.monotonic()
        deadline = start + self.timeout
        while time.monotonic() < deadline:
            try:
                if self.condition():
                    self.result = True
                    self.elapsed = time.monotonic() - start
                    return True
            except Exception:
                pass
            time.sleep(0.5)
        self.result = False
        self.elapsed = time.monotonic() - start
        return False


@dataclass
class QARun:
    """A full QA run with multiple checkpoints."""

    name: str
    checkpoints: list[Checkpoint]
    timestamps: dict[str, float] = field(default_factory=dict)
    cost_log: dict[str, float] = field(default_factory=dict)
    result: str = "pending"

    def run(self) -> bool:
        """Execute all checkpoints in order."""
        for cp in self.checkpoints:
            self.timestamps[cp.name] = time.time()
            ok = cp.check()
            if not ok and cp.required:
                self.result = f"failed:{cp.name}"
                return False
        self.result = "passed"
        return True

    def elapsed(self) -> float:
        return sum(cp.elapsed for cp in self.checkpoints)

    def report(self) -> dict:
        return {
            "name": self.name,
            "result": self.result,
            "elapsed": self.elapsed(),
            "checkpoints": {
                cp.name: {"result": cp.result, "elapsed": cp.elapsed}
                for cp in self.checkpoints
            },
            "cost_log": self.cost_log,
        }


# === Verification Primitives ===

def process_alive(pid: int) -> bool:
    """Check if a process is still running."""
    return bool(psutil.pid_exists(pid))


def window_visible(hwnd: int) -> bool:
    """Check if a window handle is visible."""
    try:
        result = win32gui.IsWindowVisible(hwnd)
        return int(result) != 0
    except Exception:
        return False


def _capture_window(hwnd: int) -> np.ndarray | None:
    """Capture window contents via PrintWindow."""
    try:
        left, top, right, bot = win32gui.GetClientRect(hwnd)
        width = right - left
        height = bot - top
        if width <= 0 or height <= 0:
            return None

        hwnd_dc = win32gui.GetWindowDC(hwnd)
        mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
        save_dc = mfc_dc.CreateCompatibleDC()

        bitmap = win32ui.CreateBitmap()
        bitmap.CreateCompatibleBitmap(mfc_dc, width, height)
        save_dc.SelectObject(bitmap)

        # PW_RENDERFULLCONTENT = 2
        windll.user32.PrintWindow(hwnd, save_dc.GetSafeHdc(), 2)

        bmp_info = bitmap.GetInfo()
        bmp_str = bitmap.GetBitmapBits(True)
        img = np.frombuffer(bmp_str, dtype=np.uint8).reshape(
            (bmp_info["bmHeight"], bmp_info["bmWidth"], 4)
        )

        win32gui.DeleteObject(bitmap.GetHandle())
        save_dc.DeleteDC()
        mfc_dc.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwnd_dc)

        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    except Exception:
        return None


def frame_rendered(hwnd: int) -> bool:
    """Check if a window is rendering non-blank content."""
    frame = _capture_window(hwnd)
    if frame is None:
        return False
    # Not all-black and not all-white (blank)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    mean_val = float(np.mean(gray))
    std_val = float(np.std(gray))
    return 5.0 < mean_val < 250.0 and std_val > 10.0


def state_ocr(hwnd: int, expected_words: list[str]) -> bool:
    """Check if window OCR contains any expected words."""
    frame = _capture_window(hwnd)
    if frame is None:
        return False
    try:
        text = pytesseract.image_to_string(frame).lower()
        return any(word.lower() in text for word in expected_words)
    except Exception:
        return False


def frame_diff(
    prev: np.ndarray | None,
    curr: np.ndarray | None,
    threshold: float = 0.1,
) -> bool:
    """Detect meaningful frame change between two frames."""
    if prev is None or curr is None:
        return False
    if prev.shape != curr.shape:
        return True
    diff = cv2.absdiff(prev, curr)
    gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 30, 255, cv2.THRESH_BINARY)
    change_ratio = float(np.sum(thresh > 0) / thresh.size)
    return change_ratio > threshold


def end_state_detected(hwnd: int, markers: list[str]) -> bool:
    """Check if window OCR contains end-state markers (menu, complete, etc.)."""
    return state_ocr(hwnd, markers)
