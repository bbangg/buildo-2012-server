# What actually exists in this build

There are no dev notes, no readme and no `.pdb` in the release (the exe names
`d:\projects\proton\Buildo\bin\Buildo.pdb`, but the symbols were never
shipped). Only two source paths survive, from a logging macro:
`..\source\Component\GameLogicComponent.cpp` and `..\source\Server\World.cpp`.

So there is nothing to *read*. But there is plenty to *enumerate*, and that is
the difference between knowing and guessing. Four things in this binary are
**closed lists** — if a feature is not in them, the client cannot do it, full
stop, and implementing it server-side is invention rather than restoration.

Regenerate any of this with `ra.py` (needs `source .venv/bin/activate`).

---

## 1. Everything the server can tell the client to do

Handlers are registered by name in two blocks. This is the entire
server→client surface; a name that is not here does not exist.

**GameLogicComponent** (registration block 0x4349d1..0x4351a5)

| call | status |
|---|---|
| `OnSpawn` | used |
| `OnRemove` | used |
| `OnConsoleMessage` | used |
| `OnTalkBubble` | used |
| `OnDialogRequest` | used |
| `OnRequestWorldSelectMenu` | used |
| `OnInitialLogonAccepted` | used |
| `OnFailedToEnterWorld` | not used |
| `OnSetBux` | used |
| `OnReconnect` | not used |
| `OnZoomCamera` | not used |
| `OnPinchMod` | not used |

**NetAvatar** (string cluster 0x4cc454..0x4cc4c4; `OnAction`→0x4471f0 and
`OnChangeSkin`→0x448a20 confirmed by their registration sites)

