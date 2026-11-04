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
- [x] `README.md` / `DECISIONS.md` / `ROADMAP.md` written and kept up to date
      with the mod support, vehicles and deployment work

### Vanilla item data
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

### Mod item data (Steam Workshop mods on IBEROZOID_Server)
- [x] Located the mods on the server and mapped their real folder structure
      (several mods per Workshop ID, version folders, `common/`)
- [x] `tools/parse_items_mods.py` — items and loose icons from the mods
      (111 mods with items, 6,505 items in total)
- [x] `tools/link_icons_mods.py` — linking mod items to their icons, ignoring
      case and falling back to vanilla icons (4,540 own icons, 300 reused
      vanilla icons, 1,310 with no icon, 355 not found)
- [x] `tools/extract_translations_mods.py` — mod item names in the supported
      languages (19 mods, 3,125 items)

### Vehicle data
- [x] `tools/parse_vehicles.py` — vanilla and mod vehicles in one run, with
      names in the 10 languages
- [x] Engine stats read from the top level of each vehicle (engine force,
      max speed, mass, seats, engine quality and loudness)
- [x] `template!` inheritance followed, so variants and liveries get their
      parent's stats (231 vehicles gained their engine data)
- [x] Mod cover image (`preview.png`) copied once per mod for the vehicle card
- [x] Burnt and smashed wrecks excluded (89)
- [x] Trailers excluded with a switch (`REMOLQUES = False`): 37 excluded by
      missing engine/seats or by name
- [x] Result: 595 vehicles (152 vanilla, 443 from mods), all with complete
      stats

### Bot features
- [x] `/getitemid <name>` — returns the item's ID
- [x] `/getiteminfo <name>` — full card (name, ID, type, category, origin,
      icon)
- [x] `/getvehicleid <name>` — returns the vehicle's ID
- [x] `/getvehicleinfo <name>` — card with name, ID, origin, engine stats and
      mod cover image
- [x] Multi-language search (exact, partial, similarity-based suggestions)
- [x] Search by name only, never by internal ID (documented in DECISIONS.md)
- [x] Search matches every word in any order, also against the mod's name
- [x] Dropdown menu when a search has multiple matches (sorted, capped at 25,
      with a notice when there are more, and each option showing its ID)
- [x] Dropdown result posted as a public message
- [x] Vanilla and mod data merged in memory at startup; `vehicles.json` is
      optional
- [x] Icon upscaling (x4, NEAREST) so item icons look good in the embed

### Deployment
- [x] Bot cloned and running on the IBEROZOID_Server test machine over SSH,
      kept outside `serverfiles/` and `Zomboid/`
- [x] Vanilla item data copied to the server (the dedicated server has no
      `UI2.pack`)

## Pending

- [ ] Test the four commands in Discord after every data regeneration
      (the vehicle commands are the newest)
- [ ] Keep the bot running after closing SSH (systemd service, or
      screen/tmux as a quick option) — not decided yet
- [ ] Move from the test machine to the real IBEROZOID_Server
- [ ] Recover icons for the 355 mod items with an icon name but no file
      (probably inside mod `.pack` files or subfolders; `extract_packs.py`
      could be extended)
- [ ] Automate regenerating `data/` when the game or the mod list changes
      (currently a manual process)
- [ ] `README.md` / `DECISIONS.md` reviewed and adjusted to your liking

## Ideas for later (not committed yet)

- [ ] Bring trailers back as vehicles (set `REMOLQUES = True` and review what
      the name and stats rules let through)
- [ ] Show crafting recipe in `/getiteminfo` when the item is craftable
      (using `pz-item-browser`'s `parse_recipes.py` as a reference)
- [ ] Translated name in the dropdown menu itself, matching the language
      the user searched in
- [ ] Read mod item names stored in older `.txt` translation files (only
      `ItemName.json` is read today for items)
- [ ] A command or message to tell users when the data was last regenerated