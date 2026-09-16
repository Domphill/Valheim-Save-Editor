"""Item lookup: names and limits from the game files, camel-case splitting, word-order-independent search.

vse/itemdata.py is generated from the installed game by tools/generate_itemdata.py and holds,
per prefab: display name, item type, max stack, max durability, durability per quality level,
max quality. Prefabs without an entry there are not inventory items and are not searchable.
"""
import re

from . import itemdata
from . import items as itemdb

CATEGORIES = [("all", "All items"), ("weapon", "Weapons"), ("shield", "Shields"), ("armor", "Armor"),
              ("accessory", "Accessories"), ("food", "Food"), ("material", "Materials"), ("ammo", "Ammo"),
              ("tool", "Tools"), ("trophy", "Trophies"), ("other", "Other")]

_TYPE_TO_CATEGORY = {
    1: "material", 2: "food", 3: "weapon", 4: "weapon", 5: "shield", 6: "armor", 7: "armor", 9: "ammo",
    10: "other", 11: "armor", 12: "armor", 13: "trophy", 14: "weapon", 15: "tool", 16: "other", 17: "armor",
    18: "accessory", 19: "tool", 20: "other", 21: "food", 22: "weapon", 23: "ammo", 24: "accessory",
}

HIDDEN_PREFIXES = ("sfx_", "vfx_", "fx_", "pickable_", "mold")
HIDDEN_SUFFIXES = ("uncooked",)

_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])|_+")


def split_camel(name):
    return " ".join(p for p in _CAMEL.split(name) if p)


def info(prefab):
    return itemdata.ITEM_DATA.get(prefab)


def label(prefab):
    """In-game name from the game files, else the prefab name split into words."""
    d = info(prefab)
    return d[0] if d and d[0] else split_camel(prefab)


def category(prefab):
    d = info(prefab)
    return _TYPE_TO_CATEGORY.get(d[1], "other") if d else "other"


def type_name(prefab):
    d = info(prefab)
    return itemdata.TYPE_NAMES.get(d[1], "unknown") if d else "unknown"


def max_stack(prefab):
    d = info(prefab)
    return d[2] if d else None


def max_quality(prefab):
    d = info(prefab)
    return d[5] if d else None


def max_durability(prefab, quality=1):
    """The game's maximum durability for that quality, or None if the item is unknown."""
    d = info(prefab)
    if not d:
        return None
    return d[3] + max(0, int(quality) - 1) * d[4]


def uses_durability(prefab):
    d = info(prefab)
    return bool(d and d[6])


def searchable_names():
    if itemdata.ITEM_DATA:
        return sorted(itemdata.ITEM_DATA)
    return [n for n in sorted(itemdb.ITEM_NAME_TO_HASH)
            if not n.lower().startswith(HIDDEN_PREFIXES) and not n.lower().endswith(HIDDEN_SUFFIXES)]


def _norm(s):
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def _tokens(query):
    return [t for t in re.split(r"[^a-z0-9]+", query.lower()) if t]


def search(query, names=None, limit=200, category=None):
    """Names matching every word of the query (and the category, if given), best matches first."""
    names = searchable_names() if names is None else names
    if category and category != "all":
        names = [n for n in names if globals()["category"](n) == category]
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
        scored.append((rank, 0 if info(n) else 1, len(lab), lab.lower(), n))
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
