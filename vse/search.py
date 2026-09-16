"""Item search: in-game display names, camel-case splitting, word-order-independent matching.

DISPLAY_NAMES maps prefab names to the English in-game names for the common items. The
table only helps searching and labelling; the prefab name is always what gets written.
Anything not listed is shown with its prefab name split into words (ArrowIron -> Arrow Iron).
"""
import re

from . import items as itemdb

DISPLAY_NAMES = {
    # materials
    "Wood": "Wood", "FineWood": "Fine wood", "RoundLog": "Core wood", "ElderBark": "Ancient bark",
    "Stone": "Stone", "Flint": "Flint", "Resin": "Resin", "Feathers": "Feathers",
    "LeatherScraps": "Leather scraps", "DeerHide": "Deer hide", "TrollHide": "Troll hide",
    "BoneFragments": "Bone fragments", "Coal": "Coal", "SurtlingCore": "Surtling core",
    "CopperOre": "Copper ore", "Copper": "Copper", "TinOre": "Tin ore", "Tin": "Tin", "Bronze": "Bronze",
    "BronzeNails": "Bronze nails", "IronScrap": "Scrap iron", "Iron": "Iron", "IronNails": "Iron nails",
    "Chain": "Chain", "YmirRemains": "Ymir flesh", "Guck": "Guck", "Ooze": "Ooze", "Bloodbag": "Bloodbag",
    "Entrails": "Entrails", "WitheredBone": "Withered bone", "SilverOre": "Silver ore", "Silver": "Silver",
    "WolfPelt": "Wolf pelt", "WolfFang": "Wolf fang", "FreezeGland": "Freeze gland",
    "DragonTear": "Dragon tear", "Obsidian": "Obsidian", "Crystal": "Crystal", "Needle": "Needle",
    "LoxPelt": "Lox pelt", "BlackMetalScrap": "Black metal scrap", "BlackMetal": "Black metal",
    "LinenThread": "Linen thread", "Flax": "Flax", "Barley": "Barley", "BarleyFlour": "Barley flour",
    "Tar": "Tar", "Coins": "Coins", "Ruby": "Ruby", "Amber": "Amber", "AmberPearl": "Amber pearl",
    "SilverNecklace": "Silver necklace", "HardAntler": "Hard antler", "AncientSeed": "Ancient seed",
    "CryptKey": "Swamp key", "Wishbone": "Wishbone", "DragonEgg": "Dragon egg", "Thistle": "Thistle",
    "Dandelion": "Dandelion", "Honey": "Honey", "QueenBee": "Queen bee", "Sap": "Sap",
    "Softtissue": "Soft tissue", "BlackCore": "Black core", "Eitr": "Refined eitr",
    "MechanicalSpring": "Mechanical spring", "Carapace": "Carapace", "ScaleHide": "Scale hide",
    "JuteRed": "Red jute", "JuteBlue": "Blue jute", "RoyalJelly": "Royal jelly",
    "BeechSeeds": "Beech seeds", "FirCone": "Fir cone", "PineCone": "Pine cone",
    "CarrotSeeds": "Carrot seeds", "TurnipSeeds": "Turnip seeds", "OnionSeeds": "Onion seeds",
    "Chitin": "Chitin", "SharpeningStone": "Sharpening stone", "SerpentScale": "Serpent scale",
    "Root": "Root", "Bilebag": "Bilebag",
    # food and mead
    "Raspberry": "Raspberries", "Blueberries": "Blueberries", "Cloudberry": "Cloudberries",
    "Mushroom": "Mushroom", "MushroomYellow": "Yellow mushroom", "MushroomBlue": "Blue mushroom",
    "Carrot": "Carrot", "Turnip": "Turnip", "Onion": "Onion", "RawMeat": "Raw boar meat",
    "CookedMeat": "Cooked boar meat", "DeerMeat": "Raw deer meat", "CookedDeerMeat": "Cooked deer meat",
    "WolfMeat": "Raw wolf meat", "CookedWolfMeat": "Cooked wolf meat", "LoxMeat": "Raw lox meat",
    "CookedLoxMeat": "Cooked lox meat", "NeckTail": "Neck tail", "NeckTailGrilled": "Grilled neck tail",
    "FishRaw": "Raw fish", "FishCooked": "Cooked fish", "SerpentMeat": "Serpent meat",
    "SerpentMeatCooked": "Cooked serpent meat", "SerpentStew": "Serpent stew", "Sausages": "Sausages",
    "DeerStew": "Deer stew", "MinceMeatSauce": "Minced meat sauce", "BlackSoup": "Black soup",
    "TurnipStew": "Turnip stew", "CarrotSoup": "Carrot soup", "OnionSoup": "Onion soup",
    "QueensJam": "Queens jam", "Bread": "Bread", "FishWraps": "Fish wraps", "LoxPie": "Lox meat pie",
    "BloodPudding": "Blood pudding", "BoarJerky": "Boar jerky", "WolfJerky": "Wolf jerky",
    "WolfMeatSkewer": "Wolf skewer", "Eyescream": "Eyescream", "ShocklateSmoothie": "Shocklate smoothie",
    "HoneyGlazedChicken": "Honey glazed chicken", "MeadTasty": "Tasty mead",
    "MeadPoisonResist": "Poison resistance mead", "MeadHealthMinor": "Minor healing mead",
    "MeadHealthMedium": "Medium healing mead", "MeadHealthMajor": "Major healing mead",
    "MeadStaminaMinor": "Minor stamina mead", "MeadStaminaMedium": "Medium stamina mead",
    "MeadFrostResist": "Frost resistance mead", "BarleyWine": "Fire resistance barley wine",
    "MeadEitrMinor": "Minor eitr mead",
    # tools and weapons
    "Club": "Club", "Torch": "Torch", "Hammer": "Hammer", "Hoe": "Hoe", "Cultivator": "Cultivator",
    "AxeStone": "Stone axe", "AxeFlint": "Flint axe", "AxeBronze": "Bronze axe", "AxeIron": "Iron axe",
    "AxeBlackMetal": "Blackmetal axe", "AxeJotunBane": "Jotun bane", "KnifeFlint": "Flint knife",
    "KnifeCopper": "Copper knife", "KnifeChitin": "Abyssal razor", "KnifeBlackMetal": "Blackmetal knife",
    "KnifeSilver": "Silver knife", "KnifeButcher": "Butcher knife", "SpearFlint": "Flint spear",
    "SpearBronze": "Bronze spear", "SpearElderbark": "Ancient bark spear", "SpearWolfFang": "Fang spear",
    "SpearChitin": "Abyssal harpoon", "SpearCarapace": "Carapace spear", "Bow": "Crude bow",
    "BowFineWood": "Finewood bow", "BowHuntsman": "Huntsman bow", "BowDraugrFang": "Draugr fang",
    "BowSpineSnap": "Spine snap", "ArrowWood": "Wood arrow", "ArrowFlint": "Flint arrow",
    "ArrowFire": "Fire arrow", "ArrowBronze": "Bronzehead arrow", "ArrowIron": "Iron arrow",
    "ArrowPoison": "Poison arrow", "ArrowObsidian": "Obsidian arrow", "ArrowFrost": "Frost arrow",
    "ArrowSilver": "Silver arrow", "ArrowNeedle": "Needle arrow", "ArrowCarapace": "Carapace arrow",
    "SwordBronze": "Bronze sword", "SwordIron": "Iron sword", "SwordSilver": "Silver sword",
    "SwordBlackmetal": "Blackmetal sword", "SwordMistwalker": "Mistwalker", "MaceBronze": "Bronze mace",
    "MaceIron": "Iron mace", "MaceSilver": "Frostner", "MaceNeedle": "Porcupine",
    "SledgeStagbreaker": "Stagbreaker", "SledgeIron": "Iron sledge", "SledgeDemolisher": "Demolisher",
    "AtgeirBronze": "Bronze atgeir", "AtgeirIron": "Iron atgeir", "AtgeirBlackmetal": "Blackmetal atgeir",
    "AtgeirHimminAfl": "Himmin afl", "PickaxeAntler": "Antler pickaxe", "PickaxeBronze": "Bronze pickaxe",
    "PickaxeIron": "Iron pickaxe", "PickaxeBlackMetal": "Blackmetal pickaxe",
    "FistFenrirClaw": "Fenris claws", "BattleaxeCrystal": "Crystal battleaxe",
    "CrossbowArbalest": "Arbalest", "BoltIron": "Iron bolt", "BoltBlackmetal": "Blackmetal bolt",
    "BoltCarapace": "Carapace bolt", "StaffFireball": "Staff of embers", "StaffIceShards": "Staff of frost",
    "StaffShield": "Staff of protection", "StaffSkeleton": "Dead raiser", "ShieldWood": "Wood shield",
    "ShieldWoodTower": "Wood tower shield", "ShieldBronzeBuckler": "Bronze buckler",
    "ShieldBanded": "Banded shield", "ShieldIronTower": "Iron tower shield", "ShieldSilver": "Silver shield",
    "ShieldSerpentscale": "Serpent scale shield", "ShieldBlackmetal": "Blackmetal shield",
    "ShieldBlackmetalTower": "Blackmetal tower shield", "ShieldCarapace": "Carapace shield",
    "ShieldCarapaceBuckler": "Carapace buckler", "Tankard": "Tankard", "FishingRod": "Fishing rod",
    "FishingBait": "Fishing bait",
    # armour and accessories
    "ArmorRagsChest": "Rag tunic", "ArmorRagsLegs": "Rag pants", "ArmorLeatherChest": "Leather tunic",
    "ArmorLeatherLegs": "Leather pants", "HelmetLeather": "Leather helmet", "CapeDeerHide": "Deer hide cape",
    "ArmorTrollLeatherChest": "Troll leather tunic", "ArmorTrollLeatherLegs": "Troll leather pants",
    "HelmetTrollLeather": "Troll leather helmet", "CapeTrollHide": "Troll hide cape",
    "ArmorBronzeChest": "Bronze plate cuirass", "ArmorBronzeLegs": "Bronze plate leggings",
    "HelmetBronze": "Bronze helmet", "ArmorIronChest": "Iron scale mail", "ArmorIronLegs": "Iron greaves",
    "HelmetIron": "Iron helmet", "ArmorRootChest": "Root harnesk", "ArmorRootLegs": "Root leggings",
    "HelmetRoot": "Root mask", "ArmorWolfChest": "Wolf armor chest", "ArmorWolfLegs": "Wolf armor legs",
    "HelmetDrake": "Drake helmet", "CapeWolf": "Wolf fur cape", "ArmorFenringChest": "Fenris coat",
    "ArmorFenringLegs": "Fenris leggings", "HelmetFenring": "Fenris hood",
    "ArmorPaddedCuirass": "Padded cuirass", "ArmorPaddedGreaves": "Padded greaves",
    "HelmetPadded": "Padded helmet", "CapeLox": "Lox cape", "CapeLinen": "Linen cape",
    "ArmorCarapaceChest": "Carapace armor", "ArmorCarapaceLegs": "Carapace greaves",
    "HelmetCarapace": "Carapace helmet", "CapeFeather": "Feather cape", "ArmorMageChest": "Eitr-weave robe",
    "ArmorMageLegs": "Eitr-weave trousers", "HelmetMage": "Eitr-weave hood", "BeltStrength": "Megingjord",
    "HelmetYule": "Yule hat", "HelmetDverger": "Dverger circlet", "HelmetOdin": "Hood of Odin",
    "CapeOdin": "Cape of Odin",
}

