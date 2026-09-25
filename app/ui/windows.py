import os


def enable_dark_title_bar(widget):
    """Best-effort dark native title bar on Windows 10/11."""
    if os.name != "nt":
        return False

    try:
        import ctypes

        hwnd = int(widget.winId())
        value = ctypes.c_int(1)

        dwmapi = ctypes.windll.dwmapi

        for attribute in (20, 19):
            result = dwmapi.DwmSetWindowAttribute(
                ctypes.c_void_p(hwnd),
                ctypes.c_uint(attribute),
                ctypes.byref(value),
                ctypes.sizeof(value),
            )
            if result == 0:
                return True
    except (AttributeError, OSError, ValueError):
        return False

    return False
