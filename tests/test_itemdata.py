import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vse import core, fch, itemdata, search  # noqa: E402
from vse import items as itemdb  # noqa: E402


class ItemDataTests(unittest.TestCase):
    def test_table_is_consistent_with_the_hash_table(self):
        self.assertGreater(len(itemdata.ITEM_DATA), 900)
        missing = [n for n in itemdata.ITEM_DATA if n not in itemdb.ITEM_NAME_TO_HASH]
        self.assertEqual(missing, [])
        for name, d in itemdata.ITEM_DATA.items():
            self.assertEqual(len(d), 7, name)
            self.assertGreaterEqual(d[2], 1, name)
            self.assertGreaterEqual(d[5], 1, name)

    def test_known_values(self):
        self.assertEqual(search.label("SwordIron"), "Iron Sword")
        self.assertEqual(search.label("RoundLog"), "Corewood")
        self.assertEqual(search.label("BeltStrength"), "Megingjord")
        self.assertEqual(search.max_stack("ArrowIron"), 100)
        self.assertEqual(search.max_stack("Iron"), 30)
        self.assertEqual(search.max_stack("Sausages"), 20)
        self.assertEqual(search.max_stack("Coins"), 999)
        self.assertEqual(search.max_quality("SwordIron"), 4)
        self.assertEqual(search.max_durability("SwordIron", 1), 200.0)
        self.assertEqual(search.max_durability("SwordIron", 3), 300.0)
        self.assertEqual(search.max_durability("HelmetBronze", 3), 1400.0)   # matches a real q3 helmet: 140000/100
        self.assertEqual(search.category("SwordIron"), "weapon")
        self.assertEqual(search.category("Sausages"), "food")
        self.assertEqual(search.category("BeltStrength"), "accessory")
        self.assertEqual(search.category("ArrowIron"), "ammo")
        self.assertIsNone(search.max_stack("NotAnItem"))

    def test_search_uses_categories_and_game_names(self):
        self.assertEqual(search.search("iron sword")[0], "SwordIron")
        self.assertEqual(search.search("ironhead")[0], "ArrowIron")
        self.assertIn("SwordIron", search.search("iron", category="weapon"))
        self.assertNotIn("Iron", search.search("iron", category="weapon"))
        self.assertNotIn("TreasureChest_swamp", search.searchable_names())

    def test_limits_enforced_and_durability_defaulted(self):
        from test_fch import build_synthetic
        cf = fch.CharacterFile(build_synthetic(items=[fch.Item.new(1, 0, 0)], skills=[fch.Skill(1, 1, 0)]))
        helmet = core.add_item(cf, "bronze helmet", 1, 0, quality=2)
        self.assertEqual(helmet.durability_value, 1200.0)
        arrows = core.add_item(cf, "ArrowIron", 2, 0, stack=100)
        self.assertEqual(arrows.durability_value, 100.0)
        with self.assertRaises(ValueError):
            core.add_item(cf, "Iron", 3, 0, stack=31)
        with self.assertRaises(ValueError):
            core.add_item(cf, "SwordIron", 3, 0, quality=5)
        with self.assertRaises(ValueError):
            core.update_item(arrows, stack=101)
        core.update_item(helmet, quality=4, durability=core.default_durability("HelmetBronze", 4))
        self.assertEqual(helmet.durability_value, 1600.0)


if __name__ == "__main__":
    unittest.main()
