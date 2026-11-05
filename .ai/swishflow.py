"""SHINEBRINGERS (SwishAndFlick) flow driver.

Stages:
    python .ai/swishflow.py probe      # OCR current screen
    python .ai/swishflow.py click X Y  # foreground click at window coords
    python .ai/swishflow.py key NAME [HOLD]   # w/a/s/d/e/f/enter/esc/space
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
import sys
import time

import cv2
import numpy as np
import pytesseract

TESS = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
pytesseract.pytesseract.tesseract_cmd = TESS

OUT = r"C:\Users\Admin\UGAFStudio\screenshots\swishflow"
os.makedirs(OUT, exist_ok=True)

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
try:
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
    pass
user32.SetProcessDPIAware()

TITLE = "SwishAndFlick"


def find_hwnd(title_part: str = TITLE) -> int | None:
    found: list[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(h: int, _l: int) -> bool:
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(h, buf, 256)
        if title_part.lower() in buf.value.lower():
            found.append(h)
        return True

    user32.EnumWindows(cb, 0)
    vis = [h for h in found if user32.IsWindowVisible(h)]
    return vis[0] if vis else (found[0] if found else None)


def window_rect(hwnd: int) -> tuple[int, int, int, int]:
    r = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right - r.left, r.bottom - r.top


def capture(hwnd: int | None = None) -> np.ndarray:
    hwnd = hwnd or find_hwnd()
    if not hwnd:
        raise RuntimeError("SwishAndFlick window not found")
    l, t, w, h = window_rect(hwnd)

    class BIH(ctypes.Structure):
        _fields_ = [(x, c) for x, c in [
            ("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32),
            ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16),
            ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
            ("biSizeImage", ctypes.c_uint32), ("x", ctypes.c_int32),
            ("y", ctypes.c_int32), ("clr", ctypes.c_uint32)]]

    hdc = user32.GetWindowDC(hwnd)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mem, bmp)
    user32.PrintWindow(hwnd, mem, 2)
    bi = BIH()
    bi.biSize = ctypes.sizeof(BIH)
    bi.biWidth = w
    bi.biHeight = -h
    bi.biPlanes = 1
    bi.biBitCount = 32
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bi), 0)
    arr = np.frombuffer(buf.raw[: w * h * 4], dtype=np.uint8).reshape(h, w, 4)[:, :, :3].copy()
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(hwnd, hdc)
    if not arr.any():
        import mss
        with mss.MSS() as s:
            shot = s.grab({"left": l, "top": t, "width": w, "height": h})
        return cv2.cvtColor(np.array(shot), cv2.COLOR_BGRA2BGR)
    return arr


def avg_capture(n: int = 12, delay: float = 0.1) -> np.ndarray:
    frames = [capture().astype(np.float32) for _ in range(n)]
    time.sleep(delay)
    return np.mean(frames, axis=0).astype(np.uint8)


def save(img: np.ndarray, name: str) -> str:
    path = os.path.join(OUT, name)
    cv2.imwrite(path, img)
    return path


def ocr_words(img: np.ndarray, scale: float = 2.0, psm: int = 11,
              min_conf: int = 45) -> list[tuple[str, int, int, int, int]]:
    big = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_LANCZOS4)
    data = pytesseract.image_to_data(
        cv2.cvtColor(big, cv2.COLOR_BGR2RGB), config=f"--psm {psm}",
        output_type=pytesseract.Output.DICT)
    out = []
    for i, txt in enumerate(data["text"]):
        t = txt.strip()
        conf = float(data["conf"][i]) if data["conf"][i] not in ("-1", "") else -1
        if t and conf >= min_conf:
            out.append((t, int(data["left"][i] / scale), int(data["top"][i] / scale),
                        int(data["width"][i] / scale), int(data["height"][i] / scale)))
    return out


def ocr_thresh(img: np.ndarray, lo: int = 120, psm: int = 11) -> list[tuple[str, int, int, int, int]]:
    """OCR after brightness threshold — for bright UI on dark game scenes."""
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, th = cv2.threshold(g, lo, 255, cv2.THRESH_BINARY)
    d = pytesseract.image_to_data(th, config=f"--psm {psm}",
                                  output_type=pytesseract.Output.DICT)
    out = []
    for i, t in enumerate(d["text"]):
        tt = t.strip()
        conf = float(d["conf"][i]) if d["conf"][i] not in ("-1", "") else -1
        if tt and conf >= 30:
            out.append((tt, int(d["left"][i]), int(d["top"][i]),
                        int(d["width"][i]), int(d["height"][i])))
    return out


# ------------------------------------------------------------------ input

class _MI(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_uint32), ("dwFlags", ctypes.c_uint32),
                ("time", ctypes.c_uint32), ("extra", ctypes.POINTER(ctypes.c_ulong))]


class _KI(ctypes.Structure):
    _fields_ = [("vk", ctypes.c_ushort), ("scan", ctypes.c_ushort),
                ("flags", ctypes.c_uint32), ("time", ctypes.c_uint32),
                ("extra", ctypes.POINTER(ctypes.c_ulong))]


class _U(ctypes.Union):
    _fields_ = [("mi", _MI), ("ki", _KI)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_uint32), ("u", _U)]


SCAN = {"w": 0x11, "a": 0x1E, "s": 0x1F, "d": 0x20, "e": 0x12, "f": 0x21,
        "enter": 0x1C, "esc": 0x01, "space": 0x39, "tab": 0x0F, "q": 0x10,
        "r": 0x13, "1": 0x02, "2": 0x03, "3": 0x04, "4": 0x05, "5": 0x06}


def ensure_foreground() -> None:
    hwnd = find_hwnd()
    if hwnd and user32.GetForegroundWindow() != hwnd:
        fg = user32.GetForegroundWindow()
        tid1 = user32.GetWindowThreadProcessId(fg, None)
        tid2 = user32.GetWindowThreadProcessId(hwnd, None)
        user32.AttachThreadInput(tid1, tid2, True)
        user32.SetForegroundWindow(hwnd)
        user32.AttachThreadInput(tid1, tid2, False)
        time.sleep(0.3)


def click_xy(x: int, y: int) -> None:
    """Click at WINDOW-relative coords."""
    ensure_foreground()
    hwnd = find_hwnd()
    l, t, _, _ = window_rect(hwnd)
    vx = user32.GetSystemMetrics(76)
    vy = user32.GetSystemMetrics(77)
    vw = user32.GetSystemMetrics(78)
    vh = user32.GetSystemMetrics(79)
    ax = int((l + x - vx) * 65535 / max(vw - 1, 1))
    ay = int((t + y - vy) * 65535 / max(vh - 1, 1))
    for flags in (0x8000 | 0x0001, 0x8000 | 0x0002, 0x8000 | 0x0004):
        i = _INPUT(type=0)
        i.u.mi = _MI(ax, ay, 0, flags, 0, None)
        user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(_INPUT))
        time.sleep(0.05)


def rel_move(dx: int, dy: int) -> None:
    ensure_foreground()
    i = _INPUT(type=0)
    i.u.mi = _MI(int(dx * 2.0), int(dy * 2.0), 0, 1, 0, None)
    user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(_INPUT))


def key(name: str, hold: float = 0.15) -> None:
    ensure_foreground()
    scan = SCAN[name]
    i = _INPUT(type=1)
    i.u.ki = _KI(0, scan, 8, 0, None)
    user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(_INPUT))
    time.sleep(hold)
    i = _INPUT(type=1)
    i.u.ki = _KI(0, scan, 8 | 2, 0, None)
    user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(_INPUT))


def find_word(words: list, *needles: str):
    for needle in needles:
        low = needle.lower()
        for w in words:
            if low in w[0].lower():
                return w
    return None


# ------------------------------------------------------------------ stages

def stage_probe() -> None:
    img = avg_capture()
    save(img, f"probe_{int(time.time())}.png")
    print("== plain ==")
    for w in ocr_words(img)[:40]:
        print(w)
    print("== thresholded ==")
    for w in ocr_thresh(img)[:40]:
        print(w)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "probe"
    if cmd == "probe":
        stage_probe()
    elif cmd == "click":
        click_xy(int(sys.argv[2]), int(sys.argv[3]))
        time.sleep(int(sys.argv[4]) if len(sys.argv) > 4 else 5)
        img = avg_capture(10)
        save(img, f"after_click_{sys.argv[2]}_{sys.argv[3]}.png")
        print("words:", [w[0] for w in ocr_words(img)][:30])
        print("thresh:", [w[0] for w in ocr_thresh(img)][:30])
    elif cmd == "key":
        key(sys.argv[2], float(sys.argv[3]) if len(sys.argv) > 3 else 0.15)
        time.sleep(3)
        img = avg_capture(10)
        save(img, f"after_key_{sys.argv[2]}.png")
        print("thresh:", [w[0] for w in ocr_thresh(img)][:30])
