# Technical decisions

Log of decisions made during development, with the reasoning behind each
one. Goal: months from now, be able to remember *why* something was done a
certain way, not just *what* was done.

## Language and libraries

**Decision:** Python + `discord.py`, instead of Node.js + `discord.js`.

**Why:** a gentler learning curve for someone with no prior experience
shipping a real project to production, plus a mature and well-documented
library.

---

## Item data source

**Initial decision (dropped):** scrape `pzwiki.net/wiki/PZwiki:Item_list`
with `requests` + `BeautifulSoup4`.

**Why it was dropped:** the site has active Cloudflare protection (a "Just a
moment..." challenge) that effectively blocks automated requests, on top of
what its `robots.txt` already restricted (which also explicitly blocks AI
bots). Trying to bypass Cloudflare would have added a lot of complexity
(automated browser) and moved into more questionable ethical/legal
territory than simply not respecting a robots.txt.

**Final decision:** parse the game's own definition files directly
(`media/scripts/*.txt`), which is the original source the wiki itself pulls
its data from.

**Why this is an improvement, not just a workaround:**
- No scraping issues (local files, no network involved).
- No legal/ethical ambiguity (content from a legitimately installed game,
  for personal use).
- More reliable than the wiki: the actual source of truth for the game,
  with no transcription errors or staleness after a new patch.

---

## Item parser (`tools/parse_items.py`)

**Source:** adapted from the `parse_items.py` script in the `pz-item-browser`
GitHub repository (author: KevinLinTW1021), originally written for Project
Zomboid build 41.

**B42 compatibility:** the parser doesn't depend on specific field names (it
syntactically looks for `module`/`item` blocks and splits any
`key = value` line), so it works the same on B41 and B42. The only part that
did depend on a specific field name (the final console stats) was adjusted
for B42: the type field changed from `Type` to `ItemType`, and now carries
namespaced values (`base:clothing` instead of `clothing`).

**Addition over the original:** comments (`//`) are stripped before looking
for `module`/`item` blocks, to prevent a commented-out block from being
detected as a real item.

---

## Icon extraction (`tools/extract_packs.py`)

**Source:** adapted from `extract_packs.py` in the same `pz-item-browser`
repository. The `.pack` format is verified against the game's own source
code (`GameWindow.java`, `TexturePackPage.java`), not blind reverse
engineering.

**Packs used:** only `UI2.pack` and `IconsMoveables.pack` (they contain the
inventory icons). Everything else is skipped (`Tiles*.pack`,
`JumboTrees*.pack`, etc. — world textures, not item icons), both for size
(hundreds of MB of unneeded data) and relevance.

---

## Linking items to their icons (`tools/link_icons.py`)

**Problem:** the name stored in an item's `Icon=` field doesn't directly
match the keys in the extracted icon index.

**Matching rules applied, in order:**
1. The `UI2.pack` atlas prefixes all its names with `Item_`
   (`Item_Pocketwatch`), while the script only stores the plain name
   (`Pocketwatch`).
2. Some items with variants (clothing in different colors/materials) don't
   have an exact generic icon — only specific variants
   (`Item_Trousers_BrownLeather`). In that case, the first available variant
   is used, prioritizing one containing "Generic" in its name.
3. Weapons don't use the `Icon=` field at all, but `IconsForTexture=`
   (possibly with several variants separated by `;`, e.g.
   `Hammer;Hammer_Forged`) — `Icon` is tried first, and `IconsForTexture` is
   used as a fallback if it's missing.

**Final result, accepted as-is:** 4,078 items linked to an icon, 422 with no
icon field in the script at all (assumed to have no real graphical
representation), and 605 with an icon field but no match in the index
(accepted as residual — the Discord embed is shown without an image in
those cases, instead of failing or blocking the response).

---

## Translations (`tools/extract_translations.py`)

**Source:** `media/lua/shared/Translate/<LANGUAGE>/ItemName.json` from the
game's own installation (JSON format in B42; B41 used a different,
Lua-style format). Each entry's key is already the full `_full_id` (e.g.
`Base.Hammer`), matching what `parse_items.py` generates, so no lookup by
internal name is needed.

**Supported languages:** ES, ES_CL, ES_MX, FR, DE, IT, PT, RU, PL, NL.

**Why this source instead of translating by hand or with AI:** these are
the game's own official translations, already reviewed and consistent with
the terminology the player actually sees on screen — same reasoning as
using the game's own scripts instead of the wiki for item data.

---

## Mod support: where the data comes from

**Decision:** read the mods the server has already downloaded, in
`~/serverfiles/steamapps/workshop/content/108600/<WorkshopID>/mods/<mod_id>/`,
instead of listing mods by hand or reading the `WorkshopItems=` line of the
server `.ini`.

**Why:** the folder on disk is the real, current set of mods the server
runs. It avoids keeping a second list in sync (the `.ini` has ~190 entries)
and it lets the scripts discover what each mod actually contains.

**Structure found (it varies between mods, so the scripts don't assume one
layout):**
- A Workshop ID can hold several mods, so processed mod folders (184) are
  more than Workshop IDs (147).
- A mod can have several version folders (`42.0`, `42.13`...). For items,
  only the **highest** version is read, to avoid duplicates.
- Shared files may live in `common/` instead of the version folder.
- `mod.info` gives the readable name (`name=`) and the internal id (`id=`).
  Each mod item stores both: `_source` (internal id) and `_source_name`
  (readable name, the one shown as "Origin" in the embed).

**Result:** 111 mods add items (6,505 items in total); 70 contain no items
(vehicles reskins, UI, pure Lua...); 3 had no readable `mod.info`.

