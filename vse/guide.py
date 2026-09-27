"""What to aim for in each biome, ticked against a character file.

The recipes, foods and station costs come from vse/guidedata.py, generated from the game
files. This module adds the part a program cannot read from the game: which biome each raw
material belongs to (a crafted item belongs to the biome of its highest ingredient), the
bosses, and short hand-written notes.
"""
import collections

from . import guidedata as gd
from . import itemdata, search
from . import items as itemdb

Biome = collections.namedtuple("Biome", "tier name boss boss_trophy gp_key offering notes")

BIOMES = [
    Biome(1, "Meadows", "Eikthyr", "TrophyEikthyr", "GP_Eikthyr", "2 Deer Trophies at the altar",
          "Flint lies on the shoreline, boars and deer give hides, and Queen Bees hide in ruined "
          "houses. The runestone by the start stone marks Eikthyr's altar. Aim for a bow, the flint "
          "axe, leather armor and a bed under a roof before crossing into the Black Forest."),
    Biome(2, "Black Forest", "The Elder", "TrophyTheElder", "GP_TheElder", "3 Ancient Seeds at the altar",
          "Copper is the green-veined rock, tin lies along the water; both smelt with surtling cores "
          "from burial chambers, which also hold the runestone for the Elder. Birch and oak need a "
          "bronze axe and give fine wood for the bow, the karve and portals. Trolls hit hard but "
          "slowly; troll hide makes the stealth set. Plant carrots with the cultivator."),
    Biome(3, "Swamp", "Bonemass", "TrophyBonemass", "GP_Bonemass", "10 Withered Bones at the altar",
          "Iron comes as scrap from the muddy piles inside sunken crypts (the Elder's swamp key) and "
          "as bog iron ore lying in the mud. "
          "Everything here is wet, dark and poisonous: brew poison resistance mead, bring a torch or "
          "the Dverger circlet, and fight draugr from the walkways. Guck from the glowing trees, "
          "ancient bark from the tall trees, turnip seeds from the flowers. The Bog Witch trades here."),
    Biome(4, "Mountain", "Moder", "TrophyDragonQueen", "GP_Moder", "3 Dragon Eggs at the altar",
          "Frost resistance mead until the wolf cape is made. The Wishbone from Bonemass finds silver "
          "veins; obsidian is on the surface, crystal drops from stone golems, dragon eggs sit in "
          "nests. Wolves hunt in packs at night and drakes spit frost. Frost caves hold cultists and "
          "the fenris set. Onion seeds are in the chests."),
    Biome(5, "Plains", "Yagluth", "TrophyGoblinKing", "GP_Yagluth", "5 Fuling Totems at the altar",
          "Deathsquitos kill careless newcomers; keep a shield up. Fulings drop black metal scrap and "
          "their villages have barley and flax, which only grow in the Plains. Lox give meat and pelts, "
          "tar pits give tar, cloudberries grow in the open. The artisan table (Moder's dragon tears) "
          "unlocks the windmill and spinning wheel for flour and linen."),
    Biome(6, "Mistlands", "The Queen", "TrophySeekerQueen", "GP_Queen", "the Sealbreaker (9 fragments) opens her lair",
          "The mist hides cliffs: build a wisp fountain from Yagluth's Torn Spirit, craft the Wisplight, "
          "and plant wisp torches at outposts. Black cores come from infested mines, which also hold "
          "soft tissue, royal jelly and Sealbreaker fragments. Sap needs an extractor from dvergr "
          "crates placed on the glowing Yggdrasil roots; refined eitr is soft tissue plus sap. Seeker "
          "soldiers are only soft from behind, ticks latch on, gjall drop them; Yagluth's power covers "
          "the fire. Dvergr are neutral and fight seekers for you. Haldor sells eggs and Wider Pockets."),
    Biome(7, "Ashlands", "Fader", "TrophyFader", "GP_Ashlands", "see the runestone at his altar",
          "The coast boils: sail in with the Drakkar. Flametal is mined from the lava pillars before "
          "they sink, grausten is the building stone, charred bone drops from the charred warriors. "
          "Fortresses must be sieged, and the Morgen comes at night. Everything hits hard; keep the "
          "Ashlands foods and fire resistance up."),
    Biome(8, "Deep North", "Kall Fimbulbringer", None, "GP_DeepNorth", "see the runestone at the altar",
          "Frostwood, moose, seals, kale, oats and lingonberries; the Frost Foundry is the new station "
          "and gold is cast in moulds. These lists come straight from the game files; treat them as "
          "the target inventory and read the runestones for the rest."),
]

