"""Unit tests. Run from the project root:  python -m unittest discover -s tests -v

Set VSE_TEST_FCH=<path to a real .fch> to also run the round-trip test on a real save
(the file is only read).
"""
import os
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vse import core, fch  # noqa: E402
from vse import items as itemdb  # noqa: E402


def make_world(uid, map_bytes=b"", death=False, logout=(10.0, 30.0, -20.0)):
    w = fch.WorldEntry()
    w.uid = uid
    w.have_logout = 1
    w.logout = struct.pack("<fff", *logout)
    if death:
        w.have_death = 1
        w.death = struct.pack("<fff", 1.0, 2.0, 3.0)
    w.map_data = map_bytes or None
    return w


def build_synthetic(name="Tester", player_id=1234567890, used_cheats=0, items=(), skills=(), has_data=True,
                    worlds=(), uniques=(), known_recipes=(), known_materials=(), trophies=(), biomes=()):
    """Build a minimal but structurally complete 1.0 profile the parser accepts."""
    def slist(vals):
        return struct.pack("<i", len(vals)) + b"".join(fch.write_str(v) for v in vals)
    def i32(v): return struct.pack("<i", v)
    def f32(v): return struct.pack("<f", v)
    def i64(v): return struct.pack("<q", v)
    fdict0 = i32(0)
    bucket = b"\0" * (4 * fch.STATS_COUNT) + fdict0 * 3 + i32(0) + fdict0 * 5
    body = i32(fch.PROFILE_VERSION) + i32(fch.STATS_COUNT) + i32(1) + bucket
    body += b"\x01" + i32(len(worlds)) + b"".join(w.to_bytes() for w in worlds)  # first_spawn, worlds
    body += fch.write_str(name) + i64(player_id) + fch.write_str("")
    body += bytes([used_cheats]) + i64(1700000000) + (b"\x01" if has_data else b"\x00")
    if has_data:
        blob = i32(fch.PLAYERDATA_VERSION) + f32(25) + f32(25) + f32(50) + f32(0)
        blob += fch.write_str("") + f32(0) + i32(0)
        blob += struct.pack("<H", len(items)) + b"".join(it.to_bytes() for it in items)
        blob += slist(known_recipes) + i32(0) + slist(known_materials) + i32(0)  # recipes, stations, materials, tutorials
        blob += slist(uniques)                                                   # uniques (player keys)
        blob += slist(trophies) + slist(biomes) + i32(0)                         # trophies, biomes, texts
        blob += fch.write_str("") + fch.write_str("") + b"\0" * 24 + i32(0) + i32(0)  # beard, hair, colours, model, foods
        blob += i32(fch.SKILLS_VERSION) + i32(len(skills)) + b"".join(s.to_bytes() for s in skills)
        blob += i32(0) + f32(50) + f32(0) + f32(0) + i32(0)
        body += i32(len(blob)) + blob
    import hashlib
    return i32(len(body)) + body + i32(64) + hashlib.sha512(body).digest()


class ItemTests(unittest.TestCase):
    def test_roundtrip_full(self):
        it = fch.Item.new(itemdb.ITEM_NAME_TO_HASH["Sausages"], 7, 0, stack=10, quality=1, durability=100,
                          crafter_id=2363949630, crafter_name="Dom")
        raw = it.to_bytes()
        # Mirrors a real cauldron-food stack from a 1.0 save.
        self.assertEqual(raw.hex(), "10270000070000690a003e02e78c0000000003446f6d16e72e5e00")
        back = fch.Item.parse(fch.Reader(raw))
        self.assertEqual(back.to_bytes(), raw)
        self.assertEqual((back.stack, back.quality, back.crafter_name, back.prefab, back.cheated),
                         (10, 1, "Dom", itemdb.ITEM_NAME_TO_HASH["Sausages"], False))

    def test_real_layouts(self):
        # Raw items captured from a real 1.0 save must parse and re-serialize identically.
        for h in ("102700000202006b50003e02e78c0000000003446f6d29eeb08d00",   # equipped arrows
                  "10270000070300490400c324f3f600",                            # raw wood, no crafter
                  "102700000403004906006edb7bcc01",                            # marked root stack
                  "10270000010300690200a31a53d5ffffffff094a6f6c6c794f6c6c7916e72e5e00"):  # friend-made food
            raw = bytes.fromhex(h)
            it = fch.Item.parse(fch.Reader(raw))
            self.assertEqual(it.to_bytes(), raw)
        marked = fch.Item.parse(fch.Reader(bytes.fromhex("102700000403004906006edb7bcc01")))
        self.assertTrue(marked.cheated)
        marked.cheated = False
        self.assertEqual(marked.to_bytes()[-1], 0)
        arrows = fch.Item.parse(fch.Reader(bytes.fromhex("102700000202006b50003e02e78c0000000003446f6d29eeb08d00")))
        self.assertTrue(arrows.equipped)

    def test_custom_data_and_variant(self):
        it = fch.Item.new(1, 0, 0)
        it.variant = 3
        it.custom = [("k", "v"), ("a", "b")]
        it.refresh_flags()
        back = fch.Item.parse(fch.Reader(it.to_bytes()))
        self.assertEqual(back.variant, 3)
        self.assertEqual(back.custom, [("k", "v"), ("a", "b")])
        self.assertEqual(back.to_bytes(), it.to_bytes())


