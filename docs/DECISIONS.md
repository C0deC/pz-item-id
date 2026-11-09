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

## Bot scope: four commands

**Decision:** two pairs of commands, one for items and one for vehicles.
Within each pair, the `...id` command returns only the ID and the `...info`
command returns the full card.

| Command | Returns |
|---|---|
| `/getitemid` | the item's full ID |
| `/getiteminfo` | name, ID, type, category, origin, icon |
| `/getvehicleid` | the vehicle's full ID |
| `/getvehicleinfo` | name, ID, origin, engine force, max speed, base weight, seats, storage, mod cover image |

**Why ID and info are separate:** different use cases — quickly copying an ID
for an admin command, versus looking up the full details. A single command
that always showed everything would be slower to use for the most common case
(just the ID).

**Why items and vehicles are separate:** they have different data and
different IDs, and mixing ~11,000 items with ~600 vehicles in one search
would flood the dropdown with irrelevant results. The commands were first
called `/getid` and `/getinfo` (and `/getvehicle` for vehicles) and were
renamed so that the item/vehicle split is explicit in the command name.

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

**ID shown under each dropdown option:** several results can have exactly
the same name (for example, the front and rear doors of a vehicle mod are
both called "Door"). Each option therefore shows its full ID as a
description, so they can be told apart.

---

## Vehicles: where the data comes from

**Decision:** read vehicles from the same game and mod files as the items,
with a dedicated script (`tools/parse_vehicles.py`) that handles vanilla and
mods in one run.

**Where they are:**
- Vanilla: `media/scripts/generated/vehicles/` (not `scripts/vehicles/`; the
  folder name was found by searching, not assumed). The dedicated server has
  them, unlike the UI textures.
- Mods: `media/scripts/` inside the latest version folder and `common/`, as
  for items.

**ID:** `Module.ScriptName`, the same format as items (e.g.
`Base.70barracuda`). Mod vehicles also live in `module Base`.

**Readable name:** the script has no name. It is in the translations, under
the key `IGUI_VehicleName<ScriptName>` (e.g. `IGUI_VehicleName70barracuda`).
Vanilla uses JSON translation files, but some mods still use the legacy
`.txt` format (`key = "value"`, sometimes with a missing closing quote), so
the script reads both formats and tolerates the broken quote. Languages are
the same 10 supported for items.

**Vehicles with no English name:** 21 (mostly delivery-van liveries). They are
found by their script name instead, and the dropdown shows their ID.

---

## Vehicle inheritance (`template!`)

**Problem:** the first run left 171 vehicles with no engine data. Looking at
one (`PickUpTruckLightsFossoil`) showed why: it declares
`template! = PickUpTruckLights` and only overrides the texture, model and
seats. Everything else is inherited.

**Decision:** copy the missing stats from the parent vehicle (or from a
`template vehicle` block), following the chain if the parent also inherits.
What a vehicle defines itself always wins over what it inherits. The 2,843
`template vehicle` blocks are read only as a data source and never appear in
the final list.

**A bug worth remembering:** a vehicle can have the same name as the template
it inherits from (`vehicle StepVan` inheriting `template! = StepVan`). The
first version looked the parent up by name, found the vehicle itself, and the
chain stopped there, leaving 46 vans without an engine. The fix is to skip
the element itself when looking for its parent, so it falls through to the
template.

**Result:** 231 vehicles gained their engine data through inheritance, and
there are no unresolved `template!` references.

---

## Vehicle stats and image

**Stats:** `engineForce`, `maxSpeed`, `mass`, `seats`, `engineQuality` and
`engineLoudness` are read from the top level of the vehicle block and saved in
`vehicles.json`. Nested blocks (model, skin, wheels, parts) contain their own
`key = value` lines and would otherwise overwrite the real values.

**What the card shows:** engine force, max speed, base weight, seats and
storage. The weight is the `mass` value and is labelled "Peso Base" because
adding upgrades to a vehicle increases its weight. Engine quality and engine
loudness are still in the data but were taken out of the card on purpose:
they are not useful when looking up a vehicle.

**They are not horsepower.** They are the game's internal values with no real
units, so the embed calls the first one "engine force" and adds a footer
saying so. They are useful to compare vehicles with each other.

**Engine force is shown divided by 10.** The script of the HMMWV holds 4451
and the game shows 445.1, so the card divides the script value by 10
(`DIVISOR_FUERZA_MOTOR` at the top of `bot.py`; setting it to 1 shows the raw
script value). It was checked against that vehicle in the game and applied to
every vehicle on the assumption that the game does the same conversion for
all of them.

**Image:** there is no picture of each individual vehicle in the game files.
The `ui/vehicles` folder of the mod examined only held a mechanics overlay,
and the vanilla icons with "vehicle" in their name are UI elements (fuel and
engine gauges, slot icons). The `Shell` textures are the paint map of the 3D
model, not a picture of the vehicle.

**Decision:** for vehicles from a mod, use the mod's own `preview.png` (the
one named in `poster=` in `mod.info`), shrunk to 512 px and stored once per
mod in `data/vehicle_previews/`. Vanilla vehicles get no image. The embed
footer says "Image: mod cover" because in a mod with several vehicles the
cover may show a different one.

---

## Vehicle storage

**Where it comes from:** each vehicle declares its parts (`part TruckBed`,
`part Seat*`, `part GloveBox`...). A part that can hold items has a
`container { ... }` block. The parts are not all written in the vehicle's own
script, so they are resolved in this order: the vehicle it inherits from
(`template!`), the templates it includes (`template = Trunk/part/TruckBed`),
and its own parts, where the wildcard `part Seat*` applies to every seat.

