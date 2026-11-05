import ctypes, ctypes.wintypes as wt
user32 = ctypes.windll.user32
found = []
@ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
def cb(h, _):
    b = ctypes.create_string_buffer(256)
    user32.GetWindowTextA(h, b, 256)
    name = b.value.decode("utf-8", "ignore") if isinstance(b.value, bytes) else str(b.value)
    if "agentveil" in name.lower():
        found.append(name)
    return True
user32.EnumWindows(cb, 0)
print(found)
