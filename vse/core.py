"""Editing operations and the safety rails around saving."""
import ctypes
import datetime
import os
import shutil
import sys

from . import fch, search
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
    wa = {w.uid: w for w in orig.worlds}
    wb = {w.uid: w for w in cf.worlds}
    names = world_names()
    for uid in list(wa) + [u for u in wb if u not in wa]:
        label = world_label(uid, names)
        if uid not in wb:
            out.append("- world %s forgotten (map, position, bed spawn and death marker)" % label)
        elif uid not in wa:
            out.append("+ world %s" % label)
        else:
            a, b = wa[uid], wb[uid]
            ch = []
            if (a.map_data or b"") != (b.map_data or b""):
                ch.append("map cleared" if not b.map_data else "map changed")
            if (a.have_death, a.death) != (b.have_death, b.death):
                ch.append("death marker cleared" if not b.have_death else "death marker changed")
            if (a.have_logout, a.logout, a.have_spawn, a.spawn, a.home) != (b.have_logout, b.logout, b.have_spawn, b.spawn, b.home):
                ch.append("position data changed")
            if ch:
                out.append("world %s: %s" % (label, ", ".join(ch)))
    if not cf.has_data:
        return out
    if orig.inventory_rows != cf.inventory_rows:
        out.append("Inventory rows: %d -> %d" % (orig.inventory_rows, cf.inventory_rows))
    ua, ub = set(orig.uniques), set(cf.uniques)
    rows_key = fch.INV_ROWS_KEY + " "
    for key in [u for u in cf.uniques if u not in ua and not u.lower().startswith(rows_key)]:
        out.append("+ key %s" % unique_label(key))
    for key in [u for u in orig.uniques if u not in ub and not u.lower().startswith(rows_key)]:
        out.append("- key %s" % unique_label(key))
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
        hit = search.resolve(t)   # in-game name, any word order, if it is unambiguous
        if hit:
            return hit, itemdb.ITEM_NAME_TO_HASH[hit]
        raise ValueError("Unknown item name: %r" % t)
    if h not in itemdb.ITEM_HASH_TO_NAME:
        raise ValueError("Unknown item hash: %d" % h)
    return itemdb.ITEM_HASH_TO_NAME[h], h


def _check_values(prefab_name, stack, quality, durability):
    if int(stack) < 1 or int(quality) < 1:
        raise ValueError("Stack and quality must be 1 or more.")
    if float(durability) < 0:
        raise ValueError("Durability cannot be negative.")
    ms = search.max_stack(prefab_name)
    if ms and int(stack) > ms:
        raise ValueError("%s stacks to %d in the game, not %d." % (search.label(prefab_name), ms, int(stack)))
    mq = search.max_quality(prefab_name)
    if mq and int(quality) > mq:
        raise ValueError("%s goes up to quality %d in the game, not %d." % (search.label(prefab_name), mq, int(quality)))


def default_durability(prefab_name, quality=1):
    """What a freshly crafted item of that quality has: the game's maximum, or 100 if unknown."""
    md = search.max_durability(prefab_name, quality)
    return 100.0 if md is None else md


def add_item(cf, name, x, y, stack=1, quality=1, durability=None, crafted_by_character=True):
    """Add an item. durability=None means the game's maximum for that quality."""
    if not cf.has_data:
        raise ValueError("This character has no player data yet (it has never entered a world), "
                         "so it has no inventory to edit.")
    canonical, prefab = resolve_item(name)
    if durability is None:
        durability = default_durability(canonical, quality)
    _check_values(canonical, stack, quality, durability)
    if not (0 <= x < fch.INVENTORY_W and 0 <= y < cf.inventory_rows):
        raise ValueError("slot (%d,%d) is outside this character's inventory of %d rows"
                         % (x, y, cf.inventory_rows))
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
    _check_values(item_name(it), stack, quality, durability)
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


# -- giving a recipe's ingredients ---------------------------------------------

def free_slots(cf):
    """Empty slots: the main rows first, top to bottom and left to right, the hotbar last."""
    used = {(it.x, it.y) for it in cf.items}
    slots = [(x, y) for y in range(cf.inventory_rows) for x in range(fch.INVENTORY_W) if (x, y) not in used]
    return sorted(slots, key=lambda s: (s[1] == 0, s[1], s[0]))


def give_items(cf, needs, times=1):
    """Put `times` sets of needs ([(prefab, amount), ...]) into the inventory as materials (no
    crafter): existing unmarked stacks are topped up first, then empty slots are filled, split
    at the stack limit. Nothing changes unless it all fits. Returns (new items, [(item, added)])."""
    if not cf.has_data:
        raise ValueError("This character has no player data yet, so it has no inventory.")
    times = max(1, int(times))
    wanted = {}
    for prefab, amount in needs:
        name, _ = resolve_item(prefab)
        wanted[name] = wanted.get(name, 0) + int(amount) * times
    topups, new = [], []
    for name, left in wanted.items():
        limit = search.max_stack(name) or 1
        for it in cf.items:
            if left and item_name(it) == name and not it.cheated and it.stack < limit:
                add = min(limit - it.stack, left)
                topups.append((it, add))
                left -= add
        while left > 0:
            new.append((name, min(limit, left)))
            left -= min(limit, left)
    slots = free_slots(cf)
    if len(new) > len(slots):
        raise ValueError("That needs %d empty slot(s) and the inventory has %d. Make room first."
                         % (len(new), len(slots)))
    for it, add in topups:
        it.stack += add
        it.refresh_flags()
    added = [add_item(cf, name, x, y, stack=stack, crafted_by_character=False)
             for (name, stack), (x, y) in zip(new, slots)]
    return added, topups