**Reuse:** the parsing code is the same one adapted from `pz-item-browser`
for vanilla (see above), applied to each mod's `media/scripts`.

---

## Mod icons (`tools/link_icons_mods.py`)

**Difference from vanilla:** mod icons are loose PNG files in
`media/textures/` (also under `common/`), not packed in `.pack` files, so no
extraction step is needed. They are copied to `data/icons_mods/` and follow
the same `Item_` prefix convention as vanilla.

**Rules, in order:**
1. Look in `data/icons_mods/`, **ignoring case**. Mods are usually authored
   on Windows, where `Item_Foo.png` and `item_foo.png` are the same file; the
   server is Linux, which tells them apart.
2. If not found, look in the **vanilla icon index**: many mods reference
   base-game icons without shipping them.
3. `Icon = na` (also `none`/`null`) is a marker some authors use for "no
   icon" and is treated as having no icon, not as a missing file.

**Result:** 4,540 items with the mod's own icon, 300 reusing a vanilla icon,
1,310 with no icon (field missing or `na`), 355 with an icon name but no file.

**The 355 are accepted for now.** Likely causes (not verified): icons inside
mod `.pack` files, or in subfolders the copy step does not read.
`extract_packs.py` already understands the format, so this is an extension,
not new work from scratch.

---

## Mod translations (`tools/extract_translations_mods.py`)

**Decision:** read mod item names only for the **same languages already
supported for vanilla**; any other language a mod ships is ignored on
purpose.

**Why a generic search:** the folder layout differs a lot between mods
(`media/lua/shared/Translate/`, `media/shared/Translate/` without `lua`,
all-lowercase `translate/es/itemname.json`, the same translations repeated
in several version folders). Instead of assuming a path, the script finds any
folder named `Translate` (case-insensitive) and any `ItemName.json` inside it
(case-insensitive), and merges what it finds.

**Result:** 19 mods have translations in the supported languages, covering
3,125 items.

**Known gap:** mods that keep their names in older `.txt` translation files
are not read.

---

## Vanilla icons come from a client install, not from the server

**Finding:** the dedicated server (LinuxGSM) has the game scripts and the
vanilla translations, but **not** `UI2.pack` or the other texture packs
(only the mods' `.pack` files are present). A headless server does not need
UI textures.

**Decision:** generate the vanilla icons on a full client install and copy
`data/icons/`, `data/icon_index.json` and `data/items.json` to the server
(done with WinSCP). The mod data is generated on the server itself.

---

## Where the bot lives on the server

**Decision:** its own folder in the user's home directory, outside
`serverfiles/` and `Zomboid/`.

**Why:** LinuxGSM manages those two folders and may overwrite them on game
updates. A project placed inside could be lost without warning.

---

## Bot scope: two separate commands

**Decision:** `/getid` returns only the ID; `/getinfo` returns the full card
(name, image, type, category, source).

**Why:** different use cases — quickly copying an ID for an admin command,
versus looking up an item's full details. A single command that always
showed everything would be slower to use for the most common case (just the
ID).

---

## Search behaviour

**Search by name, not by ID.** The bot matches the display name, its
translations, and the mod's name. It never matches the internal ID. Many
items have an ID that looks nothing like their name (a vehicle part's ID
starts with the vehicle code, its name says "Hood"), and players think in
names. This was clarified during testing because it was easy to assume the
opposite.

**Multiple matches:** when a search matches several items (e.g. "Trousers"),
the bot shows a dropdown (`discord.ui.Select`) for the user to choose from,
instead of automatically picking one or asking the user to be more specific.

**Improvements made after testing with mods:**
- Mods produce many near-identical names (a single vehicle mod has dozens of
  parts containing the same model name). Matching a literal phrase was too
  strict, so now **every word** of the query must appear, in any order, in
  the item's names or in its mod name.
- Discord limits a dropdown to 25 options. Results are now **sorted
  alphabetically** and the message says how many matched in total when there
  are more than 25, so the user knows to add words instead of silently
  missing items.

**Public result after choosing:** the dropdown is an ephemeral message
(visible only to who ran the command) to avoid cluttering the channel. The
first version edited that message with the result, so the result was private
too, and it looked like "mod items are private" because mods more often fall
into the multiple-match path. The chosen item is now sent as a **new public
message**.

---

## Out of scope (for now)

- **Crafting recipes:** the `pz-item-browser` repository also includes
  `parse_recipes.py`, which would allow showing how an item is crafted. It
  was decided not to include this in the first version — the bot only
  reports on the item itself. Noted as a possible future feature.
- **Remaining mod icons (355 items):** see "Mod icons" above.
- **Mod translations in older `.txt` formats:** see "Mod translations"
  above.
- **Keeping the bot running 24/7** (systemd service vs screen/tmux): not
  decided or set up yet. Currently the bot is started by hand from an SSH
  session.
- **Automatic regeneration of `data/`** when the game or the mod list
  changes: still a manual process.

---

## What is (and is not) in the repository

**Not versioned:** `venv/`, `.env`, everything generated in `data/`
(vanilla and mod JSON files, icon folders), local copies of game assets
(`.pack` files, copyrighted), and editor files (`.vscode/`,
`*.code-workspace`).

**Why the generated data is excluded:** it is derived and can be recreated by
running the scripts in `tools/` (see the README). The repository holds the
recipe, not the output. The icons also come from copyrighted game files.

**Consequence:** a fresh clone has no `data/` and no `.env`; the bot will
not start until both are created (a missing `.env` shows up as
`expected token to be a str, received NoneType`).