# Which biome a raw material belongs to. Crafted items inherit the highest tier of their
# ingredients. Names are prefabs. 0 (absent) means "not placed"; the tests list those.
MATERIAL_TIER = {}
for _tier, _names in (
    (1, "Wood Stone Flint LeatherScraps DeerHide Resin Feathers BoneFragments Raspberry Mushroom Honey QueenBee "
        "Dandelion NeckTail HardAntler RawMeat DeerMeat BjornHide BjornMeat BjornPaw TrophyDeer TrophyBjorn FishRaw "
        "FishingBait Fish1 Fish2 Fish3 Fish5 Fish6 Fish7 Fish8 Fish10 Fish11 Fish12 Leatherstraps Upgrader0Armor Upgrader0Weapon"),
    (2, "Copper CopperOre Tin TinOre Bronze FineWood RoundLog TrollHide Coal SurtlingCore GreydwarfEye Carrot Blueberries "
        "Thistle AncientSeed MushroomYellow AmberPearl Ruby TrophyGreydwarfShaman TrophySkeleton TrophyFrostTroll "
        "TrophySurtling YmirRemains Chitin SerpentMeat SerpentScale TrophySerpent SpiceForests SpiceOceans "
        "Upgrader1Armor Upgrader1Weapon"),
    (3, "Iron IronOre IronScrap ElderBark Guck Bloodbag Entrails Ooze Chain Turnip WitheredBone Root WrithanRoots "
        "TrophyAbomination TrophyBlob TrophyLeech TrophyDraugrElite UndeadBjornRibcage TrophyBjornUndead SharpeningStone "
        "CuredSquirrelHamstring PowderedDragonEgg FragrantBundle BlobVial PungentPebbles FreshSeaweed "
        "Upgrader2Armor Upgrader2Weapon"),
    (4, "Silver SilverOre WolfPelt WolfFang WolfClaw WolfHairBundle WolfMeat TrophyWolf TrophyFenring TrophyCultist "
        "TrophyHatchling TrophySGolem FreezeGland Obsidian Crystal DragonTear Onion DragonEgg SpiceMountains Fish4_cave "
        "Upgrader3Armor Upgrader3Weapon"),
    (5, "BlackMetal BlackMetalScrap LoxMeat LoxPelt TrophyLox TrophyGoblin TrophyGoblinBrute TrophyGrowth Needle Barley "
        "Flax Cloudberry Tar YagluthDrop SpicePlains Upgrader4Armor Upgrader4Weapon"),
    (6, "YggdrasilWood BlackMarble BlackCore Softtissue Sap Carapace Mandible ScaleHide Bilebag RoyalJelly GiantBloodSack "
        "Wisp MushroomMagecap MushroomJotunPuffs HareMeat BugMeat ChickenEgg ChickenMeat QueenDrop DvergrNeedle "
        "DvergrKeyFragment TrophySeeker TrophyGjall SpiceMistlands Fish9 Upgrader5Armor Upgrader5Weapon"),
    (7, "FlametalNew FlametalOreNew Grausten Blackwood CharredBone MorgenSinew MorgenHeart TrophyMorgen AsksvinMeat AskHide "
        "AskBladder TrophyAsksvin VoltureMeat VoltureEgg Vineberry Fiddleheadfern MushroomSmokePuff MoltenCore "
        "ProustitePowder SulfurStone BonemawSerpentTooth BoneMawSerpentMeat GemstoneRed GemstoneGreen GemstoneBlue "
        "FaderEmber TrophyCharredMelee TrophyFallenValkyrie CelestialFeather MechanicalSpring CeramicPlate BellFragment "
        "DyrnwynBladeFragment DyrnwynHiltFragment DyrnwynTipFragment SpiceAshlands AxeBerzerkr MaceEldner SwordNiedhogg "
        "SpearSplitner CrossbowRipper BowAshlands THSwordSlayer Upgrader6Armor Upgrader6Weapon"),
    (8, "Frostwood MooseMeat MooseHide MooseSinew TrophyMoose SealBlubber SealHide Kale Oat OatSeeds Lingonberry Ice "
        "NornThread Gold GoldOre Poteitr FrostCore BarkaBranch MoleClaws ElakingHairBundle MushroomBzerker OrbFrostFire "
        "OrbThunderBlood ScytheHandle CrownJewel SpiceDeepNorth OozeMork TrophyBlob_Morkhalla TrophyJotunWitch "
        "TrophyJotunWarrior AtgeirGold AxeGold BattleaxeGold BowGold CrossbowGold FistGold KnifeGold MaceGold SledgeGold "
        "SpearGold SwordGold THSwordGold MoldArmorGoldChest MoldArmorGoldHelmet MoldArmorGoldLegs MoldArmorMageChest "
        "MoldArmorMageHelmet MoldArmorMageLegs MoldArmorMediumHelmet MoldArmorMediumLegs MoldArmormediumChest MoldAtgeir "
        "MoldAxe MoldAxe2H MoldBow MoldCrossbow MoldFistweapon MoldKeys MoldKnife MoldMace MoldMace2H MoldShieldBuckler "
        "MoldShieldRound MoldShieldTower MoldSpear MoldStaffOrbofAhri MoldStafffrostorbs MoldStaffspiritcaller "
        "MoldStaffthunderblood MoldSword MoldSword2H KeysGoldUncooked Upgrader7Armor Upgrader7Weapon"),
):
    for _n in _names.split():
        MATERIAL_TIER[_n] = _tier

