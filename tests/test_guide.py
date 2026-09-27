"""Tests for the Guide data and biome split."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_fch import build_synthetic  # noqa: E402
from vse import fch, guide, guidedata, itemdata  # noqa: E402
from vse import items as itemdb  # noqa: E402

# Ingredients the game uses that have no biome: odds and ends found in chests.
UNPLACED = {"AxeHead1", "AxeHead2", "Hook", "FireworksRocket_White"}


class GuideDataTests(unittest.TestCase):
    def test_every_ingredient_has_a_biome(self):
        used = set()
        for _, _, _, res in guidedata.RECIPES.values():
            used.update(i for i, _ in res)
        for _, _, _, res, _ in guidedata.PIECES.values():
            used.update(i for i, _ in res)
        unplaced = {i for i in used if guide.tier(i) == 0}
        self.assertEqual(unplaced, UNPLACED, "new materials in the game data need a biome in guide.MATERIAL_TIER")

    def test_every_biome_has_gear_and_food(self):
        for b in guide.BIOMES:
            secs = dict(guide.sections(b, None))
            self.assertTrue(secs["Weapons and tools"], b.name)
            self.assertTrue(secs["Food"], b.name)
            self.assertTrue(secs["Materials to find or make"], b.name)
            self.assertTrue(secs["Stations and base pieces"] or b.tier == 8, b.name)

    def test_known_placements(self):
        self.assertEqual(guide.tier("SwordBronze"), 2)
        self.assertEqual(guide.tier("ArrowIron"), 3)
        self.assertEqual(guide.tier("SwordMistwalker"), 6)
        self.assertEqual(guide.tier("CapeFeather"), 6)
        self.assertEqual(guide.tier("MeadHealthMedium"), 3, "bloodbags are Swamp")
        self.assertEqual(guide.tier("Eitr"), 6)
        self.assertEqual(guide.tier("blackforge"), 0, "pieces are not items; use ingredients_tier")
        self.assertEqual(guide.ingredients_tier(guidedata.PIECES["blackforge"][3]), 6)

    def test_recipe_text_follows_one_step(self):
        self.assertEqual(guide.recipe_text("MisthareSupreme"),
                         "1 Hare Meat, 3 Jotun Puffs, 2 Carrot @ Food Preparation Table, then Stone Oven")
        self.assertIn(", then Fermenter (makes 6)", guide.recipe_text("MeadHealthMedium"))
        self.assertTrue(guide.recipe_text("CookedHareMeat").startswith("1 Hare Meat @ Cooking Station"))
        self.assertIn(" · or 1 Scrap Iron, 2 Coal @ Smelter", guide.recipe_text("Iron"), "both smelter inputs are shown")
        self.assertEqual(guide.recipe_text("Hammer"), "3 Wood, 2 Stone @ by hand")

    def test_ingredients(self):
        self.assertEqual(guide.ingredients_for("MisthareSupreme"), [("HareMeat", 1), ("MushroomJotunPuffs", 3), ("Carrot", 2)])
        self.assertEqual(guide.ingredients_for("Eitr"), [("Softtissue", 1), ("Sap", 1)])
        self.assertEqual(guide.ingredients_for("MeadHealthMedium")[0], ("Honey", 10), "the mead base's ingredients")
        self.assertEqual(guide.ingredients_for("BlackCore"), [], "found, not made")
        self.assertEqual(guide.piece_ingredients("blackforge"), [("BlackMarble", 10), ("YggdrasilWood", 10), ("BlackCore", 5)])
        self.assertEqual(guide.find_piece("black forge"), "blackforge")
        self.assertEqual(guide.find_piece("piece_sapcollector"), "piece_sapcollector")
        self.assertIsNone(guide.find_piece("no such thing"))
        self.assertEqual(guide.needs_for(("piece", "portal_wood")), [("GreydwarfEye", 10), ("FineWood", 20), ("SurtlingCore", 2)])
        self.assertEqual(guide.name_of(("item", "SwordMistwalker")), "Mistwalker")
        self.assertEqual(guide.name_of(("piece", "blackforge")), "Black Forge")

    def test_mistlands_food_matches_the_game(self):
        secs = dict(guide.sections(guide.BIOMES[5], None))
        foods = {label: detail for label, _, detail, _ in secs["Food"]}
        self.assertIn("85 hp, 28 stam", foods["Misthare Supreme"])
        self.assertIn("26 hp, 80 stam", foods["Salad"])
        self.assertIn("85 eitr", foods["Seeker Aspic"])
        mats = {label: detail for label, _, detail, _ in secs["Materials to find or make"]}
        self.assertEqual(mats["Dvergr Extractor"], "cannot go through a portal")
        self.assertEqual(mats["Refined Eitr"], "1 Soft Tissue, 1 Sap @ Eitr Refinery")
        self.assertEqual(mats["Black Core"], "")
        swamp = dict(guide.sections(guide.BIOMES[2], None))
        mats = {label: detail for label, _, detail, _ in swamp["Materials to find or make"]}
        self.assertIn("cannot go through a portal", mats["Iron"])
        self.assertIn("Scrap Iron", mats["Iron"])
        self.assertIn("Coal @ Smelter", mats["Iron"], "the smelter's fuel is part of the cost")
        self.assertFalse([m for m in mats if m.startswith(("Mead Base", "Uncooked"))], "no intermediates")
        self.assertTrue([label for label, _, _, _ in secs["Food"] if "Mistlands" in label], "the 1.0 feast is a food")


class GuideStatusTests(unittest.TestCase):
    def setUp(self):
        H = itemdb.ITEM_NAME_TO_HASH
        data = build_synthetic(items=[fch.Item.new(H["ArrowIron"], 0, 0, stack=20)],
                               uniques=["GP_TheElder"], trophies=["TrophyEikthyr"],
                               known_recipes=[guidedata.TOKENS["SwordBronze"], guidedata.PIECES["forge"][1]],
                               known_materials=[guidedata.TOKENS["Copper"]],
                               biomes=["Meadows", "Black Forest", "Swamp"])
        self.cf = fch.CharacterFile(data)

    def test_lists_parsed_and_written_back(self):
        cf = self.cf
        self.assertTrue(cf.editable)
        self.assertEqual(cf.trophies, ["TrophyEikthyr"])
        self.assertEqual(cf.known_biomes, ["Meadows", "Black Forest", "Swamp"])
        self.assertEqual(cf.known_materials, ["$item_copper"])
        self.assertEqual(len(cf.known_recipes), 2)
        self.assertEqual(guide.furthest_biome(cf), 2)
        self.assertEqual(guide.furthest_biome(None), 0)

    def test_status(self):
        cf = self.cf
        self.assertEqual(guide.status(cf, "ArrowIron"), "in bag")
        self.assertEqual(guide.status(cf, "SwordBronze"), "can craft")
        self.assertEqual(guide.status(cf, "Copper"), "seen")
        self.assertEqual(guide.status(cf, "Bronze"), "")
        self.assertEqual(guide.status(None, "Copper"), "")
        meadows = dict(guide.sections(guide.BIOMES[0], cf))
        self.assertEqual(meadows["Boss"][0][1], "done", "trophy counts as beaten")
        forest = dict(guide.sections(guide.BIOMES[1], cf))
        self.assertEqual(forest["Boss"][0][1], "done", "guardian power counts as beaten")
        self.assertIn(("Forge", "can build", "4 Stone, 4 Coal, 10 Wood, 6 Copper", ("piece", "forge")),
                      forest["Stations and base pieces"])
        swamp = dict(guide.sections(guide.BIOMES[2], cf))
        self.assertEqual(swamp["Boss"][0], ("Bonemass", "", "10 Withered Bones at the altar", None))
        self.assertIn(("Ironhead Arrow", "in bag", "8 Wood, 1 Iron, 2 Feathers @ Forge level 2 (makes 20)",
                       ("item", "ArrowIron")), swamp["Ammo"])


if __name__ == "__main__":
    unittest.main()