| call | status |
|---|---|
| `OnSetClothing` | used |
| `OnSetPos` | used |
| `OnAction` | used (`/dance`, `/wave`) |
| `OnNameChanged` | not used |
| `OnChangeSkin` | not used (we set skin through `OnSetClothing`'s 3rd arg) |
| `OnKilled` | used (lava kills you) |
| `OnSetFreezeState` | not used |
| `OnPlayPositioned` | used (the sounds the exe never names) |

Plus `OnAddLog` (0x4329b9) and `OnAddNotification` (0x432919) on the console
component — neither used. Their argument keys are in the vocabulary below
(`msg|`, `imageFile|`, `audioFile|`, `delayMS|`), so a notification could carry
an image and a sound.

## 2. Everything the client can send

Packet types, from the jump table at 0x434418 (index = packetType):

| # | target | what it is | status |
|---|---|---|---|
| 0 | 0x433936 | avatar state | handled |
| 1 | 0x433961 | call function (VariantList) | handled |
| 2 | default | — | not in this build |
| 3 | 0x433c03 | set tile / the one action packet | handled |
| 4 | 0x433ff4 | map data | handled |
| 5 | 0x433f28 | **one whole tile**: Tile::Serialize (0x43e850) over the extended data, then re-render (0x441050) | handled |
| 6 | 0x433f86 | **many tiles**: pairs of dwords in the extended data until -1 | not handled |
| 7 | default | **tile activate — client SENDS this** | handled (doors) |
| 8 | 0x433b26 | tile damage | handled |
| 9 | 0x434130 | inventory | handled |
| 10 | default | **item activate — client SENDS this** | handled (wear) |
| 11 | default | **pickup request — client SENDS this** | handled |
| 12 | 0x433e72 | tree state (stage, or clear) | handled |
| 13 | 0x433e26 | **take items from the inventory**: count1 of intData via PlayerItems::Remove (0x43d800) | handled |
| 14 | 0x434173 | dropped objects | handled |
| 15 | 0x433e59 | **the lock**: ApplyPacket -> 0x441070 | handled |
| 16 | 0x434304 | items.dat | handled |

**A correction, and the limit of this method.** I first read the default-case
entries as "not in this build". That is wrong, and it is the one trap worth
naming: **this table is what the client can RECEIVE.** What it SENDS is a
separate question the table says nothing about. Measured on the wire:

* standing in a door and clicking it sends **packetType 7** with the tile in
  intX/intY — `[gs] gup type=7 netID=0 tile=50,29`. That is the door, and the
  client never accepts a 7, only sends one.
* clicking an inventory cell that is ALREADY the selected one, when that item's
  material is 14, sends **packetType 10** with the item id — 0x43615a, reached
  only past `cmp eax,[ebp+0xac]` (same item as last time) and
  `cmp [esi+4],0xe` (clothing). Clicking a garment twice is this build's own
  wear gesture.

* touching a dropped object sends **packetType 11** with the object id. The
  client owns that decision: 0x431bb0 plays audio/object_collect.wav at the
  object, raises avatar state flag 0x4000, stamps obj+0x18 so it only ever asks
  once, and sends the id (builder 0x431c35). Nothing moves until the server
  answers with a packetType 14.

So the receive table bounds what we can tell the client; only the wire bounds
what the client tells us. **All four outgoing builders are now identified** —
find them with `push 0x38` + `call 0x4a1b30`: 0x430c90 type 7, 0x430cf0 type 10,
0x430f00 type 3, 0x431c35 type 11. That is the complete list of things the
client can say. When in doubt, run it and watch `gs.log` — the server
already logs every packet type it does not handle.

Beyond those two, every action — punch, place, wrench, wear, harvest — leaves
the client as the same packetType 3 built by 0x430f00, with `intData` = the held
item, and the server decides which it was.

Text verbs: `action|` + `enter_game`, `join_request`, `refresh_item_data`,
`input`, `dialog_return`, `drop`, `info`, `respawn`, `setSkin`, `quit`,
`quit_to_exit`. The inventory panel has exactly three buttons — DROP, STORE and
INFO — and STORE sends nothing.

## 3. The protocol key vocabulary

Every `something|` string in the data section:

```
action|        reconnect|      country|       deviceVersion|  platformID|
hash|          hash2|          game_version|  protocol|       requestedName|
tankIDName|    tankIDPass|     text|          itemID|         button|
input_string|  input_checkbox| dialog_name|   buttonClicked|  name|
netID|         userID|         colrect|       posXY|          type|
spawn|         color|          msg|           file|           imageFile|
audioFile|     delayMS|
```

**`invis|` and `mstate|` are not in this binary.** Our `spawn_text()` was
sending both; they come from later Growtopia versions and this client silently
ignores them. That is exactly the failure mode to watch for — a field that
looks right, changes nothing, and reads as "implemented".

`tankIDName|`/`tankIDPass|` mean the GrowID login flow exists client-side.

## 4. Enums are closed too

Every constant the client compares a material against: 0, 1, 2, 3, 4, 5, 6, 7,
10, 12, 13, 14, 15, plus the 2..13 jump table at 0x43e83c. **8, 9 and 11 are
compared against nowhere** — they are the only genuinely inert values.
Collision is 0 (none), 1 (solid), 2 (one-way platform). Storage is 0/1 (flat),
2 (four-neighbour smart edge) and 3 (left/right smart edge, 0x440390). Body
part is the sprite slot, 0..5. See the README for where each was pinned.

Collision 2 and storage 3 were the last two values nothing shipped could
account for, and **one item explains both**: see the wood platform below.

## 5. What the assets prove, and where the data is short

`item_definitions.txt` is **not** the full item list — it is a subset of what
the shipped art and audio were built for. Textures no item claims:

| texture | what it implies |
|---|---|
| `tiles_bux.rttex` | the gem item (id 112, hard-coded at 0x434206) |
| `tiles_woodplatform.rttex` | the item that used collision 2, the one-way platform |
| `tiles_flowers.rttex` | flower tiles |
| `tiles_grass.rttex` | grass tiles |
| `tiles_paintings.rttex` | painting tiles |
| `tiles_toilet.rttex` | a toilet — and `audio/toilet_flush.wav` exists |
| `tiles_rockbackgd.rttex` | a rock background |

Sounds the exe never names can only be triggered by the server, through an
item's sound string (material 5/6) or `OnPlayPositioned`. That list is a
inventory of original-server behaviour:

`door_open.wav`, `door_shut.wav` (doors did something), `use_lock.wav`,
`blip_lock.wav`, `punch_locked.wav` (locks refused punches), `punch_organic.wav`
(trees had their own punch sound), `tile_removed.wav`, `pain.wav`,
`male_scream.wav`, `wscream.wav` (damage and death — see `OnKilled`),
`toilet_flush.wav`, `piano_nice.wav`, `choir.wav`, `secret.wav`,
`object_spawn.wav`, `beep.wav`, `bleep_fail.wav`, `dialog_confirm.wav`,
`click_8bit.wav`, `boombox/get_ready/old_timey` mp3 and ogg.

Every `setup_seed` line ships `seconds_to_bloom|0` and `max_fruit|0`, and every
`add_tile` ships no rarity. The prototype's data is placeholder.

## 6. Things we implemented that the binary does NOT pin

Kept honest on purpose. These are ours, not restored:

| ours | why |
|---|---|
| ~~refusing to place a solid tile on a player~~ | **removed** — it was invented |
| ~~a tree handing back a spare seed~~ | **removed** — invented |
| gem drop rate on breaking a block | only item 112 is pinned, never a rate or a source. `BUILDO_GEM_CHANCE=0` turns it off |
| a growing time for seeds | the data says 0, so 0 is now the default; `BUILDO_BLOOM` is ours |
| a tree yielding 1 fruit | the fruit itself is pinned (the client hangs that very block on the tree); `max_fruit` is 0, so the count is ours. `BUILDO_FRUIT` |
| pairing each server-played sound with its moment | the sound files and `OnPlayPositioned` are pinned; that `tile_removed.wav` goes with removing a tile is inference from the filename |
| the item ids, names and HP of the art-proven tiles | the textures prove the tiles existed; nothing pins their numbers. `BUILDO_NO_EXTRA_ITEMS` |
| the boombox animation period (250 ms) | mandatory non-zero or the client divides by zero; the value is a choice |
| which inert material each plain block gets (8) | 8/9/11 are indistinguishable |
| the starter kit contents | the published build had no server |
| the INFO and wrench dialog wording | the dialog protocol is pinned, the text is ours |

## 7. How to check a claim before building on it

```bash
source .venv/bin/activate
python3 ra.py strings SomeName        # does the name exist at all?
python3 ra.py xref 0xADDR             # who references it?
python3 ra.py dis 0xADDR 40           # what does it do?
python3 ra.py find 'REGEX'            # every instruction matching a pattern
python3 ra.py classes                 # every class with a vtable
```

Two rules that keep paying off: **if a feature exists, it left a string** — a
name, a sound, a texture or a format string. And **if the client has to be told
something, the name is in one of the two registration blocks.** Check there
first; it is a one-line answer instead of an afternoon.

---

## 8. Restored since this file was written

* **Doors** — packetType 7 is the door click. A door's one TileExtra string is
  where it goes: `EXIT` or empty means out to the world list (with
  `door_shut.wav`), any other value is a world name and you land there. Verified
  end to end: clicking a door labelled SECOND printed "World SECOND entered."
  `BUILDO_DOOR_DEST` labels the generated main door.
* **Wrenching a door or sign now edits its label**, using `add_text_input` and
  the reply that comes back as `action|dialog_return` + `dialog_name|` +
  `<inputName>|<value>` — measured, not guessed. Two things learned the hard
  way: the dialog name must not contain a pipe (end_dialog is
  `name|cancel|ok`, so pipes become button labels), and **a User Door cannot be
  wrenched** — 0x43e450 allows materials 2, 3 and 4 only, and a User Door is 7.
  Nor can you wrench the door you are standing in; that gesture enters it.
* **Lava kills.** Material 10 is lava and `OnKilled` is the death call; the
  client does the burn and the knockback but has no notion of dying, so the
  server sends OnKilled and puts you back at the spawn point.
* **The sounds the exe never names** now get played through
  `OnPlayPositioned`: `tile_removed` on a break, `punch_organic` on an unripe
  tree, `tree_harvest` on a ripe one, `punch_locked` on someone else's lock,
  `door_open`/`door_shut` on a door.

Still on the table, all pinned and unused: `OnSetFreezeState` (writes
avatar+0x190, and the click handler already refuses to act while it is
non-zero), `OnAddNotification` (`msg|`, `imageFile|`, `audioFile|`, `delayMS|`),
`OnAddLog`, `OnNameChanged`, `OnFailedToEnterWorld`, `OnReconnect`,
`OnZoomCamera`, `OnPinchMod`; packetTypes 5, 6, 13 and 15 on the receive side
and 10 on the send side; and the items the art proves but
`item_definitions.txt` lacks — above all `tiles_woodplatform.rttex`, the only
plausible owner of collision value 2, the one-way platform.

## 9. Restored after that

* **packetType 10 is the wear gesture.** There are exactly four places the
  client builds a 56-byte packet (every `push 0x38` / `call 0x4a1b30` pair):
  0x430c90 sends type 7 with a tile, 0x430cf0 sends type 10 with one int in
  intData, 0x430f00 sends type 3, and 0x431c35 sends type 11 (still
  unidentified). Type 10 comes from 0x43615a, reached only when the inventory
  cell you clicked is the one already selected *and* the item's material is 14.
  So clicking a garment twice wears it, and that is now handled — the
  click-a-tile-while-holding-clothes route still works, because the client
  really does send type 3 for that too.

* **The wood platform.** `tiles_woodplatform.rttex` is 128x32 — four frames: a
  left cap, two middles with legs, a right cap, which is exactly what a
  left/right smart edge (storage 3) consumes. Give it collision 2 and both
  orphaned enum values have an owner. Verified by spawning the avatar around a
  generated run (`BUILDO_FEAT=w`):

  | spawn | result | meaning |
  |---|---|---|
  | y=700, above the run | rests at y=834 | 834 + 30 = 864 = the row's top edge — it catches you |
  | y=880, inside the row | falls to y=930 | straight through to the ground, same as no platform |

  Solid from above, transparent from anywhere else. The only invented parts are
  the item id (102, `BUILDO_PLATFORM_ID`) and the name, because
  item_definitions.txt does not list it and nothing in the client hard-codes it
  the way 112 is hard-coded for gems.

## 10. Restored after that, again

* **The pickup handshake is the client's, not ours.** The server used to watch
  positions and collect things by itself. It only worked because the client was
  already asking (packetType 11) and being ignored. Now: client touches ->
  plays object_collect.wav -> sends 11 -> server answers 14. Verified, 5 -> 6
  dirt, with the position polling deleted.

* **packetType 13 fixed a real drift.** The client does NOT deduct on
  placement — measured: placing Grass, a Painting and a Toilet left all three
  counts at 5 while the server had taken one of each, so the two sides slid
  apart until the server refused placements for items the client still showed.
  One packetType 13 per placement keeps them equal. Verified 5 -> 4.

* **packetType 5 pushes a whole tile**, TileExtra included, in the world-blob
  shape. That is the only way to change a tile's extra live, which is what a
  label edited with the wrench needed — packetType 3 carries an item id and
  nothing else.

* **Tiles the art proves.** Every texture below was one no item claimed. The
  toilet earns its material exactly the way the platform earned its collision:
  `audio/toilet_flush.wav` is a sound the exe never names, **material 5** (punch
  plays the item's third string) is a material nothing shipped uses, and one
  orphan explains the other.

  | id | item | evidence |
  |---|---|---|
  | 102 | Wood Platform | collision 2 + storage 3, both otherwise unexplained |
  | 104 | Toilet | material 5 + the orphan flush sound |
  | 106 | Grass | tiles_grass.rttex, 4 tufts |
  | 108 | Flower | tiles_flowers.rttex, one daisy |
  | 110 | Painting | tiles_paintings.rttex, drawn as a background |
  | 114 | Rock Background | tiles_rockbackgd.rttex, ~47 smart-edge frames |

  The textures and frame counts are facts; **the ids, names and HP are ours** —
  only the gem's 112 is hard-coded by the client. `BUILDO_NO_EXTRA_ITEMS` leaves
  them all out.

Still unused and pinned: `OnSetFreezeState`, `OnAddNotification`, `OnAddLog`,
`OnNameChanged`, `OnFailedToEnterWorld`, `OnReconnect`, `OnZoomCamera`,
`OnPinchMod`; receive-side packet 6.

## 11. Locks, all three doors, and what is left of seeds

**The lock has no radius, and never did.** packetType 15 goes through
World::ApplyPacket to 0x441070, which:

* places the lock item at intX/intY (`SetItem`, 0x43e6d0),
* sets the TileExtra's owner from the packet's **netID** (0x43ee10 writes
  extra+8),
* then walks **netID2** uint16s out of the extended data as TILE INDICES,
  calling 0x43e2e0 on each — and that writes the lock's own index into
  **tile+0x34** and ORs **tile flag 0x02**, which is exactly the conditional
  uint16 the world blob carries.

So a lock's area is an explicit list the server chooses. There was no radius to
find; the original server picked a set of tiles just as we now do
(`BUILDO_LOCK_SIZE`, default a 10x10 square). Verified: placing a lock draws the
green dashed `lock_outline.rttex` boundary around the sent tiles.

The extra's list at +0x70/+0x74 is the ACCESS list of user ids, and 0x43ee20 is
the test — you pass if you are the owner or you are in the list. The renderer
picks the lock's frame from that (0x444662), which is what tiles_lock's four
frames are for. **The client draws all of this and enforces none of it** — every
read of tile+0x34 is in the renderer — so refusing edits is the server's job,
which is what `audio/punch_locked.wav` was always for.

**There are three doors, not one.** `item_definitions.txt` has 6 Door
(material 2), 12 User Door and **30 Dungeon Door** (both material 7), and
materials 2 and 7 both get a type-1 TileExtra — precisely what the client's
door-entry test looks for (0x43e280: `extra->type == 1`). All three verified
carrying a player to another world by their label. `BUILDO_DOOR_ITEM` picks
which one the generator lays down.

Only the white Door can be wrenched, though: 0x43e450 allows materials 2, 3 and
4, so the two material-7 doors cannot be relabelled in game, and neither can the
door you are standing in. Player-linkable doors really were a later-Growtopia
thing; on this build the server sets a door's destination.

**Seeds are done except for one number.** The chain is plant -> sapling -> six
stages -> a tree bearing the block it grew from -> punch to harvest, all
verified. What stays unpinned is how many fruit: the tree renderer reads the
TILE's flags at 0x4449aa (`mov al,[edi+4]; shr al,4`) and SetTile fills flags
0x08/0x10 from a packet's count1, but driving count1 changed nothing on screen
(0, 2 and 4 all drew the same sapling), and a second packetType 3 for the same
tile risks SetItem allocating a fresh extra and losing the growth stage. In
practice the fruit appears from the STAGE alone — a ripe tree drew five blocks
without any flag being set — so the count is emergent, not something we choose.