# Item types (itemdata.TYPE_NAMES) grouped into the Guide's sections.
SECTION_TYPES = [
    ("Weapons and tools", (3, 4, 14, 22, 15, 19)),
    ("Shields", (5,)),
    ("Armor and capes", (6, 7, 11, 12, 17)),
    ("Accessories", (18, 24, 16)),
    ("Ammo", (9, 23)),
]

_tier_cache = {}


def tier(prefab, _seen=None):
    """Biome tier of an item: its own entry, else the lowest tier among the ways to make it,
    each way being as high as its highest ingredient."""
    if prefab in MATERIAL_TIER:
        return MATERIAL_TIER[prefab]
    if prefab in _tier_cache:
        return _tier_cache[prefab]
    if prefab not in gd.RECIPES:
        return 0
    _seen = _seen or set()
    if prefab in _seen:
        return 0
    _seen.add(prefab)
    ways = [max([tier(i, _seen) for i, _ in rec[3]] + [0]) for rec in _all_recipes(prefab)]
    ways = [w for w in ways if w] or [0]
    t = min(ways)
    _tier_cache[prefab] = t
    return t


def _all_recipes(prefab):
    return [gd.RECIPES[prefab]] + list(gd.ALTERNATIVES.get(prefab, ())) if prefab in gd.RECIPES else []


def recipes_for(prefab):
    """Every way to make it, the earliest-biome way first; ways using unplaced materials come last."""
    ways = _all_recipes(prefab)
    return sorted(ways, key=lambda rec: (max([tier(i) for i, _ in rec[3]] + [0]) or 99, ways.index(rec)))


def ingredients_tier(res):
    return max([tier(i) for i, _ in res] + [0])


def station_name(prefab):
    if not prefab:
        return "by hand"
    p = gd.PIECES.get(prefab)
    return p[0] if p else search.split_camel(prefab.replace("piece_", ""))


def label(prefab):
    """In-game name; falls back to the generated table for fish and feasts, then to the prefab."""
    if prefab in itemdata.ITEM_DATA:
        return search.label(prefab)
    return gd.NAMES.get(prefab) or search.split_camel(prefab)


def _res_text(res):
    return ", ".join("%d %s" % (n, label(i)) for i, n in res)


def _one_recipe_text(rec):
    station, level, amount, res = rec
    where = station_name(station) + (" level %d" % level if level > 1 else "")
    if len(res) == 1 and res[0][0] not in MATERIAL_TIER and res[0][0] in gd.RECIPES:
        inner = recipes_for(res[0][0])[0]
        where = station_name(inner[0]) + (" level %d" % inner[1] if inner[1] > 1 else "") + ", then " + station_name(station)
        res = inner[3]
    out = "%s @ %s" % (_res_text(res), where)
    if amount > 1:
        out += " (makes %d)" % amount
    return out


def recipe_text(prefab):
    """'1 Hare Meat, 3 Jotun Puffs, 2 Carrot @ Prep Table, then Oven' - follows one intermediate
    step, and lists the other ways the game offers (scrap or ore) after 'or'."""
    ways = recipes_for(prefab)
    if not ways:
        return ""
    best = ingredients_tier(ways[0][3])
    texts = [_one_recipe_text(ways[0])]
    for rec in ways[1:]:
        # Skip ways that need something with no biome (legacy items nothing drops).
        if best and not ingredients_tier(rec[3]):
            continue
        texts.append(_one_recipe_text(rec))
    return " · or ".join(texts)


