# Roadmap

Feature checklist. Marked `[x]` as items get completed.

## Done

- [x] Bot created in the Discord Portal, invited to the server, connecting
      correctly (Guild Install)
- [x] Development environment (venv, discord.py, requests, python-dotenv, Pillow)
- [x] Data source decision: local game files instead of scraping the wiki
      (see DECISIONS.md)
- [x] `tools/parse_items.py` — item parser from `media/scripts/*.txt`
      (5,105 items extracted, B42-compatible)
- [x] `tools/extract_packs.py` — icon extraction from `UI2.pack` and
      `IconsMoveables.pack` (4,988 icons extracted)
- [x] `tools/link_icons.py` — linking items to their icons (4,078 of 4,681
      linked successfully; 605 unmatched accepted as residual)
- [x] `tools/extract_translations.py` — name translations in 10 languages
      (ES, ES_CL, ES_MX, FR, DE, IT, PT, RU, PL, NL)
- [x] `/getid <name>` command — returns the item's ID
- [x] `/getinfo <name>` command — full card (name, ID, type, category,
      source, icon)
- [x] Multi-language search (exact, partial, similarity-based suggestions)
- [x] Dropdown menu when a search has multiple matches
- [x] Icon upscaling (x4, NEAREST) so they look good in the embed
- [x] `.gitignore` (excluding venv, .env, generated data, and copyrighted
      game assets)

## Pending

- [x] GitHub repository created and first commit
- [x] `README.md` / `DECISIONS.md` created and filled with the current state of the project
- [ ] Define the real folder structure of mods installed on
      IBEROZOID_Server, to extend the parser to also read their folders
      (`_source` field already prepared in the data)
- [ ] Icon extraction for mods (different format from the vanilla `.pack`
      files — likely standalone PNGs, to be confirmed)
- [ ] Deployment on IBEROZOID_Server (details still to be defined with the
      server owner)
- [ ] Automate regenerating `data/` when the game updates to a new version
      (currently a manual process)

## Ideas for later (not committed yet)

- [ ] Add mods items to the database (requires defining the folder structure of mods on IBEROZOID_Server)

- [ ] Automate the process of regenerating `data/` when the game updates to a new version (currently a manual process)