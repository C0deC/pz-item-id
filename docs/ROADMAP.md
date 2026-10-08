# Roadmap

Feature checklist. Marked `[x]` as items get completed.

## Done

### Bot and environment
- [x] Bot created in the Discord Portal, invited to the server, connecting
      correctly (Guild Install)
- [x] Development environment (venv, discord.py, requests, python-dotenv, Pillow)
- [x] GitHub repository created and first commit pushed
- [x] `.gitignore` (excluding venv, .env, editor files, generated data, and
      copyrighted game assets)
- [x] `README.md` / `DECISIONS.md` / `ROADMAP.md` written and updated with the
      mod support and deployment work

### Vanilla data
- [x] Data source decision: local game files instead of scraping the wiki
      (see DECISIONS.md)
- [x] `tools/parse_items_vanilla.py` — item parser from `media/scripts/*.txt`
      (5,105 items extracted, B42-compatible)
- [x] `tools/extract_packs.py` — icon extraction from `UI2.pack` and
      `IconsMoveables.pack` (4,988 icons extracted)
- [x] `tools/link_icons.py` — linking items to their icons (4,078 of 4,681
      linked successfully; 605 unmatched accepted as residual)
- [x] `tools/extract_translations.py` — name translations in 10 languages
      (ES, ES_CL, ES_MX, FR, DE, IT, PT, RU, PL, NL)

### Mod data (Steam Workshop mods on IBEROZOID_Server)
- [x] Located the mods on the server and mapped their real folder structure
      (several mods per Workshop ID, version folders, `common/`)
- [x] `tools/parse_items_mods.py` — items and loose icons from the mods
      (111 mods with items, 6,505 items in total)
- [x] `tools/link_icons_mods.py` — linking mod items to their icons, ignoring
      case and falling back to vanilla icons (4,540 own icons, 300 reused
      vanilla icons, 1,310 with no icon, 355 not found)
- [x] `tools/extract_translations_mods.py` — mod item names in the supported
      languages (19 mods, 3,125 items)

### Bot features
- [x] `/getid <name>` command — returns the item's ID
- [x] `/getinfo <name>` command — full card (name, ID, type, category,
      origin, icon)
- [x] Multi-language search (exact, partial, similarity-based suggestions)
- [x] Search by name only, never by internal ID (documented in DECISIONS.md)
- [x] Search matches every word in any order, also against the mod's name
- [x] Dropdown menu when a search has multiple matches (sorted, capped at 25,
      with a notice when there are more)
- [x] Dropdown result posted as a public message
- [x] Vanilla and mod data merged in memory at startup
- [x] Icon upscaling (x4, NEAREST) so they look good in the embed

### Deployment
- [x] Bot cloned and running on the IBEROZOID_Server test machine over SSH
- [x] Vanilla data copied to the server (the dedicated server has no
      `UI2.pack`)

## Pending

- [ ] Keep the bot running after closing SSH (systemd service, or
      screen/tmux as a quick option) — not decided yet
- [ ] Recover icons for the 355 mod items with an icon name but no file
      (probably inside mod `.pack` files or subfolders; `extract_packs.py`
      could be extended)
- [ ] Automate regenerating `data/` when the game or the mod list changes
      (currently a manual process)
- [ ] `README.md` / `DECISIONS.md` reviewed and adjusted to your liking

## Ideas for later (not committed yet)

- [ ] Show crafting recipe in `/getinfo` when the item is craftable
      (using `pz-item-browser`'s `parse_recipes.py` as a reference)
- [ ] Translated name in the dropdown menu itself, matching the language
      the user searched in
- [ ] Read mod item names stored in older `.txt` translation files (only
      `ItemName.json` is read today)
- [ ] A command or message to tell users when the data was last regenerated