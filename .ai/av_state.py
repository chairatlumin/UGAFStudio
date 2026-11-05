"""Quick state check for Agent Veil window (DPI-aware)."""
import sys, time, ctypes
import cv2, numpy as np
import pytesseract
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
try:
    user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
    pass
user32.SetProcessDPIAware()
HWND = 3606126


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32),
                ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16),
                ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
                ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32),
                ("biYPelsPerMeter", ctypes.c_int32), ("biClrUsed", ctypes.c_uint32),
                ("biClrImportant", ctypes.c_uint32)]


class RGBQUAD(ctypes.Structure):
    _fields_ = [("b", ctypes.c_ubyte * 4)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", RGBQUAD * 1)]


def capture_pw():
    class RECT(ctypes.Structure):
        _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long),
                    ("r", ctypes.c_long), ("b", ctypes.c_long)]
    rc = RECT()
    user32.GetWindowRect(HWND, ctypes.byref(rc))
    w, h = rc.r - rc.l, rc.b - rc.t
    hdc = user32.GetWindowDC(HWND)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mem, bmp)
    user32.PrintWindow(HWND, mem, 2)
    bi = BITMAPINFO()
    bi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.bmiHeader.biWidth = w
    bi.bmiHeader.biHeight = -h
    bi.bmiHeader.biPlanes = 1
    bi.bmiHeader.biBitCount = 32
    bi.bmiHeader.biCompression = 0
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bi), 0)
    arr = np.frombuffer(buf.raw[:w * h * 4], dtype=np.uint8).reshape(h, w, 4)[:, :, :3].copy()
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    return arr


def avg_capture(n=15, delay=0.12):
    acc = None
    for _ in range(n):
        f = capture_pw().astype(np.float32)
        acc = f if acc is None else acc + f
        time.sleep(delay)
    return (acc / n).astype(np.uint8)


def ocr(img):
    big = cv2.resize(img, None, fx=3, fy=3)
    data = pytesseract.image_to_data(
        big, config="--psm 11", output_type=pytesseract.Output.DICT)
    words = []
    for i in range(len(data["text"])):
        t = data["text"][i].strip()
        if len(t) >= 4 and int(data["conf"][i]) > 25:
            words.append((t, data["left"][i] // 3, data["top"][i] // 3))
    return sorted(words, key=lambda w: w[2])


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "state.png"
    img = avg_capture()
    cv2.imwrite(rf"C:\Users\Admin\UGAFStudio\screenshots\{name}", img)
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    print("mean:", round(float(g.mean()), 1))
    for t, x, y in ocr(img):
        print(f"{t!r:28} x={x:5} y={y:5}")