# Prefabs in the asset table that are not inventory items: sounds, effects, pickable ground
# objects, and the casting moulds used by the game's crafting model.
HIDDEN_PREFIXES = ("sfx_", "vfx_", "fx_", "pickable_", "mold")
HIDDEN_SUFFIXES = ("uncooked",)

_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])|_+")


def split_camel(name):
    return " ".join(p for p in _CAMEL.split(name) if p)


def label(prefab):
    """In-game name if known, else the prefab name split into words."""
    return DISPLAY_NAMES.get(prefab) or split_camel(prefab)


def searchable_names():
    return [n for n in sorted(itemdb.ITEM_NAME_TO_HASH)
            if not n.lower().startswith(HIDDEN_PREFIXES) and not n.lower().endswith(HIDDEN_SUFFIXES)]


def _norm(s):
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def _tokens(query):
    return [t for t in re.split(r"[^a-z0-9]+", query.lower()) if t]


def search(query, names=None, limit=200):
    """Names matching every word of the query, best matches first."""
    names = searchable_names() if names is None else names
    toks = _tokens(query)
    if not toks:
        return names[:limit]
    joined = "".join(toks)
    scored = []
    for n in names:
        lab = label(n)
        hay_words = [w for w in re.split(r"[^a-z0-9]+", (lab + " " + split_camel(n)).lower()) if w]
        hay = " ".join(hay_words)
        if not all(t in hay for t in toks):
            continue
        nn, nl = _norm(n), _norm(lab)
        if nl == joined or nn == joined:
            rank = 0
        elif nl.startswith(joined) or nn.startswith(joined):
            rank = 1
        elif all(any(w.startswith(t) for w in hay_words) for t in toks):
            rank = 2
        else:
            rank = 3
        # Known in-game items outrank prefabs nobody has named, e.g. enemy weapons and props.
        scored.append((rank, 0 if n in DISPLAY_NAMES else 1, len(lab), lab.lower(), n))
    scored.sort()
    return [s[-1] for s in scored[:limit]]


def resolve(text, names=None):
    """Exact prefab or display name (any case/spacing), or the single match; else None."""
    if not text or not text.strip():
        return None
    key = _norm(text)
    names = searchable_names() if names is None else names
    for n in names:
        if _norm(n) == key or _norm(label(n)) == key:
            return n
    hits = search(text, names, limit=2)
    return hits[0] if len(hits) == 1 else None
