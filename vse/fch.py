"""Reader/writer for Valheim 1.0 character files (.fch).

Format (all little-endian):
    int32 payloadLength, payload, int32 hashLength (64), SHA-512(payload)
    payload = player profile (version 46) which embeds a player-data blob (version 33)
The game rejects the file if the trailing hash does not match the payload.

Parsing logic derived from valheim_character_editor.py in
https://github.com/ValterKane/ValhaimCheaterRemover (MIT). Item flag bits 0x01
(picked up) and 0x02 (equipped) were identified from real 1.0 saves.

Everything the tool does not understand is kept as raw bytes and written back
unchanged. A file is only considered editable if rebuilding it with no changes
reproduces the original bytes exactly (see CharacterFile.editable).
"""
import hashlib
import struct

PROFILE_VERSION = 46
PLAYERDATA_VERSION = 33
STATS_COUNT = 205
SKILLS_VERSION = 2

SKILLS = {
    1: "Swords", 2: "Knives", 3: "Clubs", 4: "Polearms", 5: "Spears",
    6: "Blocking", 7: "Axes", 8: "Bows", 9: "ElementalMagic",
    10: "BloodMagic", 11: "Unarmed", 12: "Pickaxes", 13: "WoodCutting",
    14: "Crossbows", 100: "Jump", 101: "Sneak", 102: "Run", 103: "Swim",
    104: "Fishing", 105: "Cooking", 106: "Farming", 107: "Crafting",
    108: "Dodge", 110: "Ride",
}
SKILL_TYPES = {name: t for t, name in SKILLS.items()}

# Item flag bits.
F_PICKED_UP = 0x01
F_EQUIPPED = 0x02
F_QUALITY = 0x04
F_STACK = 0x08
F_VARIANT = 0x10
F_CRAFTER = 0x20
F_PREFAB = 0x40
F_CUSTOM = 0x80

INVENTORY_W = 8
INVENTORY_H = 4


class FchError(Exception):
    pass


def _write_varint(n):
    out = bytearray()
    while n >= 0x80:
        out.append((n & 0x7F) | 0x80)
        n >>= 7
    out.append(n)
    return bytes(out)


def write_str(s):
    b = s.encode("utf-8")
    return _write_varint(len(b)) + b


class Reader:
    def __init__(self, data, offset=0):
        self.b = data
        self.o = offset

    def _need(self, n):
        if self.o + n > len(self.b):
            raise FchError("truncated data at offset %d" % self.o)

    def _unpack(self, fmt, n):
        self._need(n)
        v = struct.unpack_from(fmt, self.b, self.o)[0]
        self.o += n
        return v

    def i32(self):
        return self._unpack("<i", 4)

    def i64(self):
        return self._unpack("<q", 8)

    def f32(self):
        return self._unpack("<f", 4)

    def u16(self):
        return self._unpack("<H", 2)

    def byte(self):
        return self._unpack("<B", 1)

    def raw(self, n):
        self._need(n)
        v = bytes(self.b[self.o:self.o + n])
        self.o += n
        return v

    def varint(self):
        shift = val = 0
        while True:
            byte = self.byte()
            val |= (byte & 0x7F) << shift
            if not byte & 0x80:
                return val
            shift += 7
            if shift > 28:
                raise FchError("invalid string length prefix at offset %d" % self.o)

    def string(self):
        return self.raw(self.varint()).decode("utf-8", "replace")

    def float_dict(self):
        for _ in range(self.i32()):
            self.string()
            self.f32()