class FileTests(unittest.TestCase):
    def setUp(self):
        self.items = [fch.Item.new(itemdb.ITEM_NAME_TO_HASH["Wood"], 0, 0, stack=20),
                      fch.Item.new(itemdb.ITEM_NAME_TO_HASH["AxeFlint"], 1, 0, quality=2, durability=200,
                                   crafter_id=1234567890, crafter_name="Tester")]
        self.items[1].cheated = True
        self.skills = [fch.Skill(1, 42.0, 5.5), fch.Skill(102, 60.0, 0.0)]
        self.data = build_synthetic(used_cheats=1, items=self.items, skills=self.skills)

    def test_parse_and_rebuild(self):
        cf = fch.CharacterFile(self.data)
        self.assertTrue(cf.hash_ok)
        self.assertTrue(cf.editable)
        self.assertEqual(cf.name, "Tester")
        self.assertEqual(cf.used_cheats, 1)
        self.assertEqual(len(cf.items), 2)
        self.assertEqual(len(cf.marked_items), 1)
        self.assertEqual([s.level for s in cf.skills], [42.0, 60.0])
        self.assertEqual(cf.to_bytes(), self.data)

    def test_edit_flow(self):
        cf = fch.CharacterFile(self.data)
        cf.used_cheats = 0
        self.assertEqual(core.clear_marks(cf), 1)
        core.add_item(cf, "ArrowIron", 7, 1, stack=100)
        core.add_item(cf, "IronScrap", 6, 1, stack=30, crafted_by_character=False)
        core.set_skill(cf, 1, 55)
        core.set_skill(cf, 8, 20)      # new skill
        core.remove_skill(cf, 102)
        out = cf.to_bytes()
        self.assertTrue(fch.CharacterFile.verify(out))
        cf2 = fch.CharacterFile(out)
        self.assertEqual(cf2.used_cheats, 0)
        self.assertEqual(len(cf2.items), 4)
        self.assertEqual(len(cf2.marked_items), 0)
        arrows = cf2.item_at(7, 1)
        self.assertEqual((core.item_name(arrows), arrows.stack, arrows.crafter_name), ("ArrowIron", 100, "Tester"))
        scrap = cf2.item_at(6, 1)
        self.assertEqual((core.item_name(scrap), scrap.crafter_name), ("IronScrap", ""))
        self.assertEqual({s.type: s.level for s in cf2.skills}, {1: 55.0, 8: 20.0})
        with self.assertRaises(ValueError):
            core.add_item(cf2, "Wood", 7, 1)   # occupied
        with self.assertRaises(ValueError):
            core.add_item(cf2, "NotAnItem", 5, 1)

    def test_no_player_data(self):
        cf = fch.CharacterFile(build_synthetic(has_data=False, used_cheats=1))
        self.assertFalse(cf.has_data)
        self.assertTrue(cf.editable)
        cf.used_cheats = 0
        self.assertEqual(fch.CharacterFile(cf.to_bytes()).used_cheats, 0)
        with self.assertRaises(ValueError):
            core.add_item(cf, "Wood", 0, 0)
        with self.assertRaises(ValueError):
            core.set_skill(cf, 1, 10)

    def test_bad_checksum_is_repairable(self):
        bad = bytearray(self.data)
        bad[-1] ^= 0xFF
        cf = fch.CharacterFile(bytes(bad))
        self.assertFalse(cf.hash_ok)
        self.assertTrue(cf.editable)
        self.assertTrue(fch.CharacterFile.verify(cf.to_bytes()))
        self.assertEqual(cf.to_bytes(), self.data)

    def test_item_helpers(self):
        cf = fch.CharacterFile(self.data)
        self.assertEqual(core.resolve_item("sausages")[0], "Sausages")
        self.assertEqual(core.resolve_item(str(itemdb.ITEM_NAME_TO_HASH["Wood"]))[0], "Wood")
        with self.assertRaises(ValueError):
            core.resolve_item("")
        it = core.add_item(cf, "arrowiron", 5, 3, stack=100)
        self.assertEqual(core.item_name(it), "ArrowIron")
        core.update_item(it, stack=40, quality=1, durability=75.5)
        back = fch.Item.parse(fch.Reader(it.to_bytes()))
        self.assertEqual((back.stack, back.quality, back.durability, back.crafter_name), (40, 1, 7550, "Tester"))
        with self.assertRaises(ValueError):
            core.update_item(it, stack=0)
        equipped = fch.Item.parse(fch.Reader(bytes.fromhex("102700000202006b50003e02e78c0000000003446f6d29eeb08d00")))
        core.update_item(equipped, stack=100)
        self.assertTrue(equipped.equipped, "editing must keep the equipped bit")

    def test_process_check_finds_a_known_process(self):
        if sys.platform != "win32":
            self.skipTest("Windows only")
        self.assertTrue(core.is_process_running("explorer.exe"))
        self.assertFalse(core.is_process_running("no-such-process-xyz.exe"))

    def test_cli_dump_and_clear(self):
        import io
        from contextlib import redirect_stdout
        from vse import cli
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "Tester.fch")
            with open(path, "wb") as f:
                f.write(self.data)
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(cli.main(["dump", path]), 0)
            self.assertIn("Cheat flag: SET", out.getvalue())
            self.assertIn("MARKED", out.getvalue())
            if core.is_valheim_running():
                self.skipTest("Valheim is running")
            saved_env = os.environ.get("LOCALAPPDATA")
            os.environ["LOCALAPPDATA"] = d  # keep the CLI's backups inside the temp dir
            try:
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(cli.main(["clear", path]), 0)
                    self.assertEqual(cli.main(["skill", path, "swords=70"]), 0)
                    self.assertEqual(cli.main(["add", path, "IronScrap", "--slot", "3,3", "--stack", "30", "--no-crafter"]), 0)
            finally:
                if saved_env is None:
                    os.environ.pop("LOCALAPPDATA", None)
                else:
                    os.environ["LOCALAPPDATA"] = saved_env
            cf = fch.CharacterFile.load(path)
            self.assertEqual((cf.used_cheats, len(cf.marked_items)), (0, 0))
            self.assertEqual({s.type: s.level for s in cf.skills}[1], 70.0)
            self.assertEqual(core.item_name(cf.item_at(3, 3)), "IronScrap")

    def test_wrong_version_rejected(self):
        bad = bytearray(self.data)
        struct.pack_into("<i", bad, 4, 45)
        with self.assertRaises(fch.FchError):
            fch.CharacterFile(bytes(bad))

    def test_save_writes_backup_and_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "Tester.fch")
            with open(path, "wb") as f:
                f.write(self.data)
            cf = fch.CharacterFile.load(path)
            cf.used_cheats = 0
            if core.is_valheim_running():
                self.skipTest("Valheim is running")
            backup = core.save(cf, path, os.path.join(d, "backups"))
            self.assertTrue(os.path.exists(backup))
            with open(backup, "rb") as f:
                self.assertEqual(f.read(), self.data)
            self.assertEqual(fch.CharacterFile.load(path).used_cheats, 0)
            self.assertEqual(core.list_backups(path, os.path.join(d, "backups")), [backup])


