"""OCR menu region (bottom-left area) with upscaling for small text."""
import subprocess, sys, os
sys.path.insert(0, r"C:\Users\Admin\UGAFStudio")
from explore_av import grab  # noqa
import cv2

img = grab("av_menu_zoom.png")
h, w = img.shape[:2]
# crop left half where menu items appear
crop = img[int(h*0.4):int(h*0.95), 0:int(w*0.45)]
crop = cv2.resize(crop, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
gray = cv2.GaussianBlur(gray, (3, 3), 0)
tmp = r"C:\Users\Admin\AppData\Local\Temp\av_menu.png"
cv2.imwrite(tmp, gray)
out = subprocess.run([r"C:\Program Files\Tesseract-OCR\tesseract.exe",
                      tmp, "stdout", "--psm", "6"],
                     capture_output=True, text=True).stdout
print(out)
