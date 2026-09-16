"""Tkinter GUI for the Valheim Save Editor."""
import datetime
import os
import subprocess
import sys
import tkinter as tk
import traceback
from tkinter import filedialog, messagebox, ttk

from . import __version__, core, fch, icon, paths, search

APP_TITLE = "Valheim Save Editor"
PAD = {"padx": 6, "pady": 3}

C_EMPTY = "#eeeeee"
C_ITEM = "#ffffff"
C_MARKED = "#f6b3b3"
C_SELECTED = "#3d7bd9"
C_SELECTED_MARKED = "#c0392b"
C_RING = "#d5d5d5"
C_RING_HOVER = "#7fa8e6"
UNDO_LIMIT = 50
GAME_POLL_MS = 3000


class App:
    def __init__(self, root):
        self.root = root
        self.font = ("Segoe UI", 10) if sys.platform == "win32" else ("TkDefaultFont", 10)
        self.bold = (self.font[0], 10, "bold")
        self.small = (self.font[0], 9)
        root.option_add("*Font", self.font)
        self._style()
        try:
            self._icon = icon.make_photo(32, master=root)
            root.iconphoto(True, self._icon)
        except Exception:
            self._icon = None
        root.title("%s %s" % (APP_TITLE, __version__))

        self.cf = None
        self.path = None
        self.dirty = False
        self.selected = None
        self.cells = {}
        self.by_slot = {}
        self.skill_rows = {}
        self.all_items = search.searchable_names()
        self.add_selected = None
        self._results_names = []
        self._undo = []
        self._game_running = None

        self._build()
        # Size the window from what the widgets need, so scaled displays never clip a control.
        root.update_idletasks()
        w = max(1000, root.winfo_reqwidth() + 24)
        h = max(700, root.winfo_reqheight() + 24)
        root.geometry("%dx%d" % (w, h))
        root.minsize(w, h)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.bind_all("<Control-s>", lambda e: self.save())
        root.bind_all("<Control-o>", lambda e: self.ask_open())
        root.bind_all("<Control-z>", lambda e: self.undo())
        root.bind_all("<Delete>", self._on_delete_key)
        for key in ("Left", "Right", "Up", "Down"):
            root.bind_all("<%s>" % key, self._on_arrow_key)
        self._poll_game()
        for a in sys.argv[1:]:
            if a.lower().endswith((".fch", ".old")) and os.path.exists(a):
                self.open_file(a)
                break

    # -- style ------------------------------------------------------------

    def _style(self):
        s = ttk.Style(self.root)
        try:
            if "vista" in s.theme_names():
                s.theme_use("vista")
        except tk.TclError:
            pass
        s.configure(".", font=self.font)
        s.configure("TButton", padding=(10, 4))
        s.configure("Accent.TButton", font=self.bold)
        s.configure("TNotebook.Tab", padding=(14, 6))
        s.configure("TLabelframe.Label", font=self.bold)
        s.configure("Hint.TLabel", foreground="#666666", font=self.small)
        s.configure("Muted.TLabel", foreground="#666666")
        s.configure("Bold.TLabel", font=self.bold)
        s.configure("Good.TLabel", foreground="#1b7f3b", font=self.bold)
        s.configure("Bad.TLabel", foreground="#b00020", font=self.bold)

    # -- layout -----------------------------------------------------------

    def _build(self):
        bar = ttk.Frame(self.root)
        bar.pack(fill="x", padx=6, pady=(6, 3))
        ttk.Button(bar, text="Open…", command=self.ask_open).pack(side="left")
        self.found_btn = ttk.Menubutton(bar, text="Found characters")
        self.found_menu = tk.Menu(self.found_btn, tearoff=0, postcommand=self._fill_found)
        self.found_btn["menu"] = self.found_menu
        self.found_btn.pack(side="left", padx=(4, 0))
        ttk.Button(bar, text="Reload", command=self.reload).pack(side="left", padx=(4, 0))
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=8, pady=2)
        self.save_btn = ttk.Button(bar, text="Save", style="Accent.TButton", command=self.save)
        self.save_btn.pack(side="left")
        self.undo_btn = ttk.Button(bar, text="Undo", command=self.undo)
        self.undo_btn.pack(side="left", padx=(4, 0))
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=8, pady=2)
        ttk.Button(bar, text="Restore backup…", command=self.restore_backup).pack(side="left")
        ttk.Button(bar, text="Backups folder", command=self.open_backups).pack(side="left", padx=(4, 0))
        self.file_var = tk.StringVar(value="No file open")
        ttk.Label(bar, textvariable=self.file_var, style="Bold.TLabel").pack(side="left", padx=14)

        status = ttk.Frame(self.root, relief="sunken")
        status.pack(side="bottom", fill="x")
        self.status = tk.StringVar(value="Open a character file (.fch) to begin.")
        ttk.Label(status, textvariable=self.status, anchor="w").pack(side="left", fill="x", expand=True, padx=6, pady=2)
        self.game_var = tk.StringVar(value="")
        self.game_lbl = ttk.Label(status, textvariable=self.game_var, style="Muted.TLabel")
        self.game_lbl.pack(side="right", padx=8)

        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=6, pady=(3, 6))
        self.nb = nb
        self.tab_char = ttk.Frame(nb)
        self.tab_inv = ttk.Frame(nb)
        self.tab_skills = ttk.Frame(nb)
        self.tab_worlds = ttk.Frame(nb)
        nb.add(self.tab_char, text="Character")
        nb.add(self.tab_inv, text="Inventory")
        nb.add(self.tab_skills, text="Skills")
        nb.add(self.tab_worlds, text="Worlds")
        self._build_char()
        self._build_inv()
        self._build_skills()
        self._build_worlds()

    def _build_char(self):
        f = self.tab_char
        info = ttk.LabelFrame(f, text="Character")
        info.pack(fill="x", **PAD)
        self.info_vars = {}
        fields = [("Name", "name"), ("Player ID", "pid"), ("Worlds visited", "worlds"),
                  ("Max health", "health"), ("Max stamina", "stamina"), ("Items", "items"), ("Skills", "skills")]
        for i, (label, key) in enumerate(fields):
            r, c = divmod(i, 2)
            ttk.Label(info, text=label + ":", style="Muted.TLabel").grid(row=r, column=c * 2, sticky="e", padx=(8, 4), pady=2)
            var = tk.StringVar(value="")
            ttk.Label(info, textvariable=var).grid(row=r, column=c * 2 + 1, sticky="w", padx=(0, 24), pady=2)
            self.info_vars[key] = var

        checks = ttk.LabelFrame(f, text="Checks")
        checks.pack(fill="x", **PAD)
        self.check_labels = {}
        for key in ("hash", "roundtrip", "flag", "marks"):
            lbl = ttk.Label(checks, text="", style="Muted.TLabel")
            lbl.pack(anchor="w", padx=8, pady=1)
            self.check_labels[key] = lbl
        self.flag_var = tk.BooleanVar(value=False)
        self.flag_chk = ttk.Checkbutton(checks, text="Cheat flag set (m_usedCheats). Untick to clear it on save.",
                                        variable=self.flag_var, command=self._on_flag_toggle)
        self.flag_chk.pack(anchor="w", padx=8, pady=(6, 6))

        note = ("Achievements are blocked while any of these is true: the cheat flag is set, a marked "
                "item is in the inventory, the world has cheated modifiers, or the game is modded. "
                "This tool handles the first two. Items left in chests or on the ground keep their "
                "marks, and picking one up later brings the temporary cheat state back.\n\n"
                "Steam Cloud characters are edited in place; Steam uploads the edited file on the next "
                "launch. If Steam shows a cloud conflict, keep the local file.\n\n"
                "Backups, the save history and the error log live in:  %s" % paths.app_dir())
        ttk.Label(f, text=note, wraplength="675p", style="Hint.TLabel", justify="left").pack(anchor="w", padx=8, pady=8)

    def _build_inv(self):
        f = self.tab_inv
        top = ttk.Frame(f)
        top.pack(fill="x", padx=6, pady=(6, 0))
        self.summary_var = tk.StringVar(value="")
        ttk.Label(top, textvariable=self.summary_var, style="Muted.TLabel").pack(side="left")

        grid = ttk.Frame(f)
        grid.pack(anchor="w", padx=6, pady=(2, 4))
        ttk.Label(grid, text="Hotbar  (keys 1 to 8)", style="Hint.TLabel").grid(row=0, column=0, columnspan=8, sticky="w")
        ttk.Label(grid, text="Inventory", style="Hint.TLabel").grid(row=2, column=0, columnspan=8, sticky="w", pady=(6, 0))
        for y in range(fch.INVENTORY_H):
            for x in range(fch.INVENTORY_W):
                lbl = tk.Label(grid, text="", font=self.small, width=13, height=3, relief="flat", bd=0,
                               highlightthickness=2, highlightbackground=C_RING, bg=C_EMPTY,
                               anchor="center", justify="center", wraplength="69p", cursor="hand2")
                lbl.grid(row=1 if y == 0 else y + 2, column=x, padx=2, pady=2)
                lbl.bind("<Button-1>", lambda e, x=x, y=y: self.select(x, y))
                lbl.bind("<Enter>", lambda e, l=lbl: l.config(highlightbackground=C_RING_HOVER))
                lbl.bind("<Leave>", lambda e, x=x, y=y: self._ring(x, y))
                self.cells[(x, y)] = lbl

        side = ttk.LabelFrame(f, text="Selected slot")
        side.pack(fill="x", **PAD)
        det = ttk.Frame(side)
        det.pack(anchor="w", padx=4, pady=(2, 4))
        self.detail_vars = {}
        fields = [("Item", "item"), ("Stack", "stack"), ("Crafted by", "crafter"), ("Marked", "marked"),
                  ("Prefab", "prefab"), ("Quality", "quality"), ("Durability", "dur"), ("Equipped", "equipped")]
        for i, (label, key) in enumerate(fields):
            r, c = divmod(i, 4)
            ttk.Label(det, text=label + ":", style="Muted.TLabel").grid(row=r, column=c * 2, sticky="e", padx=(6, 4), pady=1)
            var = tk.StringVar(value="")
            ttk.Label(det, textvariable=var, width=22 if key in ("item", "prefab", "crafter") else 10,
                      anchor="w").grid(row=r, column=c * 2 + 1, sticky="w", pady=1)
            self.detail_vars[key] = var
        self.detail_var = tk.StringVar(value="Click a slot.")
        ttk.Label(side, textvariable=self.detail_var, style="Hint.TLabel").pack(anchor="w", padx=8)
        edit = ttk.Frame(side)
        edit.pack(anchor="w", **PAD)
        self.ed_stack = self._small_entry(edit, "Stack:", "")
        self.ed_quality = self._small_entry(edit, "Quality:", "")
        self.ed_dur = self._small_entry(edit, "Durability:", "")
        ttk.Button(edit, text="Max", width=5, command=self._fill_edit_durability).pack(side="left", padx=(0, 8))
        ttk.Button(edit, text="Apply to selected", command=self.apply_selected).pack(side="left")
        ttk.Button(edit, text="Unmark", command=self.unmark_selected).pack(side="left", padx=(12, 0))
        ttk.Button(edit, text="Remove item", command=self.remove_selected).pack(side="left", padx=(4, 0))
        ttk.Button(edit, text="Clear all marks", command=self.clear_all).pack(side="left", padx=(4, 0))
        ttk.Label(side, text="Red tiles are marked as cheated. Durability is the number the game shows. "
                             "Arrow keys move the selection, Delete removes the item, Ctrl+Z undoes. "
                             "Nothing is written until you press Save.",
                  style="Hint.TLabel", wraplength="705p", justify="left").pack(anchor="w", padx=8, pady=(0, 4))

        add = ttk.LabelFrame(f, text="Add an item to the selected empty slot")
        add.pack(fill="x", **PAD)
        left = ttk.Frame(add)
        left.pack(side="left", anchor="n", **PAD)
        srow = ttk.Frame(left)
        srow.pack(fill="x")
        ttk.Label(srow, text="Search:").pack(side="left")
        self.add_query = tk.StringVar()
        self.add_entry = ttk.Entry(srow, textvariable=self.add_query, width=24)
        self.add_entry.pack(side="left", padx=(4, 6))
        self.add_cat = ttk.Combobox(srow, state="readonly", width=11, values=[t for _, t in search.CATEGORIES])
        self.add_cat.current(0)
        self.add_cat.pack(side="left")
        self.add_cat.bind("<<ComboboxSelected>>", lambda e: self._refilter())
        self.add_entry.bind("<KeyRelease>", lambda e: self._refilter())
        self.add_entry.bind("<Down>", self._focus_results)
        self.add_entry.bind("<Return>", lambda e: self.add_item())
        self.results = tk.Listbox(left, height=6, width=46, exportselection=False, activestyle="dotbox",
                                  highlightthickness=1, highlightbackground=C_RING, relief="flat")
        self.results.pack(fill="x", pady=(3, 0))
        self.results.bind("<<ListboxSelect>>", lambda e: self._pick_result())
        self.results.bind("<Return>", lambda e: self.add_item())
        self.results.bind("<Double-1>", lambda e: self.add_item())

        right = ttk.Frame(add)
        right.pack(side="left", anchor="n", fill="x", expand=True, **PAD)
        self.add_selected_var = tk.StringVar(value="Type to search, then pick from the list.")
        ttk.Label(right, textvariable=self.add_selected_var, style="Bold.TLabel",
                  wraplength="330p", justify="left").pack(anchor="w")
        row = ttk.Frame(right)
        row.pack(anchor="w", pady=(4, 0))
        self.add_stack = self._small_entry(row, "Stack:", "1")
        self.add_quality = self._small_entry(row, "Quality:", "1")
        self.add_quality.bind("<KeyRelease>", lambda e: self._fill_add_durability())
        self.add_dur = self._small_entry(row, "Durability:", "100")
        row2 = ttk.Frame(right)
        row2.pack(anchor="w", pady=(4, 0))
        self.add_crafted = tk.BooleanVar(value=True)
        self.add_crafted_chk = ttk.Checkbutton(row2, text="Crafted by this character", variable=self.add_crafted)
        self.add_crafted_chk.pack(side="left")
        ttk.Button(row2, text="Add", style="Accent.TButton", command=self.add_item).pack(side="left", padx=(12, 0))
        hint = ("Names, stack limits and durability come from the game files. Type an in-game name in any "
                "word order (iron sword, scrap iron, corewood, megingjord). Durability fills in with the "
                "item's maximum for the chosen quality. Untick 'Crafted by' for raw materials, which never "
                "show a crafter.")
        ttk.Label(right, text=hint, style="Hint.TLabel", wraplength="330p", justify="left").pack(anchor="w", pady=(6, 0))
        self._refilter()

    def _small_entry(self, parent, label, default):
        ttk.Label(parent, text=label).pack(side="left")
        e = ttk.Entry(parent, width=6)
        e.insert(0, default)
        e.pack(side="left", padx=(2, 8))
        return e

    def _build_skills(self):
        f = self.tab_skills
        top = ttk.Frame(f)
        top.pack(fill="x", **PAD)
        ttk.Label(top, text="Add skill:").pack(side="left")
        self.add_skill_combo = ttk.Combobox(top, state="readonly", width=24)
        self.add_skill_combo.pack(side="left", padx=4)
        ttk.Button(top, text="Add", command=self.add_skill).pack(side="left")
        ttk.Label(f, text="Level 0 to 100. Experience is progress toward the next level and is left as it is. "
                          "Levels are read when you press Save.",
                  style="Hint.TLabel").pack(side="bottom", anchor="w", **PAD)
        body = ttk.Frame(f)
        body.pack(fill="both", expand=True, **PAD)
        canvas = tk.Canvas(body, highlightthickness=0, background="#ffffff")
        vsb = ttk.Scrollbar(body, orient="vertical", command=canvas.yview)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.configure(yscrollcommand=vsb.set)
        self.skills_canvas = canvas
        self.skills_box = ttk.Frame(canvas)
        self._skills_win = canvas.create_window((0, 0), window=self.skills_box, anchor="nw")
        self.skills_box.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(self._skills_win, width=e.width))
        hdr = ttk.Frame(self.skills_box)
        hdr.pack(fill="x", padx=4, pady=(4, 2))
        for txt, w in (("Skill", 18), ("Level", 8), ("", 24), ("Experience", 12)):
            ttk.Label(hdr, text=txt, width=w, style="Bold.TLabel").pack(side="left", padx=4)

    def _build_worlds(self):
        f = self.tab_worlds
        ttk.Label(f, text="Every world this character has been in keeps a block of data on the character: "
                          "the explored map, the logout position, the bed spawn and the death marker. "
                          "Names are matched against the world saves found on this PC; worlds hosted "
                          "elsewhere show their ID only.",
                  style="Hint.TLabel", wraplength="705p", justify="left").pack(anchor="w", padx=8, pady=(8, 4))
        cols = ("world", "uid", "spawn", "logout", "death", "map")
        self.worlds_tree = ttk.Treeview(f, columns=cols, show="headings", height=8, selectmode="browse")
        for col, text, width, anchor in (("world", "World", 240, "w"), ("uid", "World ID", 130, "w"),
                                          ("spawn", "Bed spawn", 90, "center"), ("logout", "Logout position", 140, "center"),
                                          ("death", "Death marker", 140, "center"), ("map", "Explored map", 110, "center")):
            self.worlds_tree.heading(col, text=text)
            self.worlds_tree.column(col, width=width, anchor=anchor, stretch=(col == "world"))
        self.worlds_tree.pack(fill="x", padx=8, pady=4)
        btns = ttk.Frame(f)
        btns.pack(anchor="w", padx=8, pady=4)
        ttk.Button(btns, text="Forget world", command=self.forget_world).pack(side="left")
        ttk.Button(btns, text="Clear map", command=self.clear_world_map).pack(side="left", padx=(6, 0))
        ttk.Button(btns, text="Clear death marker", command=self.clear_death_marker).pack(side="left", padx=(6, 0))
        ttk.Label(f, text="Forget world: the next login there spawns at the start stone with an unexplored map; "
                          "inventory, skills and gear are untouched. Clear map: exploration only, position and bed "
                          "stay. Clear death marker: removes the skull from the map. Nothing is written until "
                          "you press Save.",
                  style="Hint.TLabel", wraplength="705p", justify="left").pack(anchor="w", padx=8, pady=(2, 8))

    def _refresh_worlds(self):
        tree = self.worlds_tree
        keep = tree.selection()
        tree.delete(*tree.get_children())
        if not self.cf:
            return
        names = core.world_names()
        for w in self.cf.worlds:
            logout = "%.0f, %.0f" % (w.logout_xyz[0], w.logout_xyz[2]) if w.have_logout else "none"
            death = "%.0f, %.0f" % (w.death_xyz[0], w.death_xyz[2]) if w.have_death else "none"
            size = "%d KB" % (w.map_size // 1024) if w.map_size else "none"
            tree.insert("", "end", iid=str(w.uid), values=(core.world_label(w.uid, names), w.uid,
                                                             "yes" if w.have_spawn else "no", logout, death, size))
        for iid in keep:
            if tree.exists(iid):
                tree.selection_set(iid)
        self.info_vars["worlds"].set(str(len(self.cf.worlds)))

    def _selected_world(self):
        if not self.cf:
            messagebox.showerror("No file", "Open a character file first.")
            return None
        sel = self.worlds_tree.selection()
        if not sel:
            messagebox.showerror("No world", "Click a world in the list first.")
            return None
        return int(sel[0])

    def _world_action(self, fn, verb, question):
        uid = self._selected_world()
        if uid is None:
            return
        label = core.world_label(uid)
        if not messagebox.askyesno(verb, question % label):
            return
        self._push_undo()
        try:
            fn(self.cf, uid)
        except ValueError as e:
            self._undo.pop()
            messagebox.showerror("Cannot do that", str(e))
            return
        self._mark_dirty()
        self._refresh_worlds()
        self.status.set("%s: %s. Save to write the file." % (verb, label))

    def forget_world(self):
        self._world_action(core.forget_world, "Forget world",
                           "Forget %s?\n\nThe explored map, logout position, bed spawn and death marker for that "
                           "world are removed from this character. The next login there starts at the start stone.")

    def clear_world_map(self):
        self._world_action(core.clear_world_map, "Clear map",
                           "Clear the explored map for %s?\n\nPosition, bed spawn and death marker stay.")

    def clear_death_marker(self):
        self._world_action(core.clear_death_marker, "Clear death marker",
                           "Remove the death marker for %s?")

    # -- game state -----------------------------------------------------------

    def _poll_game(self):
        running = core.is_valheim_running()
        if running != self._game_running:
            self._game_running = running
            if running:
                self.game_var.set("●  Valheim is running: saving blocked")
                self.game_lbl.configure(style="Bad.TLabel")
                self.save_btn.state(["disabled"])
            else:
                self.game_var.set("●  Valheim closed: saving allowed")
                self.game_lbl.configure(style="Good.TLabel")
                self.save_btn.state(["!disabled"])
        self.root.after(GAME_POLL_MS, self._poll_game)

    # -- file handling ------------------------------------------------------

    def _fill_found(self):
        m = self.found_menu
        m.delete(0, "end")
        files = paths.find_characters()
        if not files:
            m.add_command(label="No character files found", state="disabled")
            return
        for p, label in files:
            m.add_command(label="%s   (%s)" % (os.path.basename(p), label),
                          command=lambda p=p: self.open_file(p))

    def ask_open(self):
        if not self._confirm_discard():
            return
        dirs = paths.character_dirs()
        initial = dirs[0][0] if dirs else os.path.expanduser("~")
        p = filedialog.askopenfilename(title="Open a Valheim character file", initialdir=initial,
                                       filetypes=[("Valheim character", "*.fch"),
                                                  ("Game's previous save", "*.old"),
                                                  ("All files", "*.*")])
        if p:
            self.open_file(p)

    def open_file(self, path):
        if self.path != path and not self._confirm_discard():
            return
        try:
            cf = fch.CharacterFile.load(path)
        except Exception as e:
            messagebox.showerror("Cannot open", "%s\n\n%s" % (path, e))
            return
        self.cf = cf
        self.path = path
        self.dirty = False
        self.selected = None
        self._undo = []
        self.file_var.set(os.path.basename(path))
        self.status.set(path)
        self._set_title()
        self._populate()
        if not cf.hash_ok:
            messagebox.showwarning("Checksum", "This file's checksum does not match its contents. The game "
                                   "would reject it as it is. Saving from here rewrites a valid checksum.")
        if not cf.editable:
            messagebox.showwarning("Read only", "Rebuilding this file without changes did not reproduce it "
                                   "byte for byte, so editing is disabled for safety. You can still look.")
        elif core.is_valheim_running():
            messagebox.showwarning("Valheim is running", "You can look, but saving is blocked until the game "
                                   "is closed. The game rewrites the character file on exit.")

    def reload(self):
        if self.path and self._confirm_discard():
            self.open_file(self.path)

    def _confirm_discard(self):
        if not self.dirty:
            return True
        return messagebox.askyesno("Unsaved changes", "Discard the unsaved changes?")

    def on_close(self):
        if self._confirm_discard():
            self.root.destroy()

    def _set_title(self):
        name = os.path.basename(self.path) + " - " if self.path else ""
        self.root.title("%s%s%s %s" % ("*" if self.dirty else "", name, APP_TITLE, __version__))

    def _mark_dirty(self):
        self.dirty = True
        self._set_title()

    def open_backups(self):
        d = paths.backup_dir()
        os.makedirs(d, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(d)
        else:
            subprocess.Popen(["xdg-open", d])

    def restore_backup(self):
        if not self.path:
            messagebox.showerror("No file", "Open a character file first.")
            return
        backups = core.list_backups(self.path, paths.backup_dir())
        initial = paths.backup_dir() if backups else os.path.dirname(self.path)
        p = filedialog.askopenfilename(title="Choose a backup to restore over %s" % os.path.basename(self.path),
                                       initialdir=initial,
                                       filetypes=[("Backups", "*.bak"), ("Character files", "*.fch *.old"),
                                                  ("All files", "*.*")])
        if not p:
            return
        if not messagebox.askyesno("Restore", "Replace\n%s\nwith\n%s ?\n\nThe current file is backed up first."
                                   % (self.path, p)):
            return
        try:
            core.make_backup(self.path, paths.backup_dir())
            core.restore(self.path, p)
        except Exception as e:
            messagebox.showerror("Not restored", str(e))
            return
        self.dirty = False
        self.open_file(self.path)
        messagebox.showinfo("Restored", "Restored %s" % os.path.basename(p))

    # -- undo -----------------------------------------------------------------

    def _push_undo(self):
        if self.cf is None:
            return
        self._undo.append(self.cf.to_bytes())
        del self._undo[:-UNDO_LIMIT]

    def undo(self):
        if not self.cf or not self._undo:
            self.status.set("Nothing to undo.")
            return
        snap = self._undo.pop()
        restored = fch.CharacterFile(snap)
        restored.original = self.cf.original
        restored.hash_ok = self.cf.hash_ok
        self.cf = restored
        n = int.from_bytes(self.cf.original[:4], "little", signed=True)
        self.dirty = self.cf.build_body() != self.cf.original[4:4 + n]
        self._set_title()
        self._populate()
        self.status.set("Undone. %d step(s) left to undo." % len(self._undo))

    # -- populate -----------------------------------------------------------

    def _populate(self):
        cf = self.cf
        v = self.info_vars
        v["name"].set(cf.name)
        v["pid"].set(str(cf.player_id))
        v["worlds"].set(str(cf.world_count))
        if cf.has_data:
            v["health"].set("%.0f" % cf.max_health)
            v["stamina"].set("%.0f" % cf.max_stamina)
            v["items"].set("%d" % len(cf.items))
            v["skills"].set("%d" % len(cf.skills))
        else:
            for k in ("health", "stamina", "items", "skills"):
                v[k].set("no player data yet")
        self.flag_var.set(bool(cf.used_cheats))
        self.add_crafted_chk.config(text="Crafted by %s" % cf.name)
        self._refresh_checks()
        self._refresh_inventory()
        self._rebuild_skill_rows()
        self._refresh_worlds()

    def _refresh_checks(self):
        cf = self.cf
        if not cf:
            return
        def show(key, ok, good, bad):
            self.check_labels[key].configure(text=("✓  " + good) if ok else ("✗  " + bad),
                                             style="Good.TLabel" if ok else "Bad.TLabel")
        show("hash", cf.hash_ok, "Checksum matches", "Checksum mismatch, repaired on save")
        show("roundtrip", cf.editable, "Round-trip check passed, editing enabled",
             "Round-trip check failed, file is read only")
        show("flag", not cf.used_cheats, "Cheat flag clear", "Cheat flag SET, achievements disabled")
        self.flag_chk.configure(text="Cheat flag is set (m_usedCheats). Untick it to clear the flag on save."
                                if cf.used_cheats else "Cheat flag is clear. Tick this only to set it.")
        n = len(cf.marked_items)
        show("marks", n == 0, "No marked items in the inventory", "%d marked item(s) in the inventory" % n)

    # -- inventory ------------------------------------------------------------

    def _refresh_inventory(self):
        self.by_slot = {}
        if self.cf:
            for it in self.cf.items:
                self.by_slot[(it.x, it.y)] = it
        for (x, y) in self.cells:
            self._render(x, y)
        self._update_summary()
        self._update_detail()

    def _ring(self, x, y):
        self.cells[(x, y)].config(highlightbackground=C_SELECTED if (x, y) == self.selected else C_RING)

    def _render(self, x, y):
        lbl = self.cells[(x, y)]
        it = self.by_slot.get((x, y))
        if it is None:
            text, bg, fg = "", C_EMPTY, "#888888"
        else:
            parts = [search.label(core.item_name(it))]
            if it.stack > 1:
                parts.append("x%d" % it.stack)
            if it.quality > 1:
                parts.append("q%d" % it.quality)
            if it.equipped:
                parts.append("(equipped)")
            text = "\n".join(parts)
            bg, fg = (C_MARKED, "#5b0a0a") if it.cheated else (C_ITEM, "#000000")
        if (x, y) == self.selected:
            bg = C_SELECTED_MARKED if (it is not None and it.cheated) else C_SELECTED
            fg = "#ffffff"
        lbl.config(text=text, bg=bg, fg=fg)
        self._ring(x, y)

    def select(self, x, y):
        prev = self.selected
        self.selected = (x, y)
        if prev:
            self._render(*prev)
        self._render(x, y)
        self._update_detail()

    def _set_edit_fields(self, it):
        for ent, val in ((self.ed_stack, it.stack if it else ""),
                         (self.ed_quality, it.quality if it else ""),
                         (self.ed_dur, self._fmt(it.durability_value) if it else "")):
            ent.delete(0, "end")
            ent.insert(0, str(val))

    def _update_detail(self):
        d = self.detail_vars
        it = self.by_slot.get(self.selected) if self.selected else None
        self._set_edit_fields(it)
        if self.selected is None:
            for var in d.values():
                var.set("")
            self.detail_var.set("Click a slot.")
            return
        if it is None:
            for var in d.values():
                var.set("")
            self.detail_var.set("Slot %d,%d is empty. Use the panel below to add an item here." % self.selected)
            return
        prefab = core.item_name(it)
        d["item"].set(search.label(prefab))
        d["prefab"].set("%s, %s" % (prefab, search.type_name(prefab)) if search.info(prefab) else prefab)
        d["stack"].set(str(it.stack))
        d["quality"].set(str(it.quality))
        d["dur"].set("%.1f" % it.durability_value)
        d["crafter"].set(it.crafter_name or "(none)")
        d["marked"].set("YES" if it.cheated else "no")
        d["equipped"].set("yes" if it.equipped else "no")
        extra = []
        if it.variant:
            extra.append("variant %d" % it.variant)
        if it.custom:
            extra.append("%d custom data entries" % len(it.custom))
        self.detail_var.set("Slot %d,%d" % self.selected + (", " + ", ".join(extra) if extra else ""))

    def _update_summary(self):
        if not self.cf or not self.cf.has_data:
            self.summary_var.set("")
            return
        items = self.cf.items
        free = fch.INVENTORY_W * fch.INVENTORY_H - len(items)
        self.summary_var.set("%d items   ·   %d marked   ·   %d equipped   ·   %d free slots"
                             % (len(items), len(self.cf.marked_items), sum(1 for i in items if i.equipped), free))

    def _need_item(self):
        if not self.cf:
            messagebox.showerror("No file", "Open a character file first.")
            return None
        if self.selected is None or self.by_slot.get(self.selected) is None:
            messagebox.showerror("No item", "Click an item slot first.")
            return None
        return self.by_slot[self.selected]

    def _stack_ok(self, name, stack):
        """Soft warning for unknown items only; known items are limited by the game's own numbers."""
        if search.max_stack(name) is not None or stack <= 100:
            return True
        return messagebox.askyesno("Large stack", "The game's stack limit for this item is not known and "
                                   "nothing except coins stacks above 100 in Valheim. The game may not "
                                   "show %d in one slot.\n\nContinue anyway?" % stack)

    def _fill_edit_durability(self):
        it = self.by_slot.get(self.selected) if self.selected else None
        if it is None:
            return
        try:
            q = int(self.ed_quality.get().strip() or it.quality)
        except ValueError:
            q = it.quality
        self.ed_dur.delete(0, "end")
        self.ed_dur.insert(0, self._fmt(core.default_durability(core.item_name(it), q)))

    def _fill_add_durability(self):
        if not self.add_selected:
            return
        try:
            q = int(self.add_quality.get().strip() or 1)
        except ValueError:
            q = 1
        self.add_dur.delete(0, "end")
        self.add_dur.insert(0, self._fmt(core.default_durability(self.add_selected, q)))

    def _typing(self):
        w = self.root.focus_get()
        return isinstance(w, (tk.Entry, ttk.Entry, ttk.Combobox, tk.Listbox, tk.Text, tk.Spinbox))

    def _on_arrow_key(self, event):
        if self._typing() or self.nb.select() != str(self.tab_inv) or self.selected is None:
            return
        dx = {"Left": -1, "Right": 1}.get(event.keysym, 0)
        dy = {"Up": -1, "Down": 1}.get(event.keysym, 0)
        x = min(fch.INVENTORY_W - 1, max(0, self.selected[0] + dx))
        y = min(fch.INVENTORY_H - 1, max(0, self.selected[1] + dy))
        self.select(x, y)
        return "break"

    def _on_delete_key(self, event):
        if self._typing() or self.nb.select() != str(self.tab_inv):
            return
        if self.selected and self.by_slot.get(self.selected) is not None:
            self.remove_selected()
            return "break"

    def apply_selected(self):
        it = self._need_item()
        if it is None:
            return
        try:
            stack = int(self.ed_stack.get().strip() or it.stack)
            quality = int(self.ed_quality.get().strip() or it.quality)
            dur = float((self.ed_dur.get().strip() or str(it.durability_value)).replace(",", "."))
            if not self._stack_ok(core.item_name(it), stack):
                return
            self._push_undo()
            core.update_item(it, stack, quality, dur)
        except ValueError as e:
            if self._undo:
                self._undo.pop()
            messagebox.showerror("Bad value", str(e) or "Stack and Quality must be whole numbers, Durability a number.")
            return
        self._mark_dirty()
        self._refresh_inventory()
        self.status.set("Updated %s. Save to write the file." % search.label(core.item_name(it)))

    def unmark_selected(self):
        it = self._need_item()
        if it is None:
            return
        if not it.cheated:
            self.status.set("That item is not marked.")
            return
        self._push_undo()
        it.cheated = False
        self._mark_dirty()
        self._refresh_inventory()
        self._refresh_checks()
        self.status.set("Removed the mark from %s. Save to write the file." % search.label(core.item_name(it)))

    def remove_selected(self):
        it = self._need_item()
        if it is None:
            return
        name = search.label(core.item_name(it))
        if not messagebox.askyesno("Remove item", "Remove %s from slot %d,%d?" % ((name,) + self.selected)):
            return
        self._push_undo()
        core.remove_item(self.cf, it)
        self._mark_dirty()
        self._refresh_inventory()
        self._refresh_checks()
        self.status.set("Removed %s. Save to write the file." % name)

    def clear_all(self):
        if not self.cf:
            return
        if not self.cf.marked_items:
            self.status.set("No marked items to clear.")
            return
        self._push_undo()
        n = core.clear_marks(self.cf)
        self._mark_dirty()
        self._refresh_inventory()
        self._refresh_checks()
        self.status.set("Removed %d mark(s). Save to write the file." % n)

    def _refilter(self):
        cat = search.CATEGORIES[self.add_cat.current()][0] if self.add_cat.current() >= 0 else "all"
        names = search.search(self.add_query.get(), self.all_items, limit=200, category=cat)
        self._results_names = names
        self.results.delete(0, "end")
        for n in names:
            lab = search.label(n)
            self.results.insert("end", "%s   [%s]" % (lab, n) if lab != n else n)
        if len(names) == 1:
            self.results.selection_set(0)
            self._set_add_selected(names[0])
        else:
            self._set_add_selected(None)

    def _set_add_selected(self, name):
        self.add_selected = name
        if name:
            parts = ["Selected: %s   [%s]" % (search.label(name), name)]
            if search.info(name):
                parts.append("%s · stacks to %d · quality up to %d · durability %g"
                             % (search.type_name(name), search.max_stack(name), search.max_quality(name),
                                search.max_durability(name, 1)))
            self.add_selected_var.set("\n".join(parts))
            self._fill_add_durability()
        elif self._results_names:
            self.add_selected_var.set("%d matches. Pick one from the list." % len(self._results_names))
        else:
            self.add_selected_var.set("No item matches that. Try another word.")

    def _pick_result(self):
        idx = self.results.curselection()
        if idx:
            self._set_add_selected(self._results_names[idx[0]])

    def _focus_results(self, event=None):
        if self._results_names:
            self.results.focus_set()
            self.results.selection_clear(0, "end")
            self.results.selection_set(0)
            self.results.activate(0)
            self._pick_result()
        return "break"

    def add_item(self):
        if not self.cf:
            messagebox.showerror("No file", "Open a character file first.")
            return
        if self.selected is None:
            messagebox.showerror("No slot", "Click an empty slot first.")
            return
        if self.by_slot.get(self.selected) is not None:
            messagebox.showerror("Slot in use", "That slot already holds an item. Pick an empty one.")
            return
        try:
            stack = int(self.add_stack.get() or "1")
            quality = int(self.add_quality.get() or "1")
            dur = float((self.add_dur.get() or "100").replace(",", "."))
            if stack < 1 or quality < 1 or dur < 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Bad value", "Stack and Quality must be whole numbers of 1 or more; "
                                 "Durability must be 0 or more.")
            return
        name = self.add_selected or search.resolve(self.add_query.get(), self.all_items)
        if not name:
            messagebox.showerror("No item", "Type a name in the search box and pick an item from the list.")
            return
        if not self._stack_ok(name, stack):
            return
        self._push_undo()
        try:
            it = core.add_item(self.cf, name, self.selected[0], self.selected[1], stack, quality, dur,
                               crafted_by_character=bool(self.add_crafted.get()))
        except ValueError as e:
            self._undo.pop()
            messagebox.showerror("Cannot add", str(e))
            return
        self._mark_dirty()
        self._refresh_inventory()
        self.status.set("Added %s x%d at %d,%d. Save to write the file." % (search.label(name), stack, it.x, it.y))

    # -- character ------------------------------------------------------------

    def _on_flag_toggle(self):
        if not self.cf:
            return
        self._push_undo()
        self.cf.used_cheats = 1 if self.flag_var.get() else 0
        self._mark_dirty()
        self._refresh_checks()

    # -- skills ---------------------------------------------------------------

    def _rebuild_skill_rows(self):
        for row in self.skill_rows.values():
            row["frame"].destroy()
        self.skill_rows = {}
        if self.cf:
            for s in sorted(self.cf.skills, key=lambda s: s.name.lower()):
                self._add_skill_row(s)
        self._refresh_add_skill_combo()

    def _add_skill_row(self, s):
        frame = ttk.Frame(self.skills_box)
        frame.pack(fill="x", padx=4, pady=1)
        ttk.Label(frame, text=s.name, width=18, anchor="w").pack(side="left", padx=4)
        var = tk.StringVar(value=self._fmt(s.level))
        ent = ttk.Entry(frame, textvariable=var, width=8)
        ent.pack(side="left", padx=4)
        bar = ttk.Progressbar(frame, length=170, maximum=100, value=s.level)
        bar.pack(side="left", padx=4)
        ttk.Label(frame, text=self._fmt(s.acc), width=12, anchor="w").pack(side="left", padx=4)
        ttk.Button(frame, text="Remove", command=lambda t=s.type: self.del_skill(t)).pack(side="left", padx=6)

        def typed(event=None, var=var, bar=bar):
            self._mark_dirty()
            try:
                bar["value"] = max(0.0, min(100.0, float(var.get().replace(",", "."))))
            except ValueError:
                pass
        ent.bind("<KeyRelease>", typed)
        self.skill_rows[s.type] = {"frame": frame, "level": var, "name": s.name}

    @staticmethod
    def _fmt(v):
        return ("%.3f" % v).rstrip("0").rstrip(".")

    def _refresh_add_skill_combo(self):
        present = set(self.skill_rows)
        missing = [fch.SKILLS[t] for t in sorted(fch.SKILLS) if t not in present]
        self.add_skill_combo["values"] = missing
        if missing:
            self.add_skill_combo.current(0)
        else:
            self.add_skill_combo.set("")

    def add_skill(self):
        if not self.cf:
            return
        name = self.add_skill_combo.get()
        if not name:
            return
        stype = fch.SKILL_TYPES[name]
        if stype in self.skill_rows:
            return
        self._push_undo()
        try:
            s = core.set_skill(self.cf, stype, 1.0, 0.0)
        except ValueError as e:
            self._undo.pop()
            messagebox.showerror("Cannot add", str(e))
            return
        self._add_skill_row(s)
        self._refresh_add_skill_combo()
        self._mark_dirty()

    def del_skill(self, stype):
        self._push_undo()
        core.remove_skill(self.cf, stype)
        row = self.skill_rows.pop(stype)
        row["frame"].destroy()
        self._refresh_add_skill_combo()
        self._mark_dirty()

    def _apply_skill_entries(self):
        for stype, row in self.skill_rows.items():
            txt = row["level"].get().strip().replace(",", ".")
            try:
                lvl = float(txt)
            except ValueError:
                raise ValueError("Level of %s is not a number: %r" % (row["name"], txt))
            if lvl != lvl or lvl < 0 or lvl > 100:
                raise ValueError("Level of %s must be between 0 and 100." % row["name"])
            core.set_skill(self.cf, stype, lvl)

    # -- save -----------------------------------------------------------------

    def save(self):
        if not self.cf:
            messagebox.showerror("No file", "Open a character file first.")
            return
        try:
            self._apply_skill_entries()
        except ValueError as e:
            messagebox.showerror("Bad value", str(e))
            return
        self.cf.used_cheats = 1 if self.flag_var.get() else 0
        changes = core.describe_changes(self.cf)
        if not changes and self.cf.hash_ok:
            messagebox.showinfo("Nothing to save", "No changes have been made.")
            return
        shown = changes[:40]
        if len(changes) > 40:
            shown.append("… and %d more" % (len(changes) - 40))
        if not changes:
            shown = ["(no content changes; the checksum will be repaired)"]
        if not messagebox.askokcancel("Save changes?", "About to write %s with these changes:\n\n%s\n\n"
                                      "A backup is made first." % (os.path.basename(self.path), "\n".join(shown))):
            return
        try:
            backup = core.save(self.cf, self.path, paths.backup_dir())
        except core.SaveBlocked as e:
            messagebox.showerror("Not saved", str(e))
            return
        except Exception as e:
            messagebox.showerror("Not saved", "%s: %s" % (type(e).__name__, e))
            return
        self.dirty = False
        messagebox.showinfo("Saved", "Saved %s\n\nBackup: %s\n\nChecksum written and verified."
                            % (os.path.basename(self.path), backup))
        self.open_file(self.path)


def _log_error(exc, val, tb):
    """Tk callback exception hook: log the traceback and tell the user where it went."""
    text = "".join(traceback.format_exception(exc, val, tb))
    log = paths.error_log()
    try:
        os.makedirs(paths.app_dir(), exist_ok=True)
        with open(log, "a", encoding="utf-8") as f:
            f.write("\n==== %s  %s %s\n%s" % (datetime.datetime.now().isoformat(timespec="seconds"),
                                                APP_TITLE, __version__, text))
    except OSError:
        pass
    sys.stderr.write(text)
    try:
        messagebox.showerror("Error", "Something went wrong:\n%s\n\nDetails were written to:\n%s" % (val, log))
    except Exception:
        pass


def main():
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # crisp text on high-DPI screens
        except Exception:
            pass
    root = tk.Tk()
    root.report_callback_exception = _log_error
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