class WorldTests(unittest.TestCase):
    def setUp(self):
        self.worlds = [make_world(111, map_bytes=bytes(range(256)) * 8, death=True),
                       make_world(222)]
        self.data = build_synthetic(worlds=self.worlds, items=[fch.Item.new(1, 0, 0)], skills=[fch.Skill(1, 5, 0)])

    def test_parse_and_roundtrip(self):
        cf = fch.CharacterFile(self.data)
        self.assertEqual(cf.world_count, 2)
        self.assertTrue(cf.editable)
        w = cf.world(111)
        self.assertEqual(w.map_size, 2048)
        self.assertTrue(w.have_death)
        self.assertEqual(w.logout_xyz, (10.0, 30.0, -20.0))
        self.assertIsNone(cf.world(222).map_data)
        self.assertEqual(cf.to_bytes(), self.data)

    def test_forget_clear_and_describe(self):
        cf = fch.CharacterFile(self.data)
        core.clear_death_marker(cf, 111)
        core.clear_world_map(cf, 111)
        core.forget_world(cf, 222)
        lines = core.describe_changes(cf)
        self.assertTrue(any("ID 111" in l and "map cleared" in l and "death marker cleared" in l for l in lines), lines)
        self.assertTrue(any(l.startswith("- world") and "ID 222" in l for l in lines), lines)
        out = cf.to_bytes()
        cf2 = fch.CharacterFile(out)
        self.assertEqual(cf2.world_count, 1)
        self.assertFalse(cf2.world(111).have_death)
        self.assertIsNone(cf2.world(111).map_data)
        self.assertEqual(cf2.world(111).logout_xyz, (10.0, 30.0, -20.0), "position must survive a map clear")
        with self.assertRaises(ValueError):
            core.forget_world(cf2, 999)

    def test_world_header(self):
        pkg = (struct.pack("<i", 41) + fch.write_str("MyWorld") + fch.write_str("abcSEED123")
               + struct.pack("<i", 77) + struct.pack("<q", 5227202803) + struct.pack("<i", 2) + b"\x01")
        data = struct.pack("<i", len(pkg)) + pkg + b"trailing"
        self.assertEqual(fch.read_world_header(data), ("MyWorld", "abcSEED123", 5227202803))
        self.assertIsNone(fch.read_world_header(b"\x00\x00"))
        self.assertEqual(core.world_label(5227202803, {5227202803: "MyWorld"}), "MyWorld")
        self.assertEqual(core.world_label(42, {}), "Unknown world (ID 42)")