class Item:
    """One inventory item. Durability is stored as an int (game value * 100)."""

    __slots__ = ("durability", "x", "y", "world_level", "flags", "quality", "stack",
                 "variant", "crafter_id", "crafter_name", "prefab", "custom", "cheat_byte")

    def __init__(self):
        self.durability = 10000
        self.x = self.y = self.world_level = 0
        self.flags = F_PICKED_UP | F_PREFAB
        self.quality = 1
        self.stack = 1
        self.variant = 0
        self.crafter_id = 0
        self.crafter_name = ""
        self.prefab = 0
        self.custom = []
        self.cheat_byte = 0

    @property
    def cheated(self):
        return bool(self.cheat_byte & 1)

    @cheated.setter
    def cheated(self, value):
        self.cheat_byte = (self.cheat_byte & ~1) | (1 if value else 0)

    @property
    def equipped(self):
        return bool(self.flags & F_EQUIPPED)

    @property
    def durability_value(self):
        return self.durability / 100.0

    @classmethod
    def parse(cls, r):
        it = cls()
        it.durability = r.i32()
        it.x = r.byte()
        it.y = r.byte()
        it.world_level = r.byte()
        f = it.flags = r.byte()
        it.quality = r.u16() if f & F_QUALITY else 1
        it.stack = r.u16() if f & F_STACK else 1
        it.variant = r.i32() if f & F_VARIANT else 0
        if f & F_CRAFTER:
            it.crafter_id = r.i64()
            it.crafter_name = r.string()
        it.prefab = r.i32() if f & F_PREFAB else 0
        if f & F_CUSTOM:
            cnt = r.byte()
            if cnt & 0x80:
                cnt = ((cnt & 0x7F) << 8) | r.byte()
            it.custom = [(r.string(), r.string()) for _ in range(cnt)]
        it.cheat_byte = r.byte()
        return it

    def to_bytes(self):
        f = self.flags
        b = bytearray(struct.pack("<iBBBB", self.durability, self.x, self.y, self.world_level, f))
        if f & F_QUALITY:
            b += struct.pack("<H", self.quality)
        if f & F_STACK:
            b += struct.pack("<H", self.stack)
        if f & F_VARIANT:
            b += struct.pack("<i", self.variant)
        if f & F_CRAFTER:
            b += struct.pack("<q", self.crafter_id) + write_str(self.crafter_name)
        if f & F_PREFAB:
            b += struct.pack("<i", self.prefab)
        if f & F_CUSTOM:
            n = len(self.custom)
            b += bytes([n]) if n < 0x80 else bytes([0x80 | (n >> 8), n & 0xFF])
            for k, v in self.custom:
                b += write_str(k) + write_str(v)
        b.append(self.cheat_byte)
        return bytes(b)

    def refresh_flags(self):
        """Recompute the presence bits from the field values (keeps picked-up/equipped)."""
        f = self.flags & (F_PICKED_UP | F_EQUIPPED)
        f |= F_PREFAB
        if self.quality != 1:
            f |= F_QUALITY
        if self.stack != 1:
            f |= F_STACK
        if self.variant:
            f |= F_VARIANT
        if self.crafter_name or self.crafter_id:
            f |= F_CRAFTER
        if self.custom:
            f |= F_CUSTOM
        self.flags = f

    @classmethod
    def new(cls, prefab, x, y, stack=1, quality=1, durability=100.0, crafter_id=0, crafter_name=""):
        it = cls()
        it.prefab = int(prefab)
        it.x, it.y = int(x), int(y)
        it.stack = max(1, int(stack))
        it.quality = max(1, int(quality))
        it.durability = max(0, int(round(float(durability) * 100)))
        it.crafter_id = int(crafter_id)
        it.crafter_name = crafter_name or ""
        it.flags = F_PICKED_UP
        it.refresh_flags()
        it.cheat_byte = 0
        return it


