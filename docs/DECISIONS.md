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

## Bot scope: two separate commands

**Decision:** `/getid` returns only the ID; `/getinfo` returns the full card
(name, image, type, category, source).

**Why:** different use cases — quickly copying an ID for an admin command,
versus looking up an item's full details. A single command that always
showed everything would be slower to use for the most common case (just the
ID).

---

## Multiple matches in a search

**Decision:** when a search matches several items (e.g. "Trousers"), the
bot shows a dropdown menu (`discord.ui.Select`) for the user to choose from,
instead of automatically picking one or asking the user to be more
specific.

---

## Out of scope (for now)

- **Crafting recipes:** the `pz-item-browser` repository also includes
  `parse_recipes.py`, which would allow showing how an item is crafted. It
  was decided not to include this in the first version — the bot only
  reports on the item itself. Noted as a possible future feature.
- **Steam Workshop mod items:** the design already accounts for a `_source`
  field per item (currently always `"vanilla"`) so the parser could later be
  extended to also read mod folders installed on IBEROZOID_Server, but that
  extension hasn't been implemented yet — it requires looking at the real
  folder structure of an actual mod to design it properly, rather than
  guessing.
