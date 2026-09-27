#!/usr/bin/env python3
"""Regenerate vse/guidedata.py from an installed copy of Valheim.

Developer tool, not needed to run the editor. Requires:  pip install UnityPy

    python tools/generate_guidedata.py [path/to/Valheim]

Reads, from the game's asset bundles: every crafting recipe (ingredients, station, station
level), the cooking, smelting and fermenting conversions, the food values, the "$item_"
name tokens the character file uses in its known-materials and known-recipes lists, the
teleportable flag, and the build costs of every crafting station and station extension.
The Guide tab turns this into per-biome lists; the biome split and the notes live in
vse/guide.py and are written by hand.
"""
import datetime
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vse import items as itemdb  # noqa: E402
from generate_itemdata import find_game, read_localization  # noqa: E402

try:
    import UnityPy
except ImportError:
    sys.exit("UnityPy is required:  python -m pip install UnityPy")

# Pieces that are not crafting stations but belong in a base-building checklist.
EXTRA_PIECES = ("portal_wood", "piece_sapcollector", "piece_wisplure", "piece_beehive", "bed", "piece_bed02",
                "piece_chest_wood", "piece_chest", "piece_chest_blackmetal", "guard_stone", "piece_cartographytable",
                "windmill", "piece_spinningwheel", "smelter", "blastfurnace", "charcoal_kiln", "fermenter",
                "piece_oven", "piece_cookingstation", "piece_cookingstation_iron", "piece_MeadCauldron")


_INSTANCE = re.compile(r" \(\d+\)$")   # Unity names scene copies "smelter (1)"


def go_name(pptr):
    return _INSTANCE.sub("", pptr.read().m_GameObject.read().m_Name)


def read_all(data_dir):
    env = UnityPy.load(os.path.join(data_dir, "StreamingAssets", "SoftRef", "Bundles"),
                       os.path.join(data_dir, "globalgamemanagers.assets"))
    items, recipes, pieces, extensions = {}, {}, {}, {}
    alternatives = {}   # item -> further recipes for it (a second Recipe asset, or another conversion)
    conversions = []
    for o in env.objects:
        if o.type.name != "MonoBehaviour":
            continue
        try:
            mb = o.read()
            script = mb.m_Script.read() if mb.m_Script else None
            if not script:
                continue
            cls = script.m_ClassName
            if cls == "ItemDrop":
                name = mb.m_GameObject.read().m_Name
                # Feasts are placed, not carried, and fish are their own prefabs: neither is in the
                # inventory item table, but feasts have food values and fish are ingredients.
                if (name not in itemdb.ITEM_NAME_TO_HASH and not name.startswith(("Feast", "Fish"))) or name in items:
                    continue
                sh = o.read_typetree()["m_itemData"]["m_shared"]
                items[name] = {"token": sh.get("m_name", ""), "teleportable": bool(sh.get("m_teleportable", True)),
                               "food": (float(sh.get("m_food", 0)), float(sh.get("m_foodStamina", 0)),
                                        float(sh.get("m_foodEitr", 0)), float(sh.get("m_foodBurnTime", 0)))}
            elif cls == "Recipe":
                tt = o.read_typetree()
                if not tt.get("m_enabled", True) or not mb.m_item:
                    continue
                item = go_name(mb.m_item)
                # Skip upgrade-only costs (amount 0, only a per-level amount) and the Forge of
                # Potential's refinement idol (m_upgraderResource); neither is needed to craft.
                res = [(go_name(mb.m_resources[i].m_resItem), int(r.get("m_amount", 0)))
                       for i, r in enumerate(tt.get("m_resources", []))
                       if int(r.get("m_amount", 0)) > 0 and not r.get("m_upgraderResource", 0)]
                station = go_name(mb.m_craftingStation) if mb.m_craftingStation else ""
                rec = (station, int(tt.get("m_minStationLevel", 1)), int(tt.get("m_amount", 1)), tuple(res))
                if item not in recipes:
                    recipes[item] = rec
                elif rec != recipes[item] and rec not in alternatives.get(item, []):
                    alternatives.setdefault(item, []).append(rec)
            elif cls in ("CookingStation", "Smelter", "Fermenter"):
                station = _INSTANCE.sub("", mb.m_GameObject.read().m_Name)
                fuel = None  # smelters burn something per product: coal, or sap in the eitr refinery
                if cls == "Smelter" and mb.m_fuelItem:
                    try:
                        fuel = (go_name(mb.m_fuelItem), max(1, int(o.read_typetree().get("m_fuelPerProduct", 1))))
                    except Exception:
                        fuel = None
                for c in mb.m_conversion:
                    try:
                        frm, to = go_name(c.m_from), go_name(c.m_to)
                    except Exception:
                        continue
                    n = int(getattr(c, "m_producedItems", 1) or 1)
                    conversions.append((to, station, n, ((frm, 1),) + ((fuel,) if fuel else ())))
            elif cls == "Piece":
                name = mb.m_GameObject.read().m_Name
                if name in pieces:
                    continue
                tt = o.read_typetree()
                res = [(go_name(mb.m_resources[i].m_resItem), int(r.get("m_amount", 0)))
                       for i, r in enumerate(tt.get("m_resources", [])) if int(r.get("m_amount", 0)) > 0]
                station = go_name(mb.m_craftingStation) if mb.m_craftingStation else ""
                pieces[name] = (tt.get("m_name", ""), station, tuple(res))
            elif cls == "StationExtension":
                name = mb.m_GameObject.read().m_Name
                if mb.m_craftingStation:
                    extensions[name] = go_name(mb.m_craftingStation)
        except Exception:
            continue
    return items, recipes, alternatives, pieces, extensions, conversions


