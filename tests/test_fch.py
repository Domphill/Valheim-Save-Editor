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


def build_synthetic(name="Tester", player_id=1234567890, used_cheats=0, items=(), skills=(), has_data=True):
    """Build a minimal but structurally complete 1.0 profile the parser accepts."""
    def i32(v): return struct.pack("<i", v)
    def f32(v): return struct.pack("<f", v)
    def i64(v): return struct.pack("<q", v)
    fdict0 = i32(0)
    bucket = b"\0" * (4 * fch.STATS_COUNT) + fdict0 * 3 + i32(0) + fdict0 * 5
    body = i32(fch.PROFILE_VERSION) + i32(fch.STATS_COUNT) + i32(1) + bucket
    body += b"\x01" + i32(0)  # first_spawn, no worlds
    body += fch.write_str(name) + i64(player_id) + fch.write_str("")
    body += bytes([used_cheats]) + i64(1700000000) + (b"\x01" if has_data else b"\x00")
    if has_data:
        blob = i32(fch.PLAYERDATA_VERSION) + f32(25) + f32(25) + f32(50) + f32(0)
        blob += fch.write_str("") + f32(0) + i32(0)
        blob += struct.pack("<H", len(items)) + b"".join(it.to_bytes() for it in items)
        blob += i32(0) * 8 + fch.write_str("") + fch.write_str("") + b"\0" * 24 + i32(0) + i32(0)
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
        core.update_item(it, stack=40, quality=2, durability=75.5)
        back = fch.Item.parse(fch.Reader(it.to_bytes()))
        self.assertEqual((back.stack, back.quality, back.durability, back.crafter_name), (40, 2, 7550, "Tester"))
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
