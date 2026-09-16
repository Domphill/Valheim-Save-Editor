"""A round Viking shield, drawn in code so the app needs no image files at runtime.

`python -m vse.icon assets/icon.ico` writes the .ico (and a .png) used for the exe build.
"""
import math
import struct
import sys
import tkinter as tk

RIM = "#2b1d0e"
BOSS = "#b8bec4"
RED = "#a3231f"
GOLD = "#d9a441"


def make_photo(size=32, master=None):
    img = tk.PhotoImage(width=size, height=size, master=master)
    c = (size - 1) / 2.0
    r = size / 2.0 - 0.5
    rim = max(1.5, size * 0.07)
    boss = size * 0.13
    rows, transparent = [], []
    for y in range(size):
        row = []
        for x in range(size):
            d = math.hypot(x - c, y - c)
            if d > r:
                row.append("#000000")
                transparent.append((x, y))
            elif d > r - rim:
                row.append(RIM)
            elif d < boss:
                row.append(BOSS)
            elif d < boss + max(1.0, size * 0.05):
                row.append(RIM)
            else:
                row.append(RED if (x < c) == (y < c) else GOLD)
        rows.append("{" + " ".join(row) + "}")
    img.put(" ".join(rows))
    for x, y in transparent:
        img.transparency_set(x, y, True)
    return img


def write_ico(path, size=64):
    root = tk.Tk()
    root.withdraw()
    img = make_photo(size, master=root)
    png_path = (path[:-4] if path.lower().endswith(".ico") else path) + ".png"
    img.write(png_path, format="png")
    root.destroy()
    with open(png_path, "rb") as f:
        png = f.read()
    header = struct.pack("<HHH", 0, 1, 1)
    entry = struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(png), 6 + 16)
    with open(path, "wb") as f:
        f.write(header + entry + png)
    return path, png_path


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "icon.ico"
    print("wrote", *write_ico(out))
