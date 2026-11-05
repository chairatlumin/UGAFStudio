"""Explore Agent Veil Demo: capture + OCR helper."""
import subprocess, sys, os
sys.path.insert(0, r"C:\Users\Admin\UGAFStudio")
import cv2, numpy as np, mss

TESS = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
OUT = r"C:\Users\Admin\UGAFStudio\screenshots"
os.makedirs(OUT, exist_ok=True)

def grab(name):
    with mss.mss() as s:
        mon = s.monitors[1]
        img = cv2.cvtColor(np.array(s.grab(mon)), cv2.COLOR_BGRA2BGR)
    path = os.path.join(OUT, name)
    cv2.imwrite(path, img)
    return img

def ocr(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=1.5, fy=1.5)
    tmp = r"C:\Users\Admin\AppData\Local\Temp\av_ocr.png"
    cv2.imwrite(tmp, gray)
    return subprocess.run([TESS, tmp, "stdout", "--psm", "6"],
                          capture_output=True, text=True).stdout

if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "av_menu_01.png"
    img = grab(name)
    print("shape", img.shape,
          "meanBGR", img.reshape(-1, 3).mean(axis=0).round(1),
          "nonblack%", round((img.max(axis=2) > 15).mean() * 100, 1))
    print("---- OCR ----")
    print(ocr(img))
