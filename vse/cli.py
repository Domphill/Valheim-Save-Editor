"""Command-line interface, for machines without a desktop or for scripting.

    python -m vse dump  <file.fch>
    python -m vse clear <file.fch> [--flag] [--marks]          (default: both)
    python -m vse skill <file.fch> Swords=55 Run=40 ...
    python -m vse add   <file.fch> --slot X,Y Item [--stack N] [--quality N] [--durability F] [--no-crafter]

Every write goes through the same backup/verify/replace pipeline as the GUI.
"""
import argparse
import sys

from . import __version__, core, fch, paths


def _load(path):
    cf = fch.CharacterFile.load(path)
    if not cf.hash_ok:
        print("warning: checksum mismatch; saving will repair it", file=sys.stderr)
    return cf


def cmd_dump(a):
    cf = _load(a.file)
    print("Character : %s (ID %d)" % (cf.name, cf.player_id))
    print("Cheat flag: %s" % ("SET" if cf.used_cheats else "clear"))
    print("Checksum  : %s    Round-trip: %s" % ("OK" if cf.hash_ok else "MISMATCH",
                                                "OK" if cf.editable else "FAILED (read only)"))
    if not cf.has_data:
        print("No player data (the character has never entered a world).")
        return 0
    print("Inventory (%d items, %d marked):" % (len(cf.items), len(cf.marked_items)))
    for it in sorted(cf.items, key=lambda i: (i.y, i.x)):
        flags = []
        if it.cheated:
            flags.append("MARKED")
        if it.equipped:
            flags.append("equipped")
        print("   [%d,%d] %-26s x%-4d q%d dur %-8.1f crafter=%-12s %s"
              % (it.x, it.y, core.item_name(it), it.stack, it.quality, it.durability_value,
                 it.crafter_name or "-", " ".join(flags)))
    print("Skills (%d):" % len(cf.skills))
    for s in sorted(cf.skills, key=lambda s: -s.level):
        print("   %-16s %5.1f" % (s.name, s.level))
    return 0


def _save(cf, path):
    changes = core.describe_changes(cf)
    if not changes and cf.hash_ok:
        print("nothing to save")
        return
    for line in changes:
        print("  " + line)
    backup = core.save(cf, path, paths.backup_dir())
    print("saved %s" % path)
    print("backup %s" % backup)


def cmd_clear(a):
    cf = _load(a.file)
    do_flag = a.flag or not (a.flag or a.marks)
    do_marks = a.marks or not (a.flag or a.marks)
    if do_flag:
        print("cheat flag: %s -> clear" % ("SET" if cf.used_cheats else "clear"))
        cf.used_cheats = 0
    if do_marks:
        print("item marks cleared: %d" % core.clear_marks(cf))
    _save(cf, a.file)
    return 0


def cmd_skill(a):
    cf = _load(a.file)
    by_lower = {n.lower(): t for t, n in fch.SKILLS.items()}
    for spec in a.skills:
        name, _, level = spec.partition("=")
        stype = by_lower.get(name.strip().lower())
        if stype is None or not level:
            print("bad skill spec %r; use Name=Level with one of: %s"
                  % (spec, ", ".join(sorted(fch.SKILL_TYPES))), file=sys.stderr)
            return 2
        s = core.set_skill(cf, stype, float(level))
        print("%s -> %.1f" % (s.name, s.level))
    _save(cf, a.file)
    return 0


def cmd_add(a):
    cf = _load(a.file)
    x, y = (int(v) for v in a.slot.split(","))
    it = core.add_item(cf, a.item, x, y, a.stack, a.quality, a.durability, crafted_by_character=not a.no_crafter)
    print("added %s x%d at %d,%d%s" % (core.item_name(it), it.stack, x, y,
                                        "" if a.no_crafter else " crafted by %s" % cf.name))
    _save(cf, a.file)
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m vse", description="Valheim Save Editor %s" % __version__)
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("dump", help="show character, inventory and skills")
    d.add_argument("file")
    d.set_defaults(fn=cmd_dump)
    c = sub.add_parser("clear", help="clear the cheat flag and/or item marks")
    c.add_argument("file")
    c.add_argument("--flag", action="store_true", help="clear only the cheat flag")
    c.add_argument("--marks", action="store_true", help="clear only the item marks")
    c.set_defaults(fn=cmd_clear)
    s = sub.add_parser("skill", help="set skill levels, e.g. Swords=55")
    s.add_argument("file")
    s.add_argument("skills", nargs="+", metavar="Name=Level")
    s.set_defaults(fn=cmd_skill)
    ad = sub.add_parser("add", help="add an item to an empty slot")
    ad.add_argument("file")
    ad.add_argument("item", help="prefab name, e.g. ArrowIron")
    ad.add_argument("--slot", required=True, metavar="X,Y", help="0-7,0-3; row 0 is the hotbar")
    ad.add_argument("--stack", type=int, default=1)
    ad.add_argument("--quality", type=int, default=1)
    ad.add_argument("--durability", type=float, default=100.0)
    ad.add_argument("--no-crafter", action="store_true", help="no 'Crafted by' line (raw materials)")
    ad.set_defaults(fn=cmd_add)
    a = p.parse_args(argv)
    try:
        return a.fn(a)
    except (fch.FchError, core.SaveBlocked, ValueError, OSError) as e:
        print("error: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