def status(cf, prefab):
    """'in bag', 'can craft' (recipe known), 'seen' (material picked up before), or ''."""
    if cf is None or not cf.has_data:
        return ""
    if any(itemdb.ITEM_HASH_TO_NAME.get(it.prefab) == prefab for it in cf.items):
        return "in bag"
    tok = gd.TOKENS.get(prefab)
    if tok and tok in cf.known_recipes:
        return "can craft"
    if tok and tok in cf.known_materials:
        return "seen"
    return ""


def _biome_known(cf, name):
    key = name.replace(" ", "").lower()
    return any(b.replace(" ", "").lower() == key for b in cf.known_biomes)


def furthest_biome(cf):
    """Index into BIOMES of the furthest biome the character has set foot in (0 if none)."""
    if cf is None or not cf.has_data:
        return 0
    idx = 0
    for i, b in enumerate(BIOMES):
        if _biome_known(cf, b.name):
            idx = i
    return idx


def sections(biome, cf):
    """[(section title, [(label, status, detail), ...]), ...] for one biome."""
    t = biome.tier
    out = []

    st = ""
    if cf is not None and cf.has_data:
        if biome.gp_key in cf.uniques or (biome.boss_trophy and biome.boss_trophy in cf.trophies):
            st = "done"
    out.append(("Boss", [(biome.boss, st, biome.offering)]))

    rows = []
    for prefab, (name, token, station, res, extends) in sorted(gd.PIECES.items(), key=lambda kv: kv[1][0]):
        if ingredients_tier(res) != t:
            continue
        pst = ""
        if cf is not None and cf.has_data and token in cf.known_recipes:
            pst = "can build"
        detail = _res_text(res)
        if extends:
            detail += " (upgrades the %s)" % station_name(extends)
        rows.append((name, pst, detail))
    out.append(("Stations and base pieces", rows))

    craftable = [p for p in gd.RECIPES if p in itemdata.ITEM_DATA and tier(p) == t]
    for title, types in SECTION_TYPES:
        rows = [(search.label(p), status(cf, p), recipe_text(p))
                for p in craftable if itemdata.ITEM_DATA[p][1] in types]
        rows.sort()
        out.append((title, rows))

    # Foods, plus the 1.0 feasts: crafted as "FeastX_Material", eaten from the placed "FeastX".
    foods = [(p, p) for p in gd.FOODS if p in itemdata.ITEM_DATA and tier(p) == t and itemdata.ITEM_DATA[p][1] in (2, 21)]
    foods += [(p, p[:-len("_Material")]) for p in craftable
              if p.startswith("Feast") and p.endswith("_Material") and p[:-len("_Material")] in gd.FOODS]
    foods.sort(key=lambda pf: -sum(gd.FOODS[pf[1]][:3]))
    rows = []
    for p, stats_of in foods:
        hp, stam, eitr, mins = gd.FOODS[stats_of]
        stats = "%d hp, %d stam" % (hp, stam) + (", %d eitr" % eitr if eitr else "") + ", %d min" % mins
        label = search.label(p) + (" (feast, shared)" if p != stats_of else "")
        rows.append((label, status(cf, p), stats + (" · " + recipe_text(p) if p in gd.RECIPES else "")))
    out.append(("Food", rows))

    rows = [(search.label(p), status(cf, p), recipe_text(p)) for p in craftable
            if itemdata.ITEM_DATA[p][1] == 2 and p not in gd.FOODS]
    rows.sort()
    out.append(("Meads and potions", rows))

    # Raw materials of this biome, plus the ones made from them (bronze, iron, refined eitr...).
    rows = []
    def _intermediate(p):
        return (p.startswith(("MeadBase", "Upgrader", "Mold", "Feast", "Unbaked")) or p.endswith("Uncooked")
                or p in gd.FOODS)
    found = [p for p, pt in MATERIAL_TIER.items() if pt == t and p in itemdata.ITEM_DATA
             and itemdata.ITEM_DATA[p][1] == 1 and not _intermediate(p)]
    made = [p for p in craftable if itemdata.ITEM_DATA[p][1] == 1 and p not in MATERIAL_TIER and not _intermediate(p)]
    for p in found + made:
        detail = recipe_text(p) if p in gd.RECIPES else ""
        if p in gd.NO_PORTAL:
            detail += (" · " if detail else "") + "cannot go through a portal"
        rows.append((search.label(p), status(cf, p), detail))
    rows.sort()
    out.append(("Materials to find or make", rows))
    return out