class WorldEntry:
    """The character's per-world data: bed spawn, logout point, death marker, home, explored map."""

    __slots__ = ("uid", "have_spawn", "spawn", "have_logout", "logout", "have_death", "death", "home", "map_data")
    ZERO = b"\0" * 12

    def __init__(self):
        self.uid = 0
        self.have_spawn = self.have_logout = self.have_death = 0
        self.spawn = self.logout = self.death = self.home = self.ZERO
        self.map_data = None

    @classmethod
    def parse(cls, r):
        w = cls()
        w.uid = r.i64()
        w.have_spawn = r.byte()
        w.spawn = r.raw(12)
        w.have_logout = r.byte()
        w.logout = r.raw(12)
        w.have_death = r.byte()
        w.death = r.raw(12)
        w.home = r.raw(12)
        if r.byte():
            w.map_data = r.raw(r.i32())
        return w

    def to_bytes(self):
        b = (struct.pack("<q", self.uid) + bytes([self.have_spawn]) + self.spawn
             + bytes([self.have_logout]) + self.logout + bytes([self.have_death]) + self.death + self.home)
        if self.map_data is not None:
            b += b"\x01" + struct.pack("<i", len(self.map_data)) + self.map_data
        else:
            b += b"\x00"
        return b

    @staticmethod
    def _xyz(v):
        return struct.unpack("<fff", v)

    @property
    def logout_xyz(self):
        return self._xyz(self.logout)

    @property
    def death_xyz(self):
        return self._xyz(self.death)

    @property
    def spawn_xyz(self):
        return self._xyz(self.spawn)

    @property
    def map_size(self):
        return len(self.map_data) if self.map_data else 0


def read_world_header(data):
    """(name, seed name, uid) from the start of a .fwl or .fwl2 world file, or None."""
    if len(data) < 8:
        return None
    n = struct.unpack_from("<i", data, 0)[0]
    if n <= 0 or 4 + n > len(data):
        return None
    r = Reader(data[4:4 + n])
    try:
        r.i32()  # file version
        name = r.string()
        seed_name = r.string()
        r.i32()  # seed
        uid = r.i64()
    except FchError:
        return None
    return name, seed_name, uid


class Skill:
    __slots__ = ("type", "level", "acc")

    def __init__(self, stype, level, acc):
        self.type = int(stype)
        self.level = float(level)
        self.acc = float(acc)

    @property
    def name(self):
        return SKILLS.get(self.type, "Skill %d" % self.type)

    def to_bytes(self):
        return struct.pack("<iff", self.type, self.level, self.acc)


