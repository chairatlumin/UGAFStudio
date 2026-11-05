"""Walk toward the biggest bright circle (mission marker) in Agent Veil."""
import av_state, cv2, numpy as np, time, ctypes

user32 = ctypes.windll.user32


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_uint32), ("dwFlags", ctypes.c_uint32),
                ("time", ctypes.c_uint32), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_uint32), ("time", ctypes.c_uint32),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class U(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_uint32), ("u", U)]


def rel_move(dx, dy):
    i = INPUT(type=0)
    i.u.mi = MOUSEINPUT(int(dx * 2.0), int(dy * 2.0), 0, 1, 0, None)
    user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(INPUT))


def key_sc(scan, t):
    scan = int(scan)
    i = INPUT(type=1)
    i.u.ki = KEYBDINPUT(0, scan, 8, 0, None)
    user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(INPUT))
    time.sleep(t)
    i = INPUT(type=1)
    i.u.ki = KEYBDINPUT(0, scan, 8 | 2, 0, None)
    user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(INPUT))


def find_target():
    img = av_state.avg_capture(6)
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(g, (9, 9), 2)
    c = cv2.HoughCircles(blur, cv2.HOUGH_GRADIENT, dp=1.5, minDist=120,
                         param1=80, param2=45, minRadius=20, maxRadius=350)
    target = None
    score = -1
    if c is not None:
        for x, y, r in np.round(c[0]).astype(int):
            b = int(g[y, x])
            if b > 150 and 300 < x < 1620 and y > 180:
                s = r * b
                if s > score:
                    score = s
                    target = (int(x), int(y), int(r))
    return target, img


for step in range(12):
    target, img = find_target()
    if target:
        x, y, r = target
        dx, dy = x - 960, y - 540
        print(f"step{step}: target ({x},{y}) r={r}")
        if abs(dx) > 60:
            rel_move(int(dx / 3), 0)
            time.sleep(0.25)
        if dy > 80:
            rel_move(0, int(dy / 3))
            time.sleep(0.25)
        key_sc(0x11, 2.0)
    else:
        print(f"step{step}: no target, turning")
        rel_move(600, 0)
        time.sleep(0.4)

img = av_state.avg_capture(12)
cv2.imwrite(r"C:\Users\Admin\UGAFStudio\screenshots\travel.png", img)
print("mean:", round(float(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).mean()), 1))
