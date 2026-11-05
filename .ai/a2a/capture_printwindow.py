import ctypes
import ctypes.wintypes as wt

import cv2
import numpy as np

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

PW_RENDERFULLCONTENT = 2

hwnd = None


@ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
def cb(h, _):
    global hwnd
    b = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(h, b, 256)
    if "agent veil" in b.value.lower() and user32.IsWindowVisible(h):
        hwnd = h
        return False
    return True


user32.EnumWindows(cb, 0)
assert hwnd, "window not found"

r = wt.RECT()
user32.GetWindowRect(hwnd, ctypes.byref(r))
w, hgt = r.right - r.left, r.bottom - r.top

hdc = user32.GetWindowDC(hwnd)
mem = gdi32.CreateCompatibleDC(hdc)
bmp = gdi32.CreateCompatibleBitmap(hdc, w, hgt)
gdi32.SelectObject(mem, bmp)
ok = user32.PrintWindow(hwnd, mem, PW_RENDERFULLCONTENT)

# BITMAPINFOHEADER
class BMIH(ctypes.Structure):
    _fields_ = [
        ("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32),
        ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16),
        ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
        ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32),
        ("biYPelsPerMeter", ctypes.c_int32), ("biClrUsed", ctypes.c_uint32),
        ("biClrImportant", ctypes.c_uint32),
    ]


bmi = BMIH(ctypes.sizeof(BMIH), w, -hgt, 1, 32, 0, 0, 0, 0, 0, 0)
buf = ctypes.create_string_buffer(w * hgt * 4)
gdi32.GetDIBits(mem, bmp, 0, hgt, buf, ctypes.byref(bmi), 0)
img = np.frombuffer(buf.raw, dtype=np.uint8).reshape(hgt, w, 4)[:, :, :3].copy()
cv2.imwrite(r"C:\Users\Admin\UGAFStudio\screenshots\av_pw.png", img)
print("PrintWindow ok:", ok, "shape:", img.shape)

import pytesseract  # noqa: E402

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
big = cv2.resize(img, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_LANCZOS4)
gray = cv2.cvtColor(big, cv2.COLOR_BGR2GRAY)
_, th = cv2.threshold(gray, 140, 255, cv2.THRESH_BINARY)
txt = pytesseract.image_to_string(th)
words = [t for t in txt.splitlines() if t.strip()]
print("OCR words:", words[:30])
