import ctypes, ctypes.wintypes as wt
user32 = ctypes.windll.user32
res = []
@ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
def cb(h, _):
    b = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(h, b, 256)
    if "agent veil" in b.value.lower():
        r = wt.RECT()
        user32.GetWindowRect(h, ctypes.byref(r))
        res.append((b.value, r.left, r.top, r.right, r.bottom, user32.IsWindowVisible(h), user32.IsIconic(h)))
    return True
user32.EnumWindows(cb, 0)
print(res)
