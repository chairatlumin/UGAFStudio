import ctypes, ctypes.wintypes as wt
import cv2, numpy as np, mss

user32 = ctypes.windll.user32
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
with mss.mss() as s:
    img = cv2.cvtColor(np.array(s.grab({"left": r.left, "top": r.top, "width": r.right-r.left, "height": r.bottom-r.top})), cv2.COLOR_BGRA2BGR)
cv2.imwrite(r"C:\Users\Admin\UGAFStudio\screenshots\av_after_agent.png", img)
print("saved", img.shape)
# OCR
import pytesseract
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
data = pytesseract.image_to_data(rgb, output_type=pytesseract.Output.DICT)
for i in range(len(data["text"])):
    t = data["text"][i].strip()
    if t and int(data["conf"][i]) > 45:
        print(f"{t!r:30} x={data['left'][i]:5} y={data['top'][i]:5}")
