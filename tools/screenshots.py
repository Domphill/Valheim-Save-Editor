"""Regenerate the README screenshots (docs/*.png) from a live instance of the editor.

    python tools/screenshots.py path\\to\\Character.fch

Windows only. Captures with PrintWindow, so other windows in front do not matter. Needs
Pillow (pip install Pillow). The character file is only read.
"""
import ctypes
import os
import sys
import time
from ctypes import wintypes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
ctypes.windll.shcore.SetProcessDpiAwareness(1)

import tkinter as tk  # noqa: E402
from PIL import Image  # noqa: E402
import vse.app as A  # noqa: E402

user32, gdi32, dwm = ctypes.windll.user32, ctypes.windll.gdi32, ctypes.windll.dwmapi


class BMI(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


def capture(hwnd, path):
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    hdc = user32.GetWindowDC(hwnd)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    old = gdi32.SelectObject(mem, bmp)
    ok = user32.PrintWindow(hwnd, mem, 2)  # PW_RENDERFULLCONTENT
    bmi = BMI(biSize=ctypes.sizeof(BMI), biWidth=w, biHeight=-h, biPlanes=1, biBitCount=32, biCompression=0)
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(bmi), 0)
    img = Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1)
    gdi32.SelectObject(mem, old)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mem)
    user32.ReleaseDC(hwnd, hdc)
    vis = wintypes.RECT()  # crop the invisible DWM borders away (not reported while a game runs fullscreen)
    if (dwm.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(vis), ctypes.sizeof(vis)) == 0
            and vis.right > vis.left and vis.bottom > vis.top):
        img = img.crop((vis.left - rect.left, vis.top - rect.top, vis.right - rect.left, vis.bottom - rect.top))
    if not ok or img.getbbox() is None:
        sys.exit("PrintWindow returned nothing for %s; close fullscreen games and retry" % os.path.basename(path))
    img.save(path)
    print("%s  %dx%d  printwindow=%d" % (os.path.basename(path), img.width, img.height, ok))


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    root = tk.Tk()
    app = A.App(root)
    root.geometry("+0+0")
    app.open_file(sys.argv[1])
    root.update()
    hwnd = user32.GetParent(root.winfo_id())
    for name, tab, slot in (("character", app.tab_char, None), ("inventory", app.tab_inv, (0, 0)),
                            ("skills", app.tab_skills, None), ("worlds", app.tab_worlds, None),
                            ("guide", app.tab_guide, None)):
        app.nb.select(tab)
        if slot:
            app.select(*slot)
        if name == "guide":
            for sec in app.guide_tree.get_children():
                for row in app.guide_tree.get_children(sec):
                    if app.guide_tree.item(row)["text"] == "Mistwalker":
                        app.guide_tree.selection_set(row)
                        app.guide_tree.see(row)
        for _ in range(6):
            root.update()
        time.sleep(0.4)
        root.update()
        capture(hwnd, os.path.join(ROOT, "docs", name + ".png"))
    root.destroy()
    return 0


if __name__ == "__main__":
    sys.exit(main())
