#!/usr/bin/env python3
"""Regenerate vse/itemdata.py from an installed copy of Valheim.

Developer tool, not needed to run the editor. Requires:  pip install UnityPy

    python tools/generate_itemdata.py [path/to/Valheim]

Reads every ItemDrop prefab from the game's asset bundles (name, type, stack limit,
durability, quality levels) and the English strings from the game's localization table,
and writes them as a plain Python dict. Only prefabs that are actual inventory items,
meaning they appear in vse/items.py, are kept.
"""
import collections
import csv
import datetime
import glob
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vse import items as itemdb  # noqa: E402

try:
    import UnityPy
except ImportError:
    sys.exit("UnityPy is required:  python -m pip install UnityPy")

# ItemDrop.ItemData.ItemType in the game's assembly.
TYPE_NAMES = {
    0: "none", 1: "material", 2: "consumable", 3: "one-handed weapon", 4: "bow", 5: "shield",
    6: "helmet", 7: "chest armor", 9: "ammo", 10: "customization", 11: "leg armor", 12: "hands",
    13: "trophy", 14: "two-handed weapon", 15: "torch", 16: "misc", 17: "cape", 18: "utility",
    19: "tool", 20: "atgeir attachment", 21: "fish", 22: "two-handed weapon (left)",
    23: "ammo (non-equipable)", 24: "trinket",
}


def find_game(arg=None):
    if arg and os.path.isdir(os.path.join(arg, "valheim_Data")):
        return arg
    roots = []
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
                roots.append(winreg.QueryValueEx(k, "SteamPath")[0])
        except OSError:
            pass
        roots += [r"C:\Program Files (x86)\Steam", r"C:\Program Files\Steam"]
    else:
        roots += [os.path.expanduser("~/.steam/steam"), os.path.expanduser("~/.local/share/Steam")]
    for root in roots:
        vdf = os.path.join(root, "steamapps", "libraryfolders.vdf")
        if not os.path.exists(vdf):
            continue
        for line in open(vdf, encoding="utf-8", errors="replace"):
            line = line.strip()
            if line.startswith('"path"'):
                lib = line.split('"')[3].replace("\\\\", "\\")
                cand = os.path.join(lib, "steamapps", "common", "Valheim")
                if os.path.isdir(os.path.join(cand, "valheim_Data")):
                    return cand
    sys.exit("Valheim install not found; pass its folder as the first argument")


def read_localization(data_dir):
    env = UnityPy.load(os.path.join(data_dir, "resources.assets"))
    tables = {}
    for o in env.objects:
        if o.type.name != "TextAsset":
            continue
        ta = o.read()
        if not ta.m_Name.startswith("localization"):
            continue
        text = ta.m_Script if isinstance(ta.m_Script, str) else ta.m_Script.decode("utf-8", "replace")
        rows = list(csv.reader(io.StringIO(text.lstrip("\ufeff"))))
        if not rows or "English" not in rows[0]:
            continue
        col = rows[0].index("English")
        tables[ta.m_Name] = {r[0]: r[col] for r in rows[1:] if len(r) > col and r[0]}
    # The base table first, then the update tables override it, as the game does.
    strings = dict(tables.pop("localization", {}))
    for name in sorted(tables):
        strings.update(tables[name])
    return strings


def read_items(data_dir):
    env = UnityPy.load(os.path.join(data_dir, "StreamingAssets", "SoftRef", "Bundles"),
                       os.path.join(data_dir, "globalgamemanagers.assets"))
    found = {}
    for o in env.objects:
        if o.type.name != "MonoBehaviour":
            continue
        try:
            mb = o.read()
            script = mb.m_Script.read() if mb.m_Script else None
            if not script or script.m_ClassName != "ItemDrop":
                continue
            name = mb.m_GameObject.read().m_Name
            if name not in itemdb.ITEM_NAME_TO_HASH or name in found:
                continue
            sh = o.read_typetree()["m_itemData"]["m_shared"]
        except Exception:
            continue
        found[name] = {
            "token": sh.get("m_name", ""),
            "type": int(sh.get("m_itemType", 0)),
            "stack": int(sh.get("m_maxStackSize", 1)),
            "durability": float(sh.get("m_maxDurability", 100.0)),
            "per_level": float(sh.get("m_durabilityPerLevel", 0.0)),
            "max_quality": int(sh.get("m_maxQuality", 1)),
            "use_durability": bool(sh.get("m_useDurability", False)),
        }
    return found


def main():
    game = find_game(sys.argv[1] if len(sys.argv) > 1 else None)
    data_dir = os.path.join(game, "valheim_Data")
    print("game:", game)
    strings = read_localization(data_dir)
    print("English strings:", len(strings))
    items = read_items(data_dir)
    print("item prefabs with data:", len(items), "of", len(itemdb.ITEM_NAME_TO_HASH), "known prefab names")

    missing_name = 0
    lines = []
    for name in sorted(items):
        d = items[name]
        token = d["token"].lstrip("$")
        display = strings.get(token, "")
        if not display:
            missing_name += 1
        lines.append("    %r: (%r, %d, %d, %s, %s, %d, %s)," % (
            name, display, d["type"], d["stack"], repr(round(d["durability"], 2)),
            repr(round(d["per_level"], 2)), d["max_quality"], d["use_durability"]))
    types = collections.Counter(d["type"] for d in items.values())
    print("prefabs without an English name:", missing_name)
    print("types:", {TYPE_NAMES.get(t, t): n for t, n in types.most_common()})

    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vse", "itemdata.py")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write('"""Item data read from the game files. Generated by tools/generate_itemdata.py on %s.\n\n'
                'ITEM_DATA[prefab] = (display name, item type, max stack, max durability at quality 1,\n'
                '                     durability per quality level, max quality, uses durability)\n'
                'Do not edit by hand; rerun the generator after a game update.\n"""\n\n'
                % datetime.date.today().isoformat())
        f.write("TYPE_NAMES = {\n")
        for t in sorted(TYPE_NAMES):
            f.write("    %d: %r,\n" % (t, TYPE_NAMES[t]))
        f.write("}\n\nITEM_DATA = {\n")
        f.write("\n".join(lines))
        f.write("\n}\n")
    print("wrote", out, "(%d entries)" % len(lines))


if __name__ == "__main__":
    main()
