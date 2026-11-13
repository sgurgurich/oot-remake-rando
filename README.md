# OoT Remake Randomizer

Research and tooling for an item randomizer for *The Legend of Zelda: Ocarina of Time* (Switch 2 remake,
title `0400486024DEC000`, update v131072 / 2.0). Built from the owner's own cartridge dump.
**No game data is committed here**: `work/` and `filelist.txt` are generated locally and git-ignored.

## Download

**[sgurgurich.github.io/oot-remake-rando](https://sgurgurich.github.io/oot-remake-rando/)**: or the
`OoTRando.exe` on the [latest release](https://github.com/sgurgurich/oot-remake-rando/releases/latest).
You need your own dump of the game (a `.nup` with the 2.0 update); nothing from the game is included.

The app checks for a newer release each time it opens. If there is one, it downloads it in the
background, checks it against the SHA-256 published with the release, and switches to it when you
restart (or the next time you open it). Running from source only tells you a new version exists.
See [randomizer/updater.py](randomizer/updater.py).

## Releases and contributing

- **CI** ([.github/workflows/ci.yml](.github/workflows/ci.yml)) runs on every pull request and push to
  `main`: the game-file check, a compile check, and 60 seeds per preset in `tests/test_seeds.py`.
- **Release** ([.github/workflows/release.yml](.github/workflows/release.yml)) runs on pushes to `main`. When
  `VERSION` in `randomize.py` has no release yet, it builds `OoTRando.exe`, writes its SHA-256 and
  publishes release `v<VERSION>`. To ship: bump `VERSION` in a PR and merge it.
- **Download page** ([docs/index.html](docs/index.html)) deploys to GitHub Pages when `docs/` changes.
- `main` is protected: changes go through pull requests that pass CI, force pushes and deletion are
  blocked, and only the owner can merge. Workflows from forks wait for approval.

**No game files, ever.** `.nup` dumps and the game's own file formats are in `.gitignore`, and
[tools/check_no_game_files.py](tools/check_no_game_files.py) fails on any of them (and on anything in
`work/`, `out/`, `build/`, `dist/` or over 2 MB). It runs in CI and as a pre-commit hook; enable the hook
in a clone with `git config core.hooksPath .githooks`.

## Download stats

The app collects nothing. Download numbers come from the counters GitHub keeps for every release
file:

```
py tools/download_stats.py          # counts per release, right now
```

From v0.8.2 each release has the app twice: `OoTRando.exe` (the download page and direct links: new
installs) and `OoTRando-update.exe` (fetched only by the app's updater: updates). Earlier releases
only had `OoTRando.exe`, so their counts include updates.

The **Download stats** workflow ([.github/workflows/stats.yml](.github/workflows/stats.yml)) runs daily
and keeps the history on the `stats` branch: `downloads.csv` (one row per release per day) and a
`README.md` with totals, the last 30 days and a per-release table, which GitHub shows at
[github.com/sgurgurich/oot-remake-rando/tree/stats](https://github.com/sgurgurich/oot-remake-rando/tree/stats).
Views of the repository and its referrers are under the repo's **Insights > Traffic** (GitHub keeps 14
days). GitHub Pages has no built-in visitor counts.

## License

The code is under the [MIT License](LICENSE). Game names, text and data the tools read belong to
their owners; no game files are included, and the app only reads your own dump.

## What the dump is

`*.nup` is an unencrypted container that holds both the base game (`base/`) and the 2.0 update
(`131072/`) as complete file trees (`exefs/` + `romfs/`), with identical files deduplicated by offset.
Format notes are at the top of [tools/nup.py](tools/nup.py). Each file entry carries a SHA-256 hash,
and extracted files verify against it.

The game runs on the same Nintendo EPD engine family as *Tears of the Kingdom*:

| Data | Where | Format |
| --- | --- | --- |
| Actor placement per area (`*_Child_*`, `*_Adult_*`, `*_Static`, `*_Dynamic`) | `romfs/Banc/<Area>/*.bcett.byml.zs` | BYML v7, zstd with `bcett.byml.zsdic` |
| zstd dictionaries | `romfs/Pack/ZsDic.pack.zs` | SARC of 4 dictionaries |
| Flags / save data list | `romfs/GameData/GameDataList.Product.110.byml.zs` | BYML |
| Actor/resource databases | `romfs/RSDB/*.rstbl.byml.zs` | BYML |
| Actor packs | `romfs/Pack/Actor/*.pack.zs` | SARC, zstd with `pack.zsdic` |
| Cutscenes / NPC dialogue logic | `romfs/Event/` | (not yet examined, likely BFEVFL) |
| Resource size table (updated by the patcher when a file grows) | `romfs/System/Resource/ResourceSizeTable...rsizetable.zs` | RSTB |

## Desktop app

`dist/OoTRando.exe` (or `py gui.py`, or double-click `OoTRando.pyw`) does the whole job in one window:

1. **Game dump**: browse to your `.nup`. The app checks it is Ocarina of Time with the 2.0 update by
   comparing the SHA-256 of every file it needs (listed in `data/romfs_manifest.json`) with the dump's own
   hashes. It never writes to the dump.
2. **Where items can hide**: switch location categories on and off (table below).
3. **Keys & dungeon items**: Boss Keys and Maps & Compasses can move within their own dungeon.
4. **Safety**: keep chests that play an item scene vanilla.
5. **Cutscenes**: skip the intro, make every cutscene skippable (see [Cutscenes](#cutscenes)).
   **Shops**: shuffle shop stock and prices (see [Shops](#shops)).
   **Logic & world**: Logic or No logic, and Open Kokiri Forest / Deku Tree / Door of Time / Zora's
   Fountain (see [Logic and world options](#logic-and-world-options)).
6. **Forge seed**: seed (empty = random), output folder, and what to make:
   - **.nup** (default): `OoTRando-<seed>.nup`, a complete copy of your dump with the changes applied.
     Load it in the emulator instead of the original. Needs about 26 GB free in the output folder.
   - **Mod folder** / **.zip**: `OoTRando-<seed>/romfs/...`, for emulators that load romfs mods.
   - **Spoiler log**.
7. **Name in your emulator**: the game name the patched `.nup` shows in your game list. Default
   `OoT Remake Rando - {date}`; `{date}` (YYYY-MM-DD) and `{seed}` are filled in, empty keeps the original.

### The patched .nup

[tools/nup_patch.py](tools/nup_patch.py) follows the [NUP v1 spec](https://github.com/a55uka/nup/blob/meow/SPEC.md).
It copies the original (which is only ever opened for reading), appends each patched file at the end of
the copy (16-byte aligned, stored raw), points that file's entry in the 2.0 update package at the new data
(size, offset, SHA-256), and rewrites the superblock's file size and TOC SHA-256. Package records, the
UUID, the TOC size and every other entry stay byte-identical; the old data stays in place unreferenced,
since base-game files can share it. Before the copy is renamed to `.nup`, it is re-read like a strict
reader would: TOC hash, file size, every replaced file's bytes and hash, no overlapping extents, and no
entry changed other than the replaced ones. The game name comes from the title TLV (type 0x0005) in the base package's
meta block; there is no NACP in this dump. A renamed copy gets a new meta block appended at the end and
the base package record points at it (meta blocks are outside the TOC hash, the record is inside it). A full check of a 466-location seed (all 372,587 files hashed
against their entries) passed.

The window is [ui/index.html](ui/index.html) shown through pywebview and the Edge WebView2 runtime that
ships with Windows 11; [gui.py](gui.py) is its Python side. Opened in a plain browser, the page runs on a
stand-in API with sample data, which is handy for working on the design.

The first run copies the 94 needed files (about 7 MB) out of the dump into
`%LOCALAPPDATA%\OoTRando\romfs-<hash>`, verified. Later runs use that cache, even without the dump.
Settings are remembered in `%APPDATA%\OoTRando\settings.json`.

**Open tracker** (top right) opens the in-game item tracker overlay; see [Item tracker](#item-tracker).

Rebuild the exe with `py -m pip install pyinstaller pywebview` and then `py build_exe.py`. The exe carries
only the randomizer code, `ui/` and `data/`, no game files.

## Randomizing

The same thing from the command line:

```
py randomize.py --nup "path/to/dump.nup" --seed 1234   # first run: reads the dump, then it is cached
py randomize.py --seed 1234                             # writes out/OoTRando-1234/ and its spoiler log
py randomize.py --seed 1234 --shuffle chest,scrub,skulltula,pot,freestanding --boss-keys own_dungeon
py randomize.py --seed 1234 --maps-compasses anywhere --keep-event-chests --zip
py randomize.py --seed 1234 --spoiler-only
py randomize.py --nup "path/to/dump.nup" --seed 1234 --make-nup --no-folder   # out/OoTRando-1234.nup only
py randomize.py --nup "path/to/dump.nup" --make-nup --nup-title "OoT Rando {seed}"  # name shown in the emulator
py tools/nup_patch.py original.nup new.nup out/OoTRando-1234                  # .nup from an existing mod folder
py tests/test_seeds.py 200                              # 200 seeds x 5 setting presets, checked independently
```

Load `OoTRando-<seed>.nup` in the emulator like the original dump. Or, for a romfs mod: copy `out/OoTRando-<seed>` into the emulator's mod folder for title
`0400486024DEC000`, so the path ends in `.../0400486024DEC000/OoTRando-<seed>/romfs/...`. Keep the
spoiler log outside the mod folder.

**What can be shuffled (v0.8).** Every category switched on joins one shared pool:

| Category | Locations | How it is patched | Status |
| --- | --- | --- | --- |
| Treasure chests | 181 | `Drop__DropActor` | default |
| Business Scrubs | 18 | `ScrubBusiness_ShopItemActorName0` | experimental |
| Gold Skulltulas | 100 | `Drop__DropActor` added (overrides the token drop table) | experimental |
| Pots, crates, grass, rocks, beehives with a fixed drop | 146 | `Drop__DropActor` | experimental |
| Heart Pieces and boss Heart Containers | 21 | the placed object itself (`Gyaml`) is swapped | experimental |

Each item has two forms in the game: a "get" object (`Item_*`, `TBox_*`) that plays the hold-it-up
scene, and a pick-up (`Obj_*`) that lies in the world. Equipment only exists as a get object, so it can
only land in chests and scrubs; pots, Gold Skulltulas and freestanding spots get pick-ups (rupees,
hearts, Heart Pieces, tokens, magic, ammo). `data/item_forms.json` lists each item's forms; the patcher
writes whichever form the location needs.

Dungeon items: Small Keys, Boss Keys, Maps and Compasses are generic (they work for whichever dungeon
they are picked up in), so they can only move within their own dungeon. Boss Keys and Maps & Compasses
can be set to *own dungeon* (chests only; maps can also go *anywhere*, where they do nothing). Small
Keys stay vanilla until there is per-room key logic.

**Not possible yet:** songs, NPC gifts and boss rewards are handed out by cutscene scripts
(`Event/EventFlow/*.bfevfl.zs`, e.g. `Dm_MelodyGet_Forest` names `Item_Melody_ForestMinuet`), which the
tools cannot rewrite yet. Excluded: the Treasure Chest Shop minigame, the Hall of Fallen Foes (boss rush),
and pots that release a fairy or bugs.

**Logic** ([randomizer/logic.py](randomizer/logic.py)) is deliberately conservative and has **not been
checked in the remake**. Each check requires everything the original game needs to fully clear that
dungeon or area, minus the item that check originally gives. Unidentified overworld checks need the whole
child and/or adult item kit. Locations in categories that are switched off keep their items but still
count for logic. That is safe (seeds are always beatable if the remake follows the original's progression)
but makes early placements predictable. Rules can be loosened per location once confirmed in game.

## Logic and world options

```
py randomize.py --seed 1234 --open-forest --open-deku --open-door --open-fountain
py randomize.py --seed 1234 --no-logic            # items anywhere; the seed may be unbeatable
```

**Logic / No logic.** With logic (default) every item is placed where it can be reached with the items
found before it, and every seed is checked to be beatable. With no logic every location's rule is
"always", so items land anywhere (still in a form the location can hold, and dungeon items still follow
their setting); the spoiler log says the seed may be impossible.

**Open options** start a new save with a story lockout already over. Each one is a flag the game flips
itself when that lockout ends, written as the flag's starting value in `GameData/GameDataList` (the
4-byte `DefaultValue` slot is changed in place, [tools/gamedata.py](tools/gamedata.py); nothing else in
the file moves). They only apply to a new save. Each also changes the logic
([randomizer/logic.py](randomizer/logic.py) `milestones()`):

| Option | Flag at the start | Logic change |
| --- | --- | --- |
| Open Kokiri Forest | `KokiriForest_Npc_Kokiri_007_Child_Blocker_00` = false (the exit guard) | leaving the forest no longer needs the Deku Tree |
| Open Deku Tree | `KokiriForest_Npc_Kokiri_Mido_Child_Blocker` = false (Mido) | the Deku Tree needs only the Slingshot (Gohma falls to Deku Sticks) |
| Open Door of Time | `Market_Child_TimeTempleDoor_Opened` = true | becoming adult only needs reaching the Temple of Time |
| Open Zora's Fountain | `HavePlayedEvent.Dm_Zora_0010` = true (King Zora's scene, which the Zora's Domain map checks) | adult Zora's Fountain / Ice Cavern no longer waits for Jabu-Jabu |

None of these has been tried in game yet. Without Open Zora's Fountain, the Ice Cavern now explicitly
requires Jabu-Jabu, which the Door of Time used to imply.

## Shops

```
py randomize.py --seed 1234 --shop-items --shop-prices random      # or cheap
py tools/shops.py              # rebuild data/shops.json (needs Banc/ and Pack/Actor/Shop_*.pack.zs in work/raw)
```

Shop stock is placed `Shop_<item>` objects with a `ShopItemIndex` (the shelf slot): 112 slots in the Kokiri
Shop, Market, Kakariko, Goron and Zora shops. **Shuffle shop stock** swaps which `Shop_` object sits in
each slot. Only items that already have a `Shop_` version can be sold (consumables, potions, bottled
items, shields, tunics, masks), so shops shuffle among themselves; tunics, shields and masks stay where
the original game sells them, because the logic assumes they can be bought there.

Prices are per item, not per slot: each `Shop_` actor pack has a `PriceParam` (`BuyingPrice`) reached
through its ActorParam and GameParameterTable. **Random** prices are a quarter to twice the original
(rounded to 5, at most 300); **Cheap** is 10 to 60 percent. Equipment never costs more than usual. The
edit only changes an integer, so the BYML, the SARC and the decompressed pack keep their size and the
resource size table is unchanged. The spoiler log lists every slot with its item and price. Price signs
beside the shelves (`Shop_Board_*`) are not moved, so a sign can describe the item that used to be there.

## Item tracker

**Open tracker** in the app (or `OoTRando.exe --tracker` on its own) opens a small overlay that stays on
top of Lichii and shows what you've found as icons (names on hover): items, equipment, upgrades, both
trading sequences and the masks, songs, Spiritual Stones and Medallions, with Gold Skulltula tokens,
Pieces of Heart and hearts. Progressive items show dots or a stage count (the adult trade sequence is
`k/11`); bottles show `n/6`.

The icons are the game's own, decoded from your dump the first time the tracker opens
(`UI/Tex/Icon/<item>.bntx.zs`, ASTC 4x4 in Switch 2 block-linear tiling: inside a 512-byte GOB the
16-byte blocks follow address bits y0, y1, x4, y2, x5; see [tools/bntx.py](tools/bntx.py)) and cached as
96 px PNGs in `%LOCALAPPDATA%\OoTRando\icons-<hash>`. Nothing from the game ships in the app. Songs,
Stones and Medallions have no icon file, so they are drawn (notes and gems in their colours). Decoding
uses the `texture2ddecoder` package. Show or hide it with a controller
combo (default: click both sticks, L3 + R3) or a key (default F10); both are set in its gear menu, with
the background opacity. Showing it never takes focus from the game. The combo is read with XInput, so
it works with Xbox-style controllers.

It reads the newest `progress.sav` in Lichii's save folder
(`%APPDATA%\lichii\nand\user\save\...\0400486024DEC000\slot_NN\`) every 1.5 s, so it updates each time
the game saves, autosaves included, and flashes what was found since. The save is TotK-style: `04 03 02
01`, a data offset at 0x08, then (murmur3 hash, value) pairs from 0x28, grouped by type. An item is found
when its `IsGet.<actor>` flag is 1 (`data/tracker.json`, built by `tools/tracker_data.py`, which checks
every flag exists in `GameData/GameDataList`). Counters: `PouchData.Item_Token_Gold.StockNum`,
`PouchData.Obj_Heart_Piece.StockNum`, `PlayerStatus.MaxLife` (quarter hearts).

Bottles are counted from the inventory slots, which the save keeps as String64 flags holding an
actor name (the wallet slot holds `Item_Wallet_Small`): every slot holding an `Item_Bottle*` name is a
bottle, Ruto's Letter included. Two String64 flags that only echo something recent (last item obtained,
last equipment) are skipped. This is inferred from saves without bottles yet, so the count is
unconfirmed until a save with bottles has been checked.

Not done yet: updates the moment an item is found (between saves), which needs the game's live flag
table in Lichii's memory. A read-only scan found its sorted hash index while the game was running; the
values that go with it still have to be located. Per-chest "checked" marks: chests don't store their
opened state under their placement hash, unlike picked-up rupees.

## Cutscenes

```
py randomize.py --seed 1234 --skip-intro --skippable-cutscenes
py tools/cutscene_skips.py     # rebuild data/cutscene_skips.json (needs Event/ and Banc/ in work/raw)
```

Cutscenes (`Dm_*`) are timelines that event flows start with an `EventSystemActor` / `EventTransition`
action. [tools/evfl.py](tools/evfl.py) reads this game's BFEVFL flows (the Breath of the Wild layout with
0x30-byte events) and can rewrite event links in place, which never moves data.

- **Skip the intro** (`skip_intro`): `OpeningEvent` plays Navi's wake-up scene (`Dm_Kokiri_0030`) and then
  checks whether the player skipped it; the "skipped" branch warps Navi into place and carries on. The
  option sends the flow straight into that branch, then through the flow's existing fade-in (the screen
  was faded out before the scene). Two bytes change. The narrated opening (`Dm_Kokiri_0000`) is kept: it
  plays while Kokiri Forest loads, and the flow checks just once, right after it, that loading finished, so
  cutting it could leave the start screen stuck. It is made skippable instead.
- **Every cutscene skippable** (`skippable_cutscenes`): only three cutscenes disable the Skip button, via a
  `SkipSetting/DisableSkip` component: the opening, the title (`Dm_Title_0005`) and the credits
  (`Dm_StaffCredit_0005`). The option removes that component from all three.
- **Skipping every cutscene automatically is not done.** The survey in `tools/cutscene_skips.py` found 331
  cutscene calls in flows: 154 go to scripted scenes (flowcharts, not plain timelines), 75 are system
  scenes (item gets, ocarina, chests, songs, title, credits), 55 would leave the screen faded out, 13 set
  a "has played" flag other scripts check, and most of the rest warp Link, change the time or start boss
  fights. Only one passed every rule. Map-triggered first-visit scenes would need their `HavePlayedEvent`
  flags preset in `GameData/GameDataList` (big-endian BYML, flags stored as murmur3 hashes), with the same
  risks.

## Item locations

`py tools/inventory.py` writes `data/locations.json` (531 locations, one per placement `Hash`, shared by
the child and adult copies of a map), `data/item_names.json` (English names from the game's text) and
`data/item_forms.json` (which actor to use for each item in each kind of location). It needs
`filelist.txt` for the list of actor packs.
Dungeon checks carry their room index and the developer room label from `RSDB/DungeonParam`.

A chest's contents are a plain string in its placement params, which is what the patcher rewrites:

```json
{ "Gyaml": "Obj_TBox_A_01", "Dynamic": { "Drop__DropActor": "Item_Hookshot" }, ... }
```

Scrubs use `ScrubBusiness_ShopItemActorName0..2`. Items given by NPCs, songs and boss rewards come
from event flows (`Event/EventFlow/*.bfevfl.zs`) and still need a writer.

## Tools

```
py tools/nup.py info    <dump.nup>
py tools/nup.py list    <dump.nup> > filelist.txt
py tools/nup.py extract <dump.nup> work/raw <path substring>   # e.g. 131072/romfs/Banc/
py tools/dump.py Banc/KokiriForest/KokiriForest_Child_Dynamic.bcett.byml.zs > out.json
py tools/inventory.py
py tools/make_manifest.py      # after inventory.py or cutscene_skips.py: refresh data/romfs_manifest.json
```

Requires Python 3.12 and `py -m pip install -r requirements.txt`.

## Building a mod

```
py tools/patcher.py plans/poc_kokiri.json out/OoTRando-POC
py tools/verify_mod.py out/OoTRando-POC      # prints every value that differs from the original
```

A plan maps a location's `Hash` to the actor it should give. The patcher edits every map containing
that location (child and adult copies), re-encodes it, and compresses it with the game's
`bcett.byml.zsdic` dictionary. If a map grew past its entry in the resource size table
(`align32(size) + 264` for maps), it also writes an updated table.

Install by copying `out/OoTRando-POC` into the emulator's mod folder for title `0400486024DEC000`, so the path
ends in `.../0400486024DEC000/OoTRando-POC/romfs/Banc/...`.

### Proof of concept test (plans/poc_kokiri.json)

| Location | Original | Patched |
| --- | --- | --- |
| Kokiri Sword chest (keeps its `Get_StoneOfForest_GetSword` event) | Kokiri Sword | Hookshot |
| Mido's House chests (4, next to Link's house) | Green / Blue rupees | Boomerang, Slingshot, Bomb Bag, Heart Piece |

What to check in game: whether each chest gives the new item with the right model and text, whether
the sword chest's event still forces a sword, and whether Mido still blocks the Deku Tree (no sword).
The sword is now unobtainable in this test build, so use a throwaway save.

`tools/test_roundtrip.py <romfs>` re-encodes all 160 maps and checks that values, types and byte
sizes match the originals (they all do).

## Roadmap

1. **In-game test**: run the proof-of-concept mod and one full seed. Open questions: do chests show the
   new item's model and text, do scripted chest events (Bow, Hammer, Slingshot, Kokiri Sword, Boss Keys
   ...) still force their original item, does the game load every map the mod replaces, and for each
   experimental category: do skulltulas honour the added drop, do swapped Heart Pieces spawn and stay
   collected, and do scrubs sell major items.
2. Confirm or loosen logic rules area by area (biggest win: the overworld chests).
3. A BFEVFL writer, to shuffle songs, NPC gifts and boss rewards.
4. Small Keys in their own dungeon (needs per-room key logic).
