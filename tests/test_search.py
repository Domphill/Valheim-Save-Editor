import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vse import search  # noqa: E402
from vse import items as itemdb  # noqa: E402


class SearchTests(unittest.TestCase):
    def test_every_display_name_belongs_to_a_real_prefab(self):
        missing = sorted(n for n in search.DISPLAY_NAMES if n not in itemdb.ITEM_NAME_TO_HASH)
        self.assertEqual(missing, [], "display names for prefabs that do not exist: %s" % missing)

    def test_camel_split(self):
        self.assertEqual(search.split_camel("ArmorTrollLeatherChest"), "Armor Troll Leather Chest")
        self.assertEqual(search.split_camel("BowFineWood"), "Bow Fine Wood")
        self.assertEqual(search.split_camel("TrophyDeer"), "Trophy Deer")
        self.assertEqual(search.label("ArrowIron"), "Iron arrow")

    def test_word_order_and_display_names(self):
        self.assertEqual(search.search("iron sword")[0], "SwordIron")
        self.assertEqual(search.search("sword iron")[0], "SwordIron")
        self.assertEqual(search.search("scrap iron")[0], "IronScrap")
        self.assertEqual(search.search("core wood")[0], "RoundLog")
        self.assertEqual(search.search("megingjord")[0], "BeltStrength")
        self.assertEqual(search.search("troll tunic")[0], "ArmorTrollLeatherChest")
        self.assertIn("ArrowIron", search.search("arrow"))
        self.assertEqual(search.search("zzzz-nothing"), [])

    def test_ranking_prefers_exact_then_prefix(self):
        self.assertEqual(search.search("Iron")[0], "Iron")
        self.assertEqual(search.search("wood")[0], "Wood")
        self.assertTrue(search.search("iron arr")[0] in ("ArrowIron",))

    def test_resolve(self):
        self.assertEqual(search.resolve("SwordIron"), "SwordIron")
        self.assertEqual(search.resolve("iron sword"), "SwordIron")
        self.assertEqual(search.resolve("Iron Arrow"), "ArrowIron")
        self.assertEqual(search.resolve("arrowiron"), "ArrowIron")
        self.assertIsNone(search.resolve("arrow"))      # ambiguous
        self.assertIsNone(search.resolve(""))

    def test_hidden_prefabs_are_not_searchable(self):
        self.assertFalse(any(n.lower().startswith(("sfx_", "vfx_")) for n in search.searchable_names()))


if __name__ == "__main__":
    unittest.main()