def main():
    game = find_game(sys.argv[1] if len(sys.argv) > 1 else None)
    data_dir = os.path.join(game, "valheim_Data")
    print("game:", game)
    strings = read_localization(data_dir)
    items, recipes, alternatives, pieces, extensions, conversions = read_all(data_dir)
    print("items %d, recipes %d, pieces %d, extensions %d, conversions %d"
          % (len(items), len(recipes), len(pieces), len(extensions), len(conversions)))

    # Cooking, smelting and fermenting are recipes too: one input, produced at that piece.
    # The same metal can come from ore or scrap; the extra ways are kept as alternatives.
    for to, station, n, res in conversions:
        if to not in items:
            continue
        rec = (station, 1, n, res)
        if to not in recipes:
            recipes[to] = rec
        elif rec != recipes[to] and rec not in alternatives.get(to, []):
            alternatives.setdefault(to, []).append(rec)

    stations = {st for st, _, _, _ in recipes.values() if st} | set(extensions.values())
    wanted = stations | set(extensions) | set(EXTRA_PIECES)
    unknown_ingredients = sorted({ing for r in recipes.values() for ing, _ in r[3] if ing not in items})
    print("stations:", sorted(stations))
    print("pieces missing:", sorted(p for p in wanted if p not in pieces))
    print("recipe ingredients that are not items:", unknown_ingredients)

    def name_of(token):
        return strings.get(token.lstrip("$"), "")

    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "vse", "guidedata.py")
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write('"""Recipes, foods, stations. Generated by tools/generate_guidedata.py on %s.\n\n'
                'TOKENS[prefab] = the "$item_..." name the character file stores in its known lists\n'
                'NAMES[prefab] = English name for prefabs outside vse/itemdata.py (fish, feasts)\n'
                'NO_PORTAL = prefabs that cannot go through a portal\n'
                'FOODS[prefab] = (health, stamina, eitr, minutes)\n'
                'RECIPES[prefab] = (station prefab or "", station level, amount made, ((ingredient prefab, n), ...))\n'
                'ALTERNATIVES[prefab] = [more recipes in the same shape] where the game offers another way\n'
                'PIECES[prefab] = (name, "$piece_..." token, station needed to build it or "", ((ingredient, n), ...),\n'
                '                  station it extends or "")\n'
                'Do not edit by hand; rerun the generator after a game update.\n"""\n\n'
                % datetime.date.today().isoformat())
        f.write("TOKENS = {\n")
        for n in sorted(items):
            f.write("    %r: %r,\n" % (n, items[n]["token"]))
        f.write("}\n\nNAMES = {   # English names of the prefabs vse/itemdata.py does not cover\n")
        for n in sorted(items):
            if n not in itemdb.ITEM_NAME_TO_HASH and name_of(items[n]["token"]):
                f.write("    %r: %r,\n" % (n, name_of(items[n]["token"])))
        f.write("}\n\nNO_PORTAL = frozenset([\n")
        for n in sorted(items):
            if not items[n]["teleportable"]:
                f.write("    %r,\n" % n)
        f.write("])\n\nFOODS = {\n")
        for n in sorted(items):
            hp, st, ei, t = items[n]["food"]
            if hp > 0 or ei > 0:
                f.write("    %r: (%d, %d, %d, %d),\n" % (n, round(hp), round(st), round(ei), round(t / 60)))
        f.write("}\n\nRECIPES = {\n")
        for n in sorted(recipes):
            if n in items:
                f.write("    %r: %r,\n" % (n, recipes[n]))
        f.write("}\n\nALTERNATIVES = {\n")
        for n in sorted(alternatives):
            if n in items:
                f.write("    %r: %r,\n" % (n, alternatives[n]))
        f.write("}\n\nPIECES = {\n")
        for n in sorted(wanted):
            if n in pieces:
                token, station, res = pieces[n]
                f.write("    %r: (%r, %r, %r, %r, %r),\n"
                        % (n, name_of(token) or token, token, station, res, extensions.get(n, "")))
        f.write("}\n")
    print("wrote", out)


if __name__ == "__main__":
    main()
