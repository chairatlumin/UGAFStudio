"""Capture ONLY the Agent Veil game window + OCR it."""
import sys, subprocess
sys.path.insert(0, r"C:\Users\Admin\UGAFStudio")
import cv2, numpy as np, mss, ctypes, ctypes.wintypes as wt

user32 = ctypes.windll.user32
TESS = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
OUT = r"C:\Users\Admin\UGAFStudio\screenshots"

def find_hwnd(title_part="Agent Veil"):
    found = []
    @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    def cb(h, _):
        buf = ctypes.create_string_buffer(256)
        user32.GetWindowTextA(h, buf, 256)
        # class name check too: Unreal windows often titled by game name
        name = buf.value
        if title_part.lower() in name.decode("utf-8","ignore").lower():
            found.append((h, name))
        return True
    user32.EnumWindows(cb, 0)
    return found

def window_rect(hwnd):
    r = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.left and r.bottom

def grab_window(name="av_win.png"):
    wins = [w for w in find_hwnd() if user32.IsWindowVisible(w[0])]
    if not wins:
        print("no window found"); sys.exit(1)
    hwnd, title = wins[0]
    l, t, r, b = (lambda rect: (rect[0], rect[1], rect[2], rect[3]))(window_rect(hwnd))
    with mss.mss() as s:
        img = cv2.cvtColor(np.array(s.grab({"left": l, "top": t,
            "width": r - l, "height": b - t})), cv2.COLOR_BGRA2BGR)
    path = OUT + "\\" + name
    cv2.imwrite(path, img)
    print(f"window {title!r} rect=({l},{t},{r},{b}) shape={img.shape}")
    return img

def ocr_words(img):
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = TESS
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    data = pytesseract.image_to_data(rgb, output_type=pytesseract.Output.DICT)
    words = []
    for i in range(len(data["text"])):
        t = data["text"][i].strip()
        if t and int(data["conf"][i]) > 45:
            words.append((t, data["left"][i], data["top"][i]))
    return words

if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "av_win.png"
    img = grab_window(name)
    for wtext, x, y in ocr_words(img):
        print(f"{wtext!r:35} x={x:5} y={y:5}")
