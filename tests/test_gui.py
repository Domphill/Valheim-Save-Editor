"""GUI tests. Skipped automatically where Tk cannot open a display."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import tkinter as tk
    _probe = tk.Tk()
    _probe.destroy()
    HAVE_TK = True
except Exception:  # no display, or tkinter missing
    HAVE_TK = False

from test_fch import build_synthetic, make_world  # noqa: E402
from vse import fch  # noqa: E402
from vse import items as itemdb  # noqa: E402


@unittest.skipUnless(HAVE_TK, "tkinter cannot open a display here")
class GuiTests(unittest.TestCase):
    def setUp(self):
        import vse.app as A
        self.A = A
        self.dialogs = []
        for name in ("showwarning", "showerror", "showinfo"):
            setattr(A.messagebox, name, lambda title, msg, **k: self.dialogs.append((title, msg)))
        A.messagebox.askyesno = lambda *a, **k: True
        A.messagebox.askokcancel = lambda *a, **k: True
        self.tmp = tempfile.TemporaryDirectory()
        items = [fch.Item.new(itemdb.ITEM_NAME_TO_HASH["Wood"], 0, 0, stack=20),
                 fch.Item.new(itemdb.ITEM_NAME_TO_HASH["AxeFlint"], 1, 0, quality=2, durability=200,
                              crafter_id=1, crafter_name="Tester")]
        items[1].cheated = True
        self.path = os.path.join(self.tmp.name, "Tester.fch")
        worlds = [make_world(111, map_bytes=b"\x00" * 3000, death=True), make_world(222)]
        with open(self.path, "wb") as f:
            f.write(build_synthetic(used_cheats=1, items=items, skills=[fch.Skill(1, 40, 0)], worlds=worlds))
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = A.App(self.root)

    def tearDown(self):
        self.root.destroy()
        self.tmp.cleanup()

    def test_every_tab_fits_the_window(self):
        app = self.app
        app.open_file(self.path)
        w, h = self.root.minsize()
        for tab in (app.tab_char, app.tab_inv, app.tab_skills):
            app.nb.select(tab)
            self.root.update_idletasks()
            self.assertLessEqual(self.root.winfo_reqwidth(), w, "tab content wider than the window")
            self.assertLessEqual(self.root.winfo_reqheight(), h, "tab content taller than the window")

    def test_edit_flow_through_the_widgets(self):
        app = self.app
        app.open_file(self.path)
        self.assertEqual(app.cf.name, "Tester")
        self.assertTrue(app.flag_var.get())
        # unmark the axe via the button
        app.select(1, 0)
        app.unmark_selected()
        self.assertFalse(app.by_slot[(1, 0)].cheated)
        # change the wood stack via the edit row
        app.select(0, 0)
        self.assertEqual(app.ed_stack.get(), "20")
        app.ed_stack.delete(0, "end")
        app.ed_stack.insert(0, "50")
        app.apply_selected()
        self.assertEqual(app.by_slot[(0, 0)].stack, 50)
        # add arrows with a space-insensitive name into an empty slot
        app.select(7, 3)
        app.add_query.set("arrow iron")
        app._refilter()
        self.assertEqual(app.add_selected, "ArrowIron")
        app.add_stack.delete(0, "end")
        app.add_stack.insert(0, "100")
        app.add_item()
        self.assertEqual(app.by_slot[(7, 3)].crafter_name, "Tester")
        # an ambiguous query with a pick from the list
        app.select(6, 3)
        app.add_query.set("mead")
        app._refilter()
        self.assertIsNone(app.add_selected)
        idx = app._results_names.index("MeadPoisonResist")
        app.results.selection_set(idx)
        app._pick_result()
        self.assertEqual(app.add_selected, "MeadPoisonResist")
        app.add_stack.delete(0, "end")
        app.add_stack.insert(0, "2")
        app.add_item()
        self.assertEqual(app.by_slot[(6, 3)].stack, 2)
        # clear the flag and save (the dialogs are stubbed to OK)
        app.flag_var.set(False)
        self.assertTrue(app.dirty)
        self.assertIn("*", self.root.title())
        from vse import core
        if core.is_valheim_running():
            self.skipTest("Valheim is running")
        os.environ["LOCALAPPDATA"] = self.tmp.name
        app.save()
        self.assertFalse(app.dirty)
        cf = fch.CharacterFile.load(self.path)
        self.assertEqual(cf.used_cheats, 0)
        self.assertEqual(len(cf.marked_items), 0)
        self.assertEqual(cf.item_at(0, 0).stack, 50)
        self.assertEqual(core.item_name(cf.item_at(7, 3)), "ArrowIron")
        self.assertTrue(any(t == "Saved" for t, _ in self.dialogs))
        self.assertTrue(os.path.exists(os.path.join(self.tmp.name, "ValheimSaveEditor", "history.log")))

    def test_undo_and_keyboard(self):
        app = self.app
        app.open_file(self.path)
        app.select(1, 0)
        app.unmark_selected()
        self.assertFalse(app.by_slot[(1, 0)].cheated)
        app.undo()
        self.assertTrue(app.by_slot[(1, 0)].cheated, "undo must restore the mark")
        self.assertFalse(app.dirty)
        app.flag_var.set(False)
        app._on_flag_toggle()
        self.assertEqual(app.cf.used_cheats, 0)
        app.undo()
        self.assertEqual(app.cf.used_cheats, 1)
        self.assertTrue(app.flag_var.get())
        # arrow keys move the selection when nothing has keyboard focus for typing
        app.nb.select(app.tab_inv)
        self.root.focus_set()

        class Ev:
            keysym = "Right"
        app.select(0, 0)
        app._on_arrow_key(Ev())
        self.assertEqual(app.selected, (1, 0))
        # Delete removes the selected item (confirm dialog is stubbed to yes)
        app._on_delete_key(Ev())
        self.assertIsNone(app.by_slot.get((1, 0)))
        app.undo()
        self.assertIsNotNone(app.by_slot.get((1, 0)))

    def test_checks_and_game_indicator(self):
        app = self.app
        app.open_file(self.path)
        self.assertIn("SET", app.check_labels["flag"].cget("text"))
        self.assertIn("1 marked", app.check_labels["marks"].cget("text"))
        self.assertTrue(app.game_var.get().startswith("●"))
        self.assertIn("marked", app.summary_var.get())

    def test_worlds_tab(self):
        app = self.app
        app.open_file(self.path)
        rows = app.worlds_tree.get_children()
        self.assertEqual(len(rows), 2)
        self.assertEqual(app.worlds_tree.item("111")["values"][5], "2 KB")
        app.worlds_tree.selection_set("111")
        app.clear_death_marker()
        self.assertFalse(app.cf.world(111).have_death)
        app.clear_world_map()
        self.assertIsNone(app.cf.world(111).map_data)
        app.worlds_tree.selection_set("222")
        app.forget_world()
        self.assertEqual(app.cf.world_count, 1)
        self.assertEqual(app.info_vars["worlds"].get(), "1")
        self.assertTrue(app.dirty)
        app.undo()
        self.assertEqual(app.cf.world_count, 2)
        for tab in (app.tab_worlds,):
            app.nb.select(tab)
            self.root.update_idletasks()
            w, h = self.root.minsize()
            self.assertLessEqual(self.root.winfo_reqwidth(), w)
            self.assertLessEqual(self.root.winfo_reqheight(), h)

    def test_inventory_rows_and_pockets(self):
        app = self.app
        app.open_file(self.path)
        self.assertEqual((app.rows_shown, app.rows_var.get()), (4, "4"))
        self.assertEqual(app.cells[(0, 4)].winfo_manager(), "", "row 4 is hidden for a 4-row character")
        # buy Wider Pockets through the checkbox
        app.pocket_vars[1].set(True)
        app._on_pocket_toggle(1)
        self.assertEqual((app.cf.inventory_rows, app.rows_shown, app.rows_var.get()), (5, 5, "5"))
        self.assertEqual(app.cells[(0, 4)].winfo_manager(), "grid")
        self.assertTrue(app.dirty)
        self.assertIn("5 rows", app.summary_var.get())
        # the window grew to fit the extra row
        self.root.update_idletasks()
        self.assertLessEqual(self.root.winfo_reqheight(), self.root.minsize()[1])
        # an item in the new row blocks handing the pocket back; the box reverts
        app.select(3, 4)
        app.add_query.set("arrow iron")
        app._refilter()
        app.add_item()
        self.assertIsNotNone(app.by_slot.get((3, 4)))
        app.pocket_vars[1].set(False)
        app._on_pocket_toggle(1)
        self.assertEqual(app.cf.inventory_rows, 5)
        self.assertTrue(app.pocket_vars[1].get())
        self.assertTrue(any(t == "Cannot change that" for t, _ in self.dialogs))
        # spinbox to 7, then undo back to 5
        app.rows_var.set("7")
        app._on_rows_spin()
        self.assertEqual((app.cf.inventory_rows, app.rows_shown), (7, 7))
        app.undo()
        self.assertEqual((app.cf.inventory_rows, app.rows_shown, app.rows_var.get()), (5, 5, "5"))
        self.assertTrue(app.pocket_vars[1].get())

    def test_opens_a_five_row_character(self):
        items = [fch.Item.new(itemdb.ITEM_NAME_TO_HASH["Coins"], 6, 4, stack=10)]
        path = os.path.join(self.tmp.name, "Five.fch")
        with open(path, "wb") as f:
            f.write(build_synthetic(items=items, uniques=["invrows 5", "invslot1"]))
        app = self.app
        app.open_file(path)
        self.assertEqual(app.rows_shown, 5)
        self.assertTrue(app.pocket_vars[1].get())
        self.assertFalse(app.pocket_vars[2].get())
        self.assertIn("Coins", app.cells[(6, 4)].cget("text"))
        self.assertIn("(5 rows)", app.info_vars["items"].get())
        for tab in (app.tab_char, app.tab_inv):
            app.nb.select(tab)
            self.root.update_idletasks()
            w, h = self.root.minsize()
            self.assertLessEqual(self.root.winfo_reqwidth(), w)
            self.assertLessEqual(self.root.winfo_reqheight(), h)

    def test_refill_and_repair_buttons(self):
        from vse import search
        items = [fch.Item.new(itemdb.ITEM_NAME_TO_HASH["ArrowIron"], 0, 0, stack=7),
                 fch.Item.new(itemdb.ITEM_NAME_TO_HASH["Wood"], 1, 0, stack=7),
                 fch.Item.new(itemdb.ITEM_NAME_TO_HASH["AxeFlint"], 2, 0, quality=1, durability=1)]
        path = os.path.join(self.tmp.name, "Supplies.fch")
        with open(path, "wb") as f:
            f.write(build_synthetic(items=items))
        app = self.app
        app.open_file(path)
        app.refill()
        self.assertEqual((app.by_slot[(0, 0)].stack, app.by_slot[(1, 0)].stack), (search.max_stack("ArrowIron"), 7))
        self.assertIn("Refilled 1 item", app.status.get())
        self.assertTrue(app.dirty)
        app.refill(True)
        self.assertEqual(app.by_slot[(1, 0)].stack, search.max_stack("Wood"))
        app.repair_all()
        self.assertEqual(app.by_slot[(2, 0)].durability_value, search.max_durability("AxeFlint", 1))
        app.repair_all()
        self.assertIn("Nothing to repair", app.status.get())
        app.undo()
        self.assertEqual(app.by_slot[(2, 0)].durability, 100)
        app.undo()
        app.undo()
        self.assertEqual((app.by_slot[(0, 0)].stack, app.by_slot[(1, 0)].stack), (7, 7))
        self.assertFalse(app.dirty)

    def test_nothing_to_save_is_not_written(self):
        app = self.app
        app.open_file(self.path)
        before = os.path.getmtime(self.path)
        app.save()
        self.assertEqual(os.path.getmtime(self.path), before)
        self.assertTrue(any(t == "Nothing to save" for t, _ in self.dialogs))


if __name__ == "__main__":
    unittest.main()