# -- whole-inventory actions ---------------------------------------------------

REFILL_QUICK = ("food", "ammo")   # what "resupply" means: food, meads, arrows and bolts
NOT_REFILLED = ("Coins",)         # currency, not supplies


def refill_stacks(cf, categories=None):
    """Fill every stackable item up to the game's stack limit. categories: the search categories
    to include, or None for every stackable item (coins excepted). Returns the items changed."""
    changed = []
    for it in cf.items:
        name = item_name(it)
        ms = search.max_stack(name)
        if not ms or ms <= 1 or name in NOT_REFILLED:
            continue
        if categories and search.category(name) not in categories:
            continue
        if it.stack < ms:
            it.stack = ms
            it.refresh_flags()
            changed.append(it)
    return changed


def repair_all(cf):
    """Raise every worn item to the game's maximum durability for its quality. Never lowers one:
    the game can store more than the table says (crafting-skill bonus). Returns the items changed."""
    changed = []
    for it in cf.items:
        name = item_name(it)
        if not search.uses_durability(name):
            continue
        target = int(round(search.max_durability(name, it.quality) * 100))
        if it.durability < target:
            it.durability = target
            changed.append(it)
    return changed


# -- inventory size ------------------------------------------------------------

# Haldor sells two inventory upgrades. Buying one adds its "buy key" to the character's uniques
# (so he stops offering it) and raises the "invrows" value by one (StoreGui.BuySelectedItem).
POCKETS = {
    1: ("invslot1", "Wider Pockets", "sold by Haldor after Moder"),
    2: ("invslot2", "Deeper Pockets", "sold by Haldor after the Queen"),
}


def unique_label(key):
    """A readable name for a player key, for the change list."""
    for k, name, where in POCKETS.values():
        if key == k:
            return "%s (%s)" % (name, where)
    return key


def set_inventory_rows(cf, rows):
    """Set the number of inventory rows (the game's 'invrows' key)."""
    if not cf.has_data:
        raise ValueError("This character has no player data yet, so it has no inventory.")
    rows = int(rows)
    if not (fch.INVENTORY_H <= rows <= fch.INVENTORY_MAX_H):
        raise ValueError("Rows must be between %d and %d; the game allows no more." % (fch.INVENTORY_H, fch.INVENTORY_MAX_H))
    below = [it for it in cf.items if it.y >= rows]
    if below:
        raise ValueError("%d item(s) sit in the rows being removed (%s). Move or remove them first; the game "
                         "would drop them on the ground." % (len(below), ", ".join(item_name(it) for it in below[:6])))
    cf.inventory_rows = rows
    return rows


def set_pocket(cf, n, bought):
    """Mirror buying (or handing back) a pocket upgrade: the buy key plus one row."""
    key = POCKETS[n][0]
    if bool(bought) == cf.has_unique(key):
        return cf.inventory_rows
    if bought:
        set_inventory_rows(cf, min(fch.INVENTORY_MAX_H, cf.inventory_rows + 1))
        cf.add_unique(key)
    else:
        set_inventory_rows(cf, max(fch.INVENTORY_H, cf.inventory_rows - 1))
        cf.remove_unique(key)
    return cf.inventory_rows


# -- worlds ------------------------------------------------------------------

_WORLD_NAMES = None


def world_names(refresh=False):
    """{world uid: world name} for every world save found on this machine."""
    global _WORLD_NAMES
    if _WORLD_NAMES is None or refresh:
        from . import paths
        names = {}
        for p in paths.world_files():
            try:
                with open(p, "rb") as f:
                    head = fch.read_world_header(f.read(4096))
            except OSError:
                head = None
            if head:
                names[head[2]] = head[0]
        _WORLD_NAMES = names
    return _WORLD_NAMES


def world_label(uid, names=None):
    names = world_names() if names is None else names
    return names.get(uid) or "Unknown world (ID %d)" % uid


def _need_world(cf, uid):
    w = cf.world(int(uid))
    if w is None:
        raise ValueError("this character has no data for world ID %d" % int(uid))
    return w


def forget_world(cf, uid):
    """Drop the character's block for that world: map, position, bed spawn and death marker."""
    _need_world(cf, uid)
    cf.worlds = [w for w in cf.worlds if w.uid != int(uid)]


def clear_world_map(cf, uid):
    _need_world(cf, uid).map_data = None


def clear_death_marker(cf, uid):
    w = _need_world(cf, uid)
    w.have_death = 0
    w.death = fch.WorldEntry.ZERO


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
