"""Editing operations and the safety rails around saving."""
import ctypes
import datetime
import os
import shutil
import sys

from . import fch
from . import items as itemdb


class SaveBlocked(Exception):
    pass


# -- process check --------------------------------------------------------

def is_process_running(exe_name):
    """True if a process with that image name is running (Windows only; False elsewhere)."""
    if sys.platform != "win32":
        return False
    exe_name = exe_name.lower()
    try:
        psapi = ctypes.windll.psapi
        k32 = ctypes.windll.kernel32
        k32.OpenProcess.restype = ctypes.c_void_p
        k32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        k32.QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_wchar_p,
                                                   ctypes.POINTER(ctypes.c_uint32)]
        k32.CloseHandle.argtypes = [ctypes.c_void_p]
        pids = (ctypes.c_uint32 * 16384)()
        needed = ctypes.c_uint32()
        if not psapi.EnumProcesses(pids, ctypes.sizeof(pids), ctypes.byref(needed)):
            return False
        buf = ctypes.create_unicode_buffer(1024)
        for pid in pids[:needed.value // 4]:
            h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            if not h:
                continue
            size = ctypes.c_uint32(1024)
            ok = k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
            k32.CloseHandle(h)
            if ok and os.path.basename(buf.value).lower() == exe_name:
                return True
    except Exception:
        return False
    return False


def is_valheim_running():
    return is_process_running("valheim.exe")


# -- backups ---------------------------------------------------------------

def make_backup(path, backup_dir):
    os.makedirs(backup_dir, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    base = os.path.basename(path)
    target = os.path.join(backup_dir, "%s.%s.bak" % (base, stamp))
    n = 2
    while os.path.exists(target):
        target = os.path.join(backup_dir, "%s.%s-%d.bak" % (base, stamp, n))
        n += 1
    shutil.copy2(path, target)
    return target


def list_backups(path, backup_dir):
    base = os.path.basename(path)
    if not os.path.isdir(backup_dir):
        return []
    out = [os.path.join(backup_dir, n) for n in os.listdir(backup_dir)
           if n.startswith(base + ".") and n.endswith(".bak")]
    return sorted(out, reverse=True)


# -- saving ----------------------------------------------------------------

def describe_changes(cf):
    """Human-readable lines describing how cf differs from the bytes it was loaded from."""
    orig = fch.CharacterFile(cf.original)
    out = []
    if bool(orig.used_cheats) != bool(cf.used_cheats):
        out.append("Cheat flag: %s -> %s" % ("SET" if orig.used_cheats else "clear",
                                             "SET" if cf.used_cheats else "clear"))
    if not cf.has_data:
        return out
    a = {(i.x, i.y): i for i in orig.items}
    b = {(i.x, i.y): i for i in cf.items}
    for slot in sorted(set(a) | set(b), key=lambda s: (s[1], s[0])):
        ia, ib = a.get(slot), b.get(slot)
        where = "%d,%d" % slot
        if ia is None:
            by = " crafted by %s" % ib.crafter_name if ib.crafter_name else ""
            out.append("+ %s x%d at %s%s" % (item_name(ib), ib.stack, where, by))
        elif ib is None:
            out.append("- %s x%d from %s" % (item_name(ia), ia.stack, where))
        elif ia.prefab != ib.prefab:
            out.append("%s: %s -> %s" % (where, item_name(ia), item_name(ib)))
        else:
            ch = []
            if ia.stack != ib.stack:
                ch.append("stack %d -> %d" % (ia.stack, ib.stack))
            if ia.quality != ib.quality:
                ch.append("quality %d -> %d" % (ia.quality, ib.quality))
            if ia.durability != ib.durability:
                ch.append("durability %.1f -> %.1f" % (ia.durability_value, ib.durability_value))
            if ia.cheated != ib.cheated:
                ch.append("mark cleared" if ia.cheated else "MARKED as cheated")
            if ia.crafter_name != ib.crafter_name:
                ch.append("crafter %r -> %r" % (ia.crafter_name, ib.crafter_name))
            if ch:
                out.append("%s at %s: %s" % (item_name(ia), where, ", ".join(ch)))
    sa = {s.type: s for s in orig.skills}
    sb = {s.type: s for s in cf.skills}
    for t in sorted(set(sa) | set(sb)):
        name = fch.SKILLS.get(t, "Skill %d" % t)
        if t not in sa:
            out.append("+ skill %s at %.1f" % (name, sb[t].level))
        elif t not in sb:
            out.append("- skill %s (was %.1f)" % (name, sa[t].level))
        elif sa[t].level != sb[t].level or sa[t].acc != sb[t].acc:
            out.append("%s: %.1f -> %.1f" % (name, sa[t].level, sb[t].level))
    return out


def _append_history(backup_dir, path, backup, changes):
    try:
        os.makedirs(backup_dir, exist_ok=True)
        log = os.path.join(os.path.dirname(backup_dir), "history.log")
        with open(log, "a", encoding="utf-8") as f:
            f.write("%s  %s\n    backup: %s\n" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                                   path, backup))
            for line in changes:
                f.write("    %s\n" % line)
    except OSError:
        pass


def save(cf, path, backup_dir):
    """Back up, rebuild, verify, then replace the file atomically. Returns the backup path."""
    if is_valheim_running():
        raise SaveBlocked("Valheim is running. Close the game completely, then save again.")
    if not cf.editable:
        raise SaveBlocked("This file did not pass the round-trip check, so editing it is disabled "
                          "to avoid corrupting it.")
    data = cf.to_bytes()
    if not fch.CharacterFile.verify(data):
        raise SaveBlocked("internal error: the rebuilt file failed its own checksum")
    fch.CharacterFile(data)  # must re-parse cleanly
    changes = describe_changes(cf)
    backup = make_backup(path, backup_dir)
    tmp = path + ".vse-tmp"
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    _append_history(backup_dir, path, backup, changes or ["(checksum repaired, no content changes)"])
    return backup


def restore(cf_path, backup_path):
    if is_valheim_running():
        raise SaveBlocked("Valheim is running. Close the game completely first.")
    with open(backup_path, "rb") as f:
        data = f.read()
    if not fch.CharacterFile.verify(data):
        raise SaveBlocked("That backup fails the checksum and would not load in the game.")
    fch.CharacterFile(data)
    shutil.copy2(backup_path, cf_path)


# -- inventory ---------------------------------------------------------------

_NAME_LOWER = {n.lower(): n for n in itemdb.ITEM_NAME_TO_HASH}


def item_name(it):
    return itemdb.ITEM_HASH_TO_NAME.get(it.prefab, "hash %d" % it.prefab)


def resolve_item(text):
    """Prefab name (any case) or numeric hash -> (canonical name, hash)."""
    t = (text or "").strip()
    if not t:
        raise ValueError("No item name given.")
    name = _NAME_LOWER.get(t.lower())
    if name is not None:
        return name, itemdb.ITEM_NAME_TO_HASH[name]
    try:
        h = int(t)
    except ValueError:
        raise ValueError("Unknown item name: %r" % t)
    if h not in itemdb.ITEM_HASH_TO_NAME:
        raise ValueError("Unknown item hash: %d" % h)
    return itemdb.ITEM_HASH_TO_NAME[h], h


def _check_values(stack, quality, durability):
    if int(stack) < 1 or int(quality) < 1:
        raise ValueError("Stack and quality must be 1 or more.")
    if float(durability) < 0:
        raise ValueError("Durability cannot be negative.")


def add_item(cf, name, x, y, stack=1, quality=1, durability=100.0, crafted_by_character=True):
    if not cf.has_data:
        raise ValueError("This character has no player data yet (it has never entered a world), "
                         "so it has no inventory to edit.")
    _, prefab = resolve_item(name)
    _check_values(stack, quality, durability)
    if not (0 <= x < fch.INVENTORY_W and 0 <= y < fch.INVENTORY_H):
        raise ValueError("slot out of range")
    if cf.item_at(x, y) is not None:
        raise ValueError("slot (%d,%d) is occupied" % (x, y))
    if crafted_by_character:
        it = fch.Item.new(prefab, x, y, stack, quality, durability, cf.player_id, cf.name)
    else:
        it = fch.Item.new(prefab, x, y, stack, quality, durability)
    cf.items.append(it)
    return it


def update_item(it, stack=None, quality=None, durability=None):
    """Change stack, quality and/or durability (game value) of an existing item."""
    stack = it.stack if stack is None else int(stack)
    quality = it.quality if quality is None else int(quality)
    durability = it.durability_value if durability is None else float(durability)
    _check_values(stack, quality, durability)
    it.stack, it.quality = stack, quality
    it.durability = int(round(durability * 100))
    it.refresh_flags()
    return it


def remove_item(cf, it):
    cf.items.remove(it)


def clear_marks(cf):
    n = 0
    for it in cf.items:
        if it.cheated:
            it.cheated = False
            n += 1
    return n


# -- skills ------------------------------------------------------------------

def set_skill(cf, stype, level, acc=None):
    if not cf.has_data:
        raise ValueError("This character has no player data yet, so it has no skills to edit.")
    stype = int(stype)
    if stype not in fch.SKILLS:
        raise ValueError("Unknown skill type %d" % stype)
    level = max(0.0, min(100.0, float(level)))
    for s in cf.skills:
        if s.type == stype:
            s.level = level
            if acc is not None:
                s.acc = max(0.0, float(acc))
            return s
    s = fch.Skill(stype, level, acc or 0.0)
    cf.skills.append(s)
    return s


def remove_skill(cf, stype):
    cf.skills = [s for s in cf.skills if s.type != stype]
