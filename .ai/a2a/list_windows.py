import ctypes, ctypes.wintypes as wt
user32 = ctypes.windll.user32
found = []
@ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
def cb(h, _):
    b = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(h, b, 256)
    name = b.value
    if name.strip():
        found.append(name)
    return True
user32.EnumWindows(cb, 0)
for n in found:
    print(n)