class CharacterFile:
    """A parsed .fch. Edit .items, .skills and .used_cheats, then to_bytes()."""

    def __init__(self, data):
        self.original = bytes(data)
        self.items = []
        self.skills = []
        self.worlds = []
        self.has_data = False
        self.max_health = self.health = self.max_stamina = 0.0
        self.guardian_power = ""
        self._parse(self.original)
        # Editing is only allowed when a no-change rebuild reproduces the payload exactly.
        # The trailing hash is always recomputed, so a file with a broken checksum can be repaired.
        n = struct.unpack_from("<i", self.original, 0)[0]
        self.editable = self.build_body() == self.original[4:4 + n]

    @classmethod
    def load(cls, path):
        with open(path, "rb") as f:
            return cls(f.read())

    @staticmethod
    def verify(data):
        """True if the trailing SHA-512 matches the payload."""
        if len(data) < 12:
            return False
        n = struct.unpack_from("<i", data, 0)[0]
        if not (0 < n <= len(data) - 8):
            return False
        hlen = struct.unpack_from("<i", data, 4 + n)[0]
        return hlen == 64 and data[8 + n:8 + n + 64] == hashlib.sha512(data[4:4 + n]).digest()

    # -- parsing ---------------------------------------------------------

    def _parse(self, data):
        if len(data) < 20:
            raise FchError("file too small to be a .fch")
        n = struct.unpack_from("<i", data, 0)[0]
        if not (0 < n <= len(data) - 8):
            raise FchError("invalid .fch header")
        body = data[4:4 + n]
        self.hash_ok = self.verify(data)

        r = Reader(body)
        ver = r.i32()
        if ver != PROFILE_VERSION:
            raise FchError("profile version %d is not supported (this tool understands version %d, the 1.0 format)"
                           % (ver, PROFILE_VERSION))
        nstats = r.i32()
        nbuckets = r.i32()
        if nstats != STATS_COUNT or not (1 <= nbuckets <= 20):
            raise FchError("unexpected stats layout (stats=%d, buckets=%d)" % (nstats, nbuckets))
        for _ in range(nbuckets):
            r.raw(4 * nstats)
            r.float_dict()
            r.float_dict()
            r.float_dict()
            for _ in range(r.i32()):
                r.float_dict()
            for _ in range(5):
                r.float_dict()
        self.first_spawn = r.byte()
        worlds_off = r.o
        n_worlds = r.i32()
        if not (0 <= n_worlds <= 10000):
            raise FchError("unreasonable world count %d" % n_worlds)
        self.worlds = [WorldEntry.parse(r) for _ in range(n_worlds)]
        post_off = r.o
        self.name = r.string()
        self.player_id = r.i64()
        self.seed = r.string()
        flag_off = r.o
        self.used_cheats = r.byte()
        self.date_raw = r.i64()
        has_data = r.byte()
        self._pre_worlds = body[:worlds_off]
        self._post_worlds = body[post_off:flag_off]
        self._mid = body[flag_off + 1:r.o]
        if has_data:
            self.has_data = True
            self._parse_blob(r.raw(r.i32()))
        if r.o != len(body):
            raise FchError("profile end mismatch (%d of %d bytes)" % (r.o, len(body)))

    def _parse_blob(self, blob):
        r = Reader(blob)
        ver = r.i32()
        if ver != PLAYERDATA_VERSION:
            raise FchError("player data version %d is not supported (expected %d)" % (ver, PLAYERDATA_VERSION))
        self.max_health = r.f32()
        self.health = r.f32()
        self.max_stamina = r.f32()
        r.f32()  # time since death
        self.guardian_power = r.string()
        r.f32()  # guardian power cooldown
        r.i32()
        inv_off = r.o
        n = r.u16()
        self.items = [Item.parse(r) for _ in range(n)]
        mid_start = r.o
        for _ in range(r.i32()):
            r.string()
        for _ in range(r.i32()):
            r.string(); r.i32()
        for _ in range(5):
            for _ in range(r.i32()):
                r.string()
        for _ in range(r.i32()):
            r.string(); r.string()
        r.string(); r.string()
        r.raw(24)
        r.i32()
        for _ in range(r.i32()):
            r.string(); r.f32()
        if r.i32() != SKILLS_VERSION:
            raise FchError("unexpected skills version")
        sk_off = r.o
        cnt = r.i32()
        skills = []
        for _ in range(cnt):
            t = r.i32(); lvl = r.f32(); acc = r.f32()
            skills.append(Skill(t, lvl, acc))
        self.skills = skills
        post_start = r.o
        for _ in range(r.i32()):
            r.string(); r.string()
        r.f32(); r.f32(); r.f32()
        r.raw(r.i32())
        if r.o != len(blob):
            raise FchError("player data end mismatch (%d of %d bytes)" % (r.o, len(blob)))
        self._blob_pre = blob[:inv_off]
        self._blob_mid = blob[mid_start:sk_off]
        self._blob_post = blob[post_start:]

    # -- writing ---------------------------------------------------------

    @property
    def world_count(self):
        return len(self.worlds)

    def world(self, uid):
        for w in self.worlds:
            if w.uid == uid:
                return w
        return None

    def build_body(self):
        body = (self._pre_worlds + struct.pack("<i", len(self.worlds))
                + b"".join(w.to_bytes() for w in self.worlds)
                + self._post_worlds + bytes([self.used_cheats & 0xFF]) + self._mid)
        if self.has_data:
            blob = (self._blob_pre
                    + struct.pack("<H", len(self.items))
                    + b"".join(it.to_bytes() for it in self.items)
                    + self._blob_mid
                    + struct.pack("<i", len(self.skills))
                    + b"".join(s.to_bytes() for s in self.skills)
                    + self._blob_post)
            body += struct.pack("<i", len(blob)) + blob
        return body

    def to_bytes(self):
        body = self.build_body()
        return struct.pack("<i", len(body)) + body + struct.pack("<i", 64) + hashlib.sha512(body).digest()

    # -- helpers ---------------------------------------------------------

    def item_at(self, x, y):
        for it in self.items:
            if it.x == x and it.y == y:
                return it
        return None

    @property
    def marked_items(self):
        return [it for it in self.items if it.cheated]
