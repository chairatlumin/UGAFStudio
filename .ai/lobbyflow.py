"""Lobbyflow driver for Agent Veil Demo (appid 4307180).

Stages (run one at a time):
    python .ai/lobbyflow.py launch
    python .ai/lobbyflow.py menu        # verify main menu, click Create Lobby
    python .ai/lobbyflow.py lobby       # verify lobby loaded
    python .ai/lobbyflow.py ball        # walk to HQ sphere + interact (E)
    python .ai/lobbyflow.py character   # pick character card
    python .ai/lobbyflow.py mission     # pick unlocked mission + confirm
    python .ai/lobbyflow.py loadcheck   # verify we loaded into the game
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

OUT = r"C:\Users\Admin\UGAFStudio\screenshots\lobbyflow"
os.makedirs(OUT, exist_ok=True)

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
try:
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
    pass
user32.SetProcessDPIAware()

APPID = 4307180


# ---------------------------------------------------------------- capture


def find_hwnd(title_part: str = "Agent Veil") -> int | None:
    found: list[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(h: int, _l: int) -> bool:
        buf = ctypes.create_string_buffer(256)
        user32.GetWindowTextA(h, buf, 256)
        if title_part.lower() in buf.value.decode("utf-8", "ignore").lower():
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
        raise RuntimeError("AgentVeil window not found")
    l, t, w, h = window_rect(hwnd)
    class RECT(ctypes.Structure):
        _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long),
                    ("r", ctypes.c_long), ("b", ctypes.c_long)]
    rc = RECT(l, t, l + w, t + h)
    hdc = user32.GetWindowDC(hwnd)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mem, bmp)
    user32.PrintWindow(hwnd, mem, 2)  # PW_RENDERFULLCONTENT
    class BIH(ctypes.Structure):
        _fields_ = [(x, c) for x, c in [
            ("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32),
            ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16),
            ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
            ("biSizeImage", ctypes.c_uint32), ("x", ctypes.c_int32),
            ("y", ctypes.c_int32), ("clr", ctypes.c_uint32)]]
    bi = BIH(); bi.biSize = ctypes.sizeof(BIH); bi.biWidth = w
    bi.biHeight = -h; bi.biPlanes = 1; bi.biBitCount = 32
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bi), 0)
    arr = np.frombuffer(buf.raw[: w * h * 4], dtype=np.uint8).reshape(h, w, 4)[:, :, :3].copy()
    gdi32.DeleteObject(bmp); gdi32.DeleteDC(mem); user32.ReleaseDC(hwnd, hdc)
    if not arr.any():
        # PrintWindow can return black for exclusive-fullscreen Unreal windows;
        # fall back to a desktop grab of the window rect.
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
              min_conf: int = 45) -> list[tuple[str, int, int]]:
    big = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_LANCZOS4)
    data = pytesseract.image_to_data(
        cv2.cvtColor(big, cv2.COLOR_BGR2RGB), config=f"--psm {psm}",
        output_type=pytesseract.Output.DICT)
    words = []
    for i, txt in enumerate(data["text"]):
        t = txt.strip()
        conf = float(data["conf"][i]) if data["conf"][i] not in ("-1", "") else -1
        if t and conf >= min_conf:
            words.append((t, int(data["left"][i] / scale), int(data["top"][i] / scale),
                          int(data["width"][i] / scale), int(data["height"][i] / scale)))
    return words


def find_word(words, *needles: str):
    """Return first matching word entry whose text contains any needle."""
    for needle in needles:
        low = needle.lower()
        for w in words:
            if low in w[0].lower():
                return w
    return None


# ---------------------------------------------------------------- input
# Foreground SendInput (background keybd_event does not reach Unreal menus).


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


SCAN = {"w": 0x11, "a": 0x1E, "s": 0x1F, "d": 0x20, "e": 0x12,
        "enter": 0x1C, "esc": 0x01, "space": 0x39}


def ensure_foreground() -> None:
    hwnd = find_hwnd()
    if hwnd:
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.3)


def click_xy(x: int, y: int) -> None:
    """Absolute click at virtual-screen coordinates via SendInput."""
    ensure_foreground()
    vx = user32.GetSystemMetrics(76)   # SM_XVIRTUALSCREEN
    vy = user32.GetSystemMetrics(77)
    vw = user32.GetSystemMetrics(78)
    vh = user32.GetSystemMetrics(79)
    ax = int((x - vx) * 65535 / max(vw - 1, 1))
    ay = int((y - vy) * 65535 / max(vh - 1, 1))
    for flags in (0x8000 | 0x0001, 0x8000 | 0x0002, 0x8000 | 0x0004):
        i = _INPUT(type=0)
        i.u.mi = _MI(ax, ay, 0, flags, 0, None)
        user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(_INPUT))
        time.sleep(0.05)


def rel_move(dx: int, dy: int) -> None:
    ensure_foreground()
    i = _INPUT(type=0)
    i.u.mi = _MI(int(dx * 2.0), int(dy * 2.0), 0, 1, 0, None)  # MOUSE_MOVE
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


def click_word(word_entry) -> None:
    _, wx, wy, ww, wh = word_entry
    l, t, _, _ = window_rect(find_hwnd())
    click_xy(l + wx + ww // 2, t + wy + wh // 2)


# ---------------------------------------------------------------- stages


def stage_launch() -> None:
    if find_hwnd():
        print("game already running")
        return
    subprocess.run(["cmd", "/c", "start", f"steam://run/{APPID}"], check=False)
    print("waiting for AgentVeil window...")
    for _ in range(120):
        time.sleep(3)
        if find_hwnd():
            break
    else:
        raise RuntimeError("window never appeared")
    print("window up, settling 25s...")
    time.sleep(25)
    img = avg_capture()
    save(img, "01_launched.png")
    print("words:", [w[0] for w in ocr_words(img)][:30])


def stage_menu() -> None:
    img = avg_capture()
    save(img, "02_menu.png")
    words = ocr_words(img)
    texts = [w[0] for w in words]
    print("menu words:", texts[:40])
    btn = find_word(words, "creat", "lobb")
    if btn:
        print("clicking:", btn)
        click_word(btn)
        time.sleep(8)
        img2 = avg_capture()
        save(img2, "03_after_createlobby.png")
        print("after words:", [w[0] for w in ocr_words(img2)][:40])
    else:
        print("Create Lobby NOT found")


def stage_lobby() -> None:
    img = avg_capture()
    save(img, "04_lobby.png")
    words = ocr_words(img)
    joined = " ".join(w[0] for w in words).lower()
    ok = any(k in joined for k in ("waiting for host", "mission", "no info"))
    print("lobby words sample:", [w[0] for w in words][:40])
    print("LOBBY OK" if ok else "LOBBY UNCERTAIN")


def stage_ball() -> None:
    """Walk toward biggest bright circle then press E to interact."""
    target = None
    for attempt in range(10):
        img = avg_capture(6)
        g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(g, (9, 9), 2)
        circles = cv2.HoughCircles(blur, cv2.HOUGH_GRADIENT, dp=1.5, minDist=120,
                                   param1=80, param2=45, minRadius=20, maxRadius=350)
        best, score = None, -1
        if circles is not None:
            for x, y, r in np.round(circles[0]).astype(int):
                if int(g[y, x]) > 150 and 300 < x < 1620 and y > 180:
                    s = r * int(g[y, x])
                    if s > score:
                        score, best = s, (int(x), int(y), int(r))
        if best is None:
            rel_move(600, 0)
            time.sleep(0.4)
            continue
        x, y, r = best
        print(f"attempt {attempt}: ball at ({x},{y}) r={r}")
        dx, dy = x - 960, y - 540
        if abs(dx) > 60:
            rel_move(dx // 3, 0)
            time.sleep(0.2)
        if dy > 80:
            rel_move(0, dy // 3)
            time.sleep(0.2)
        key("w", 2.0)
        target = best
    save(avg_capture(), "05_at_ball.png")
    if target:
        print("pressing E to interact...")
        key("e", 0.2)
        time.sleep(5)
        img = avg_capture()
        save(img, "06_interact_result.png")
        print("interact words:", [w[0] for w in ocr_words(img)][:40])
    else:
        print("NO BALL FOUND")


def stage_character() -> None:
    img = avg_capture()
    save(img, "07_character_screen.png")
    words = ocr_words(img)
    print("character words:", [w[0] for w in words][:50])


def stage_mission() -> None:
    img = avg_capture()
    save(img, "08_mission_screen.png")
    words = ocr_words(img)
    print("mission words:", [w[0] for w in words][:50])


STAGES = {
    "launch": stage_launch,
    "menu": stage_menu,
    "lobby": stage_lobby,
    "ball": stage_ball,
    "character": stage_character,
    "mission": stage_mission,
}

if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else "launch"
    STAGES[stage]()