class InventorySizeTests(unittest.TestCase):
    def setUp(self):
        self.items = [fch.Item.new(itemdb.ITEM_NAME_TO_HASH["Wood"], 0, 0, stack=20),
                      fch.Item.new(itemdb.ITEM_NAME_TO_HASH["Coins"], 6, 4, stack=10)]   # fifth row
        self.uniques = ["GP_Eikthyr", "defeated_eikthyr", "invrows 5", "invslot1"]
        self.data = build_synthetic(items=self.items, uniques=self.uniques)

    def test_parse_rows_and_keys(self):
        cf = fch.CharacterFile(self.data)
        self.assertTrue(cf.editable)
        self.assertEqual(cf.uniques, self.uniques)
        self.assertEqual(cf.inventory_rows, 5)
        self.assertTrue(cf.has_unique("invslot1"))
        self.assertEqual(cf.get_unique_value("InvRows"), "5", "keys compare case-insensitively, as in the game")
        self.assertEqual(cf.to_bytes(), self.data)
        plain = fch.CharacterFile(build_synthetic())
        self.assertEqual((plain.inventory_rows, plain.uniques), (4, []))

    def test_set_rows(self):
        cf = fch.CharacterFile(self.data)
        with self.assertRaises(ValueError):
            core.set_inventory_rows(cf, 4)      # the coins sit in row 4
        with self.assertRaises(ValueError):
            core.set_inventory_rows(cf, fch.INVENTORY_MAX_H + 1)
        core.set_inventory_rows(cf, 7)
        self.assertEqual(cf.uniques.index("invrows 7"), 2, "the key keeps its place in the list")
        core.add_item(cf, "Wood", 0, 6)
        with self.assertRaises(ValueError):
            core.add_item(cf, "Wood", 0, 7)
        self.assertIn("Inventory rows: 5 -> 7", core.describe_changes(cf))
        cf2 = fch.CharacterFile(cf.to_bytes())
        self.assertEqual(cf2.inventory_rows, 7)
        self.assertEqual(core.item_name(cf2.item_at(0, 6)), "Wood")

    def test_pockets(self):
        cf = fch.CharacterFile(build_synthetic(items=[fch.Item.new(1, 0, 0)]))
        core.set_pocket(cf, 1, True)
        self.assertEqual((cf.inventory_rows, cf.has_unique("invslot1")), (5, True))
        core.set_pocket(cf, 2, True)
        core.set_pocket(cf, 2, True)            # already bought: no change
        self.assertEqual((cf.inventory_rows, cf.uniques), (6, ["invrows 6", "invslot1", "invslot2"]))
        lines = core.describe_changes(cf)
        self.assertIn("Inventory rows: 4 -> 6", lines)
        self.assertTrue(any(l.startswith("+ key Wider Pockets") for l in lines), lines)
        self.assertFalse(any("invrows" in l for l in lines), "the rows key is reported as a row count, not a key")
        core.add_item(cf, "Wood", 0, 5)
        with self.assertRaises(ValueError):
            core.set_pocket(cf, 2, False)       # row 5 is in use
        self.assertTrue(cf.has_unique("invslot2"), "a refused removal must leave the key alone")
        core.remove_item(cf, cf.item_at(0, 5))
        core.set_pocket(cf, 2, False)
        core.set_pocket(cf, 1, False)
        self.assertEqual((cf.inventory_rows, cf.uniques), (4, ["invrows 4"]))
        self.assertEqual(fch.CharacterFile(cf.to_bytes()).uniques, ["invrows 4"])
        with self.assertRaises(ValueError):
            core.set_pocket(fch.CharacterFile(build_synthetic(has_data=False)), 1, True)

    def test_cli_rows(self):
        import io
        from contextlib import redirect_stdout
        from vse import cli
        if core.is_valheim_running():
            self.skipTest("Valheim is running")
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "Tester.fch")
            with open(path, "wb") as f:
                f.write(self.data)
            saved_env = os.environ.get("LOCALAPPDATA")
            os.environ["LOCALAPPDATA"] = d
            out = io.StringIO()
            try:
                with redirect_stdout(out):
                    self.assertEqual(cli.main(["rows", path]), 0)
                    self.assertEqual(cli.main(["rows", path, "--deeper"]), 0)
                    self.assertEqual(cli.main(["dump", path]), 0)
                    self.assertEqual(cli.main(["rows", path, "4"]), 1)    # row 4 holds the coins
            finally:
                if saved_env is None:
                    os.environ.pop("LOCALAPPDATA", None)
                else:
                    os.environ["LOCALAPPDATA"] = saved_env
            text = out.getvalue()
            self.assertIn("inventory rows: 5 (Wider Pockets)", text)
            self.assertIn("inventory rows: 6 (Wider Pockets, Deeper Pockets)", text)
            self.assertIn("Inventory : 6 rows", text)
            self.assertIn("Keys (5): GP_Eikthyr", text)
            cf = fch.CharacterFile.load(path)
            self.assertEqual((cf.inventory_rows, cf.has_unique("invslot2")), (6, True))


