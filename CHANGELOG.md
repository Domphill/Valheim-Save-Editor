# Changelog

## 0.3.0 – 2026-09-16

First public release.

- Reads and writes Valheim 1.0 character files (profile version 46, player data version 33)
  with a byte-for-byte round-trip guard: files the tool cannot reproduce exactly open read only.
- Clears the cheat flag and cheated-item marks; adds, edits and removes inventory items;
  edits skill levels.
- Added items can be stamped "Crafted by" the character, matching gear crafted in game.
- Item search by in-game name or prefab name, word order independent.
- Safety: refuses to save while Valheim runs, backs up every save, verifies the checksum,
  re-parses the result, replaces the file atomically, shows the change list before writing,
  keeps a history log and an error log.
- Undo, keyboard navigation, live game-running indicator, DPI-aware layout.
- Command-line interface for scripting and machines without a desktop.
- Tests for the file format, the editing operations, the search and the GUI; CI on Windows
  and Ubuntu; exe build with PyInstaller.
