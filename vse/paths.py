"""Where Valheim keeps character files, and where this tool keeps its own files."""
import glob
import os
import sys

VALHEIM_APPID = "892970"


def _steam_root():
    if sys.platform != "win32":
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
            path = winreg.QueryValueEx(k, "SteamPath")[0]
            if path and os.path.isdir(path):
                return os.path.normpath(path)
    except OSError:
        pass
    for p in (r"C:\Program Files (x86)\Steam", r"C:\Program Files\Steam"):
        if os.path.isdir(p):
            return p
    return None


def character_dirs():
    """Existing directories that may hold .fch files, tagged with a description."""
    found = []
    if sys.platform == "win32":
        base = os.path.join(os.environ.get("USERPROFILE", os.path.expanduser("~")),
                            "AppData", "LocalLow", "IronGate", "Valheim")
        steam_globs = []
        root = _steam_root()
        if root:
            steam_globs.append(os.path.join(root, "userdata", "*", VALHEIM_APPID, "remote", "characters"))
    else:
        base = os.path.join(os.path.expanduser("~"), ".config", "unity3d", "IronGate", "Valheim")
        steam_globs = [
            os.path.join(os.path.expanduser("~"), ".steam", "steam", "userdata", "*", VALHEIM_APPID, "remote", "characters"),
            os.path.join(os.path.expanduser("~"), ".local", "share", "Steam", "userdata", "*", VALHEIM_APPID, "remote", "characters"),
        ]
    for sub, label in (("characters", "Local"), ("characters_local", "Local")):
        d = os.path.join(base, sub)
        if os.path.isdir(d):
            found.append((d, label))
    for pattern in steam_globs:
        for d in sorted(glob.glob(pattern)):
            if os.path.isdir(d):
                found.append((d, "Steam Cloud"))
    return found


def find_characters(include_auto_backups=False):
    """Sorted list of (path, label) for every .fch in the known folders."""
    out = []
    for d, label in character_dirs():
        for name in sorted(os.listdir(d)):
            if not name.lower().endswith(".fch"):
                continue
            if not include_auto_backups and "_backup_auto-" in name:
                continue
            out.append((os.path.join(d, name), label))
    return out


def world_dirs():
    """Existing directories that hold world saves."""
    found = []
    if sys.platform == "win32":
        base = os.path.join(os.environ.get("USERPROFILE", os.path.expanduser("~")),
                            "AppData", "LocalLow", "IronGate", "Valheim")
        steam_globs = []
        root = _steam_root()
        if root:
            steam_globs.append(os.path.join(root, "userdata", "*", VALHEIM_APPID, "remote", "worlds"))
    else:
        base = os.path.join(os.path.expanduser("~"), ".config", "unity3d", "IronGate", "Valheim")
        steam_globs = [
            os.path.join(os.path.expanduser("~"), ".steam", "steam", "userdata", "*", VALHEIM_APPID, "remote", "worlds"),
            os.path.join(os.path.expanduser("~"), ".local", "share", "Steam", "userdata", "*", VALHEIM_APPID, "remote", "worlds"),
        ]
    for sub in ("worlds", "worlds_local"):
        d = os.path.join(base, sub)
        if os.path.isdir(d):
            found.append(d)
    for pattern in steam_globs:
        found.extend(d for d in sorted(glob.glob(pattern)) if os.path.isdir(d))
    return found


def world_files():
    """Header files of every world save found: 1.0 folders holding _main.N.fwl2, or legacy .fwl files."""
    out = []
    for d in world_dirs():
        for name in sorted(os.listdir(d)):
            p = os.path.join(d, name)
            if os.path.isdir(p):
                heads = glob.glob(os.path.join(p, "_main.*.fwl2"))
                if heads:
                    out.append(max(heads, key=lambda h: int(h.rsplit(".", 2)[-2]) if h.rsplit(".", 2)[-2].isdigit() else -1))
            elif name.lower().endswith(".fwl"):
                out.append(p)
    return out


def app_dir():
    """Folder for backups, the save history and the error log."""
    if sys.platform == "win32":
        root = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    else:
        root = os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(root, "ValheimSaveEditor")


def backup_dir():
    return os.path.join(app_dir(), "backups")


def history_log():
    return os.path.join(app_dir(), "history.log")


def error_log():
    return os.path.join(app_dir(), "error.log")