class RefillRepairTests(unittest.TestCase):
    def setUp(self):
        H = itemdb.ITEM_NAME_TO_HASH
        self.items = [fch.Item.new(H["Wood"], 0, 0, stack=20),
                      fch.Item.new(H["ArrowIron"], 1, 0, stack=10),
                      fch.Item.new(H["Sausages"], 2, 0, stack=3),
                      fch.Item.new(H["MeadHealthMinor"], 3, 0, stack=1),
                      fch.Item.new(H["Coins"], 4, 0, stack=5),
                      fch.Item.new(H["AxeFlint"], 5, 0, quality=2, durability=50, crafter_id=1, crafter_name="Tester"),
                      fch.Item.new(H["SwordBronze"], 6, 0, quality=1, durability=9999)]   # above the table: keep
        self.items[1].flags |= fch.F_EQUIPPED
        self.data = build_synthetic(items=self.items)

    def test_refill(self):
        from vse import search
        cf = fch.CharacterFile(self.data)
        by = lambda n: cf.item_at(*{"Wood": (0, 0), "ArrowIron": (1, 0), "Sausages": (2, 0),
                                    "MeadHealthMinor": (3, 0), "Coins": (4, 0)}[n])
        changed = core.refill_stacks(cf, core.REFILL_QUICK)
        self.assertEqual(sorted(core.item_name(i) for i in changed), ["ArrowIron", "MeadHealthMinor", "Sausages"])
        self.assertEqual(by("ArrowIron").stack, search.max_stack("ArrowIron"))
        self.assertTrue(by("ArrowIron").equipped, "refilling must keep the equipped bit")
        self.assertEqual(by("Sausages").stack, search.max_stack("Sausages"))
        self.assertEqual(by("MeadHealthMinor").stack, search.max_stack("MeadHealthMinor"))
        self.assertEqual((by("Wood").stack, by("Coins").stack), (20, 5), "materials and coins are not 'food & ammo'")
        self.assertEqual(core.refill_stacks(cf, core.REFILL_QUICK), [], "second pass changes nothing")
        changed = core.refill_stacks(cf)
        self.assertEqual([core.item_name(i) for i in changed], ["Wood"])
        self.assertEqual((by("Wood").stack, by("Coins").stack), (search.max_stack("Wood"), 5), "coins are never refilled")
        cf2 = fch.CharacterFile(cf.to_bytes())
        self.assertEqual(cf2.item_at(1, 0).stack, search.max_stack("ArrowIron"))
        self.assertTrue(any("ArrowIron at 1,0: stack 10 ->" in l for l in core.describe_changes(cf)))

    def test_repair(self):
        from vse import search
        cf = fch.CharacterFile(self.data)
        changed = core.repair_all(cf)
        self.assertEqual([core.item_name(i) for i in changed], ["AxeFlint"])
        self.assertEqual(cf.item_at(5, 0).durability_value, search.max_durability("AxeFlint", 2))
        self.assertEqual(cf.item_at(6, 0).durability_value, 9999.0, "never lower a value above the table")
        self.assertEqual(cf.item_at(2, 0).durability, 10000, "food has no durability to repair")
        self.assertEqual(core.repair_all(cf), [])

    def test_cli_refill_and_repair(self):
        import io
        from contextlib import redirect_stdout
        from vse import cli, search
        if core.is_valheim_running():
            self.skipTest("Valheim is running")
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "Tester.fch")
            with open(path, "wb") as f:
                f.write(self.data)
            saved_env = os.environ.get("LOCALAPPDATA")
            os.environ["LOCALAPPDATA"] = d
            out = io.StringIO()
            try:
                with redirect_stdout(out):
                    self.assertEqual(cli.main(["refill", path]), 0)
                    self.assertEqual(cli.main(["refill", path, "--all"]), 0)
                    self.assertEqual(cli.main(["repair", path]), 0)
                    self.assertEqual(cli.main(["repair", path]), 0)   # nothing left: no save, still 0
            finally:
                if saved_env is None:
                    os.environ.pop("LOCALAPPDATA", None)
                else:
                    os.environ["LOCALAPPDATA"] = saved_env
            text = out.getvalue()
            self.assertIn("refilled 3 stack(s)", text)
            self.assertIn("refilled 1 stack(s)", text)
            self.assertIn("repaired 1 item(s)", text)
            self.assertIn("repaired 0 item(s)", text)
            cf = fch.CharacterFile.load(path)
            self.assertEqual(cf.item_at(0, 0).stack, search.max_stack("Wood"))
            self.assertEqual(cf.item_at(4, 0).stack, 5)
            self.assertEqual(cf.item_at(5, 0).durability_value, search.max_durability("AxeFlint", 2))