**Where the capacity comes from**, in order:
1. A `capacity` written in the container (vans have 130 or 160, mods give
   their own trunks a value, e.g. 65 for the `70barracuda`).
2. The item of the part, through its `itemType`, using the item's
   `MaxCapacity`. Vanilla names the item with the vehicle's `mechanicType`
   appended (`Base.SmallTrunk` + 3 -> `Base.SmallTrunk3`); the digit is the
   vehicle type, not a quality level, and the items carry a `VehicleType`
   field with the same number. Some mods name the item in full instead
   (`Base.92amgeneralM998Roofrack`, `USMIL.Seat0`), and `itemType` can be a
   list separated by `;`, so every candidate is tried: the vanilla naming
   first, then the name as written.

**What does not count as storage:**
- Containers with a `contentType` (fuel and air), the fuel tank, the tires and
  the battery.
- Fake parts: no capacity and `itemType = nil`. Mods switch the generic
  `TruckBed` off this way (`category = nodisplay`) and add their own trunk
  with another name. Before this was understood, 440 vehicles looked like
  they had an unresolved trunk.

**How the pieces are grouped**, by the name of the part:
- Trunk: the name contains "trunk", or it is `TruckBed` / `TruckBedOpen`.
- Seats: names starting with `Seat`, except the driver's seat
  (`SeatFrontLeft`), which is left out on purpose: if it is filled with items,
  the player cannot get into the vehicle.
- Others: anything else that holds items (glove box, roof rack, gun rack,
  toolboxes, console, `...TruckBedExtras`).

**The formula:** storage = trunk + (seats - 1) x seat capacity + other
containers. It is calculated as the sum of the real seat parts without the
driver's, which gives the same number when all seats are equal and is more
accurate when they are not (for example, vehicles where the `seats` value
does not match the seat parts).

**What the card shows:** the total with the breakdown, e.g.
`55 (trunk 30 + seats 20 + others 5)`. When some container has no capacity
that can be resolved, the total is only a minimum and is shown as
`≥ 122 (...)` with a note in the footer.

**Known limits:** the trunk capacity is the maximum, with the part in perfect
condition (it drops as the part is damaged). A roof rack always counts, even
though a vehicle may not carry one by default. The grouping is by name, so a
trunk with an unusual name would be counted under "others"; the total is not
affected, only the breakdown.

---

## Vehicles left out of the list

**Non-functional wrecks.** Burnt and smashed vehicles are excluded: any
script name containing `burnt` or `smashed`, ignoring case. The first
version only checked the end of the name and missed `NormalCarBurntPolice`.
89 vehicles are excluded.

**Trailers (for now).** Excluded on purpose, with a switch at the top of
`parse_vehicles.py` (`REMOLQUES = False`; set it to `True` to include them in
a later update). A vehicle is treated as a trailer when:
1. it has no engine force or no seats, or
2. its script name starts with `Trailer`, or
3. its English name contains "trailer".

**Why a name rule is needed:** the first rule alone only caught the 9
vehicles of the `isoContainers` mod. All other trailers, vanilla and mods,
inherit an engine value and seats from their template (for example 3,600 and
2 seats; the `KI5campers` caravans have 10 and 4 to 7 seats), so they look
like ordinary vehicles in the stats. 37 vehicles are excluded in total. The Dodge Caravan minivans are cars and stay.

**Safety net:** the script prints every excluded trailer with the reason, so
the list can be checked by eye after each run.

**Result:** 595 vehicles (152 vanilla, 443 from mods), all with complete
stats.

**Optional file:** the bot starts without `data/vehicles.json` (it prints a
warning), so a missing or older deployment does not stop the item commands.

---

## Out of scope (for now)

- **Crafting recipes:** the `pz-item-browser` repository also includes
  `parse_recipes.py`, which would allow showing how an item is crafted. It
  was decided not to include this in the first version — the bot only
  reports on the item itself. Noted as a possible future feature.
- **Trailers as vehicles:** left out on purpose and controlled by the
  `REMOLQUES` switch; they may come back in a later update.
- **Exact storage for every vehicle:** a few vehicles have a container
  whose capacity cannot be worked out from the files (for example,
  because it points to an item that is not in the data). They show a
  lower bound (`≥`) instead of an exact number.
- **A picture of each individual vehicle:** not available in the game files,
  so only the mod cover is used (see above).
- **Remaining mod icons (355 items):** see "Mod icons" above.
- **Mod translations in older `.txt` formats for items:** see "Mod
  translations" above (vehicles do read both formats).
- **Keeping the bot running 24/7** (systemd service vs screen/tmux): not
  decided or set up yet. Currently the bot is started by hand from an SSH
  session.
- **Automatic regeneration of `data/`** when the game or the mod list
  changes: still a manual process.

---

## What is (and is not) in the repository

**Not versioned:** `venv/`, `.env`, everything generated in `data/`
(vanilla and mod JSON files, icon folders, `vehicles.json` and
`vehicle_previews/`), local copies of game assets
(`.pack` files, copyrighted), and editor files (`.vscode/`,
`*.code-workspace`).

**Why the generated data is excluded:** it is derived and can be recreated by
running the scripts in `tools/` (see the README). The repository holds the
recipe, not the output. The icons also come from copyrighted game files.

**Consequence:** a fresh clone has no `data/` and no `.env`; the bot will
not start until both are created (a missing `.env` shows up as
`expected token to be a str, received NoneType`).