class GiveItemsTests(unittest.TestCase):
    def test_topup_split_and_hotbar_last(self):
        from vse import search
        H = itemdb.ITEM_NAME_TO_HASH
        cf = fch.CharacterFile(build_synthetic(items=[fch.Item.new(H["Wood"], 0, 1, stack=40)]))
        added, topped = core.give_items(cf, [("Wood", 70), ("Iron", 2)])
        self.assertEqual([(core.item_name(it), n) for it, n in topped], [("Wood", 10)])
        self.assertEqual(cf.item_at(0, 1).stack, search.max_stack("Wood"))
        self.assertEqual(sorted((core.item_name(i), i.stack) for i in added), [("Iron", 2), ("Wood", 10), ("Wood", 50)])
        self.assertTrue(all(i.y == 1 for i in added), "row 1 fills before the hotbar")
        self.assertTrue(all(i.crafter_name == "" and not i.cheated for i in added))
        self.assertEqual(fch.CharacterFile(cf.to_bytes()).item_at(1, 1).stack, added[0].stack)
        # times multiplies, and a marked stack is never topped up (the unmarked 10-stack is)
        cf.items[0].cheated = True
        cf.items[0].stack = 1
        added, topped = core.give_items(cf, [("Wood", 3)], times=2)
        self.assertEqual([(core.item_name(it), it.cheated, n) for it, n in topped], [("Wood", False, 6)])
        self.assertEqual(added, [])
        self.assertEqual(cf.items[0].stack, 1)

    def test_all_or_nothing_and_unknown(self):
        H = itemdb.ITEM_NAME_TO_HASH
        items = [fch.Item.new(H["Stone"], x, y, stack=1) for y in range(4) for x in range(8)][:31]   # one slot free
        cf = fch.CharacterFile(build_synthetic(items=items))
        before = cf.to_bytes()
        with self.assertRaises(ValueError):
            core.give_items(cf, [("Wood", 60)])            # two stacks, one slot
        self.assertEqual(cf.to_bytes(), before, "a refused give changes nothing")
        with self.assertRaises(ValueError):
            core.give_items(cf, [("NoSuchThing", 1)])
        self.assertEqual(cf.to_bytes(), before)
        added, _ = core.give_items(cf, [("Wood", 50)])
        self.assertEqual((core.item_name(added[0]), added[0].stack, (added[0].x, added[0].y)), ("Wood", 50, (7, 3)))
        with self.assertRaises(ValueError):
            core.give_items(fch.CharacterFile(build_synthetic(has_data=False)), [("Wood", 1)])

    def test_cli_give(self):
        import io
        from contextlib import redirect_stdout
        from vse import cli
        if core.is_valheim_running():
            self.skipTest("Valheim is running")
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "Tester.fch")
            with open(path, "wb") as f:
                f.write(build_synthetic())
            saved_env = os.environ.get("LOCALAPPDATA")
            os.environ["LOCALAPPDATA"] = d
            out = io.StringIO()
            try:
                with redirect_stdout(out):
                    self.assertEqual(cli.main(["give", path, "misthare supreme"]), 0)
                    self.assertEqual(cli.main(["give", path, "Black Forge", "--times", "2"]), 0)
                    self.assertEqual(cli.main(["give", path, "BlackCore"]), 1)      # found, not made
                    self.assertEqual(cli.main(["give", path, "no such thing"]), 1)
            finally:
                if saved_env is None:
                    os.environ.pop("LOCALAPPDATA", None)
                else:
                    os.environ["LOCALAPPDATA"] = saved_env
            self.assertIn("added the ingredients for Misthare Supreme", out.getvalue())
            self.assertIn("added the ingredients for Black Forge x2", out.getvalue())
            cf = fch.CharacterFile.load(path)
            have = {core.item_name(i): i.stack for i in cf.items}
            self.assertEqual(have["HareMeat"], 1)
            self.assertEqual(have["MushroomJotunPuffs"], 3)
            self.assertEqual(have["BlackCore"], 10)
            self.assertEqual(have["BlackMarble"], 20)


class RealFileTest(unittest.TestCase):
    def test_real_file_roundtrip(self):
        p = os.environ.get("VSE_TEST_FCH")
        if not p:
            self.skipTest("VSE_TEST_FCH not set")
        cf = fch.CharacterFile.load(p)
        self.assertTrue(cf.hash_ok)
        self.assertTrue(cf.editable, "rebuild differs from the original bytes")
        self.assertTrue(cf.name)


if __name__ == "__main__":
    unittest.main()
