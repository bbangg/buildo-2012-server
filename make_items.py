#!/usr/bin/env python3
"""Compile game/item_definitions.txt into the binary items.dat this build wants.

Container (client: VA 0x43C090)
    uint16 version
    uint32 itemCount
    itemCount x item record        (cursor starts at 6)

Item record - 30 fields, 57 fixed bytes plus three strings. Transcribed from
the client's symmetric (de)serializer at VA 0x43ACC0, whose `bl` flag selects
read vs write, so the on-disk order reads straight off the cursor advances:

    4,1,1,S,S,4,1,4,1,1,1,1,1,1,4,1,2,1,S,4,4,1,1,1,1,4,4,2,2,4

30 fields, 57 fixed bytes. NOTE: the final field's write and read
branches each carry their own cursor advance before returning, so a
naive scan of `add $N,(%esi)` counts it twice - it is ONE field.

Strings are uint16 length + raw bytes (serializer 0x456380). In-memory record
is 0xAC = 172 bytes.

IMPORTANT: the client indexes this array BY ITEM ID, not sequentially --
    443916  mov  ebp, edi        ; item id
    443918  imul ebp, ebp, 0xac
    44391E  add  ebp, [esi+0xc]
so the array must be DENSE: entry N describes item id N. A sparse array makes
every lookup return the wrong item.
"""
import struct, sys, pathlib, os

SRC = pathlib.Path(sys.argv[1] if len(sys.argv) > 1
                   else pathlib.Path.home()/"buildo-run"/"game"/"item_definitions.txt")
OUT = pathlib.Path(sys.argv[2] if len(sys.argv) > 2
                   else pathlib.Path.home()/"buildo-server"/"items.dat")
VERSION = int(sys.argv[3]) if len(sys.argv) > 3 else 2
FILLER  = "tileset_1.rttex"     # gap entries need a texture that exists

# Clothing body part (ItemInfo+0x68). The inventory writes the worn item id
# to PlayerItems + 6 + bodyPart*2 (0x43dcd0) and the read path clears exactly
# 12 bytes there (0x43dbdf), so there are six slots, 0..5. OnSetClothing
# carries the same six as two vec3s (0x448ad0). Which name owns which index
# is NOT pinned by the binary -- it only decides the layer an item is drawn
# on -- so this is the order the names first appear in item_definitions.txt,
# checked against how the avatar actually renders.
# The body part (ItemInfo+0x68) is nothing but the SLOT INDEX in the six-entry
# array OnSetClothing fills, and the slot index alone picks which sprite sheet
# the avatar renderer draws that item from -- the item's own texture filename
# is ignored for clothing. The client's loader (0x44bd49..0x44c091) walks the
# sheets in this order:
#
#     game/player_hair.rttex        slot 0
#     game/player_shirt.rttex       slot 1
#     game/player_pants.rttex       slot 2
#     game/player_feet.rttex        slot 3
#     game/player_faceitem.rttex    slot 4
#     game/player_handitem.rttex    slot 5
#
# The loader's own order interleaves player_arm, player_puncharm and
# player_face with these, and trusting it put SHOES and FACEITEM the wrong way
# round, so the mapping was read off the screen instead: six hair items with
# frames 1..6 were worn one per slot, and whichever frame each body part drew
# named its slot (red hair on the head -> hair is slot 0, ruby slippers on the
# feet -> feet is slot 3, shades on the face -> faceitem is slot 4). With HAT
# at 3 a top hat came out as red hair, because the hair layer was drawing
# whatever sat in slot 0.
#
# The frame inside the sheet is frameX + frameY*8 (0x44a055: `movzx ecx,
# [eax+0x51]; movzx edx,[eax+0x50]; lea eax,[edx+ecx*8]`), and the sheets are
# 256px/8 columns wide, which is why frame 3 of player_hair is the top hat.
BODY = {
    "HAT":      0,
    "SHIRT":    1,
    "PANTS":    2,
    "SHOES":    3,
    "FACEITEM": 4,
    "HAND":     5,
}

# eTileMaterial (ItemInfo+0x04). Only a handful of values change what the
# client does, and every one of those is pinned by the binary:
#
#   0     SetTile takes the "remove" path -- clear the foreground, or the
#         background if there is no foreground (0x4412b5 / 0x44133e).
#         The client punches by sending item 18, so the Fist must be 0.
#   2, 7  tile gets a TileExtra of type 1              (0x43eccd)
#   3     tile gets a TileExtra of type 3, and the renderer draws the lock
#         overlay from the owner id in it (0x43ed08, 0x444662).  tiles_lock
#         .rttex has exactly the 4 frames that branch selects.
#   4     tile gets a TileExtra of type 2              (0x43ecd5)
#   5     punching plays the sound named by the item's THIRD STRING
#         (ItemInfo+0x88), rate limited by ItemInfo+0xa8
#                                                      (0x43e56b / 0x4445ea)
#   6     punching toggles tile flag 0x40 and the renderer animates the tile
#         while it is set, stepping frame +1/+2 on a period taken from
#         ItemInfo+0xa8                                (0x43e55c / 0x444556)
#   12    SetTile writes the BACKGROUND (tile+0x02) instead of the
#         foreground (0x4412de -> 0x43e1f0)
#   13    seed: only plantable on an empty tile, and gets a TileExtra with a
#         plant timestamp and a growth stage           (0x4412ba / 0x43ecdd)
#   14    clothing: the inventory equips it using the body part at
#         ItemInfo+0x68                                (0x43dcbf)
#   15    used by 0x442cd6
#
# 5 is emphatically not inert -- giving Dirt material 5 makes punching it
# try to play its texture filename as a sound. Neither is 1, and neither is
# 10:
#
#   1  NOT PLACEABLE. The world-click handler at 0x436efa does
#          mov eax,[ebp+4]   ; the held item's material
#          cmp eax,1 ; sete bl
#      and on an empty tile `test bl,bl / jne` jumps straight to
#      audio/cant_place_tile.wav -- the client sends the server nothing at
#      all. On an OCCUPIED tile it calls 0x43e450 instead, which returns
#      (ItemInfo[tile->fg].material - 2) <= 2, i.e. true only for DOOR(2),
#      LOCK(3) and SIGN(4), and acts only then. That is the WRENCH exactly:
#      a tool that cannot be placed and that works on doors, locks and signs.
#      Dirt, Lava, Bedrock, Rock and Wood all used to get 1 from
#      NEUTRAL_MATERIAL, which is why none of them could be placed and why
#      the wrench looked dead -- it was never dead, the server just treated
#      its packet as a failed placement.
#  10  the collision response at 0x4474e0 negates the avatar's velocity,
#      plays audio/burn.wav (the string at 0x4cc3a0) and raises state flag
#      0x40. That is LAVA.
#
# 8, 9 and 11 are the only values compared against NOWHERE in the binary --
# the SetItem switch's index table at 0x43e83c sends all three to the
# no-TileExtra case -- so a plain block gets one of those. Which of the three
# the original build used for Dirt vs Bedrock vs Rock is NOT recoverable:
# nothing in the binary tells them apart.
#
# BOOMBOX is 6: it is the only item in item_definitions.txt whose tilesheet
# (tiles_boombox.rttex, 4x4 frames, one item per row) has the extra frames
# the material-6 animation steps through, and "punch it to turn it on" is
# what that branch does.
NEUTRAL_MATERIAL = 8        # provably inert: no branch anywhere in the binary
MATERIAL = {
    "TILE_MATERIAL_FIST":       0,
    "TILE_MATERIAL_DOOR":       2,
    "TILE_MATERIAL_LOCK":       3,
    "TILE_MATERIAL_SIGN":       4,
    "TILE_MATERIAL_BOOMBOX":    6,
    "TILE_MATERIAL_USER_DOOR":  7,
    "TILE_MATERIAL_BACKGROUND": 12,
    "TILE_MATERIAL_SEED":       13,
    "TILE_MATERIAL_CLOTHES":    14,
    "TILE_MATERIAL_WRENCH":     1,     # the not-placeable tool material
    "TILE_MATERIAL_LAVA":       10,    # audio/burn.wav + knockback
    # a plain block: inert, and which inert value each one had is not pinned
    "TILE_MATERIAL_DIRT":       NEUTRAL_MATERIAL,
    "TILE_MATERIAL_BEDROCK":    NEUTRAL_MATERIAL,
    "TILE_MATERIAL_ROCK":       NEUTRAL_MATERIAL,
    "TILE_MATERIAL_WOOD":       NEUTRAL_MATERIAL,
}
# materials whose tiles carry a TileExtra in the world blob
EXTRA_FOR_MATERIAL = {2: 1, 7: 1, 4: 2, 3: 3, 13: 4}
VISUAL    = {"TILE_VISUAL_EFFECT_NONE": 0}
# eTileStorage (ItemInfo+0x54) decides where a tile's frame index comes from.
# The renderer at 0x444522 is
#     frame = (storage == 1) ? frameY * sheetColumns + frameX : tile[+0x0a]
# and tile+0x0a is filled by the dispatch at 0x440f38 (jump table 0x440fe8):
#     0, 1 -> frame 0            2 -> 0x4404a0 (four-neighbour smart edge)
#                                3 -> 0x440390 (left/right smart edge)
# so SINGLE_FRAME_IN_TILESHEET is 1 and SMART_EDGE is 2. With SMART_EDGE
# written as 1 the dirt renders as one flat frame with no grass edge; with 2
# the grass, corners and cave edges all appear.
STORAGE   = {"TILE_STORAGE_SINGLE_FRAME_IN_TILESHEET": 1,
             "TILE_STORAGE_SMART_EDGE": 2,
             # Value 3 is pinned by the dispatch (0x440390, left/right smart
             # edge); the token NAME is ours, item_definitions.txt never uses it.
             "TILE_STORAGE_SMART_EDGE_LEFT_RIGHT": 3}
# The client stores this at ItemInfo+0x5c, and Tile::SetItem (0x43e793) uses
# it TWICE:
#
#     mov  eax,[edi+0x5c]     ; ItemInfo.collision
#     cmp  eax,0
#     setne cl
#     mov  [esi+0x10],eax     ; tile.collision
#     mov  [esi+0x0e],cl      ; tile takes part in collision AT ALL
#
# and tile+0x0e is what the collision query at 0x44207f filters on: a tile
# with +0x0e == 0 is skipped outright, one with +0x0e != 0 gets a box, and
# 0x4420e0 picks which box -- the full 32x32 tile when collision != 2, or a
# ONE-PIXEL STRIP AT THE TILE'S TOP EDGE when it is exactly 2. So the field
# has three meanings, not two:
#
#     0  no collision at all -- the tile is not even considered   <- air
#     1  solid                                                    <- dirt
#     2  one-way platform: you land on its top edge and pass through
#        otherwise. IsTileBlocking (0x4497b0, `[0x10] != 2`) calls it
#        non-blocking, which is why it looks like "NONE" from that one
#        function alone. No item in this build uses it.
#
# NONE was 2 here for a long time, and 2 gives every EMPTY tile in the world
# +0x0e = 1 -- turning all 6000 sky tiles into 1-pixel platforms. The avatar
# then lands on the top edge of whichever tile row it happens to fall into
# and can never descend: it rests in mid-air with the ground flag set, each
# jump lifts it exactly one tile (and bonks its head on the strip above,
# which is why the jump looked so short), and it never comes back down.
# Measured before/after with tools/probe.sh av, which prints the tile column
# under the avatar including the empty tiles the world dump skips.
COLLISION = {"TILE_COLLISION_NONE": 0, "TILE_COLLISION_SOLID": 1}

# Materials 5 and 6 both read a PERIOD IN MILLISECONDS from ItemInfo+0xa8
# (the same slot that holds a seed's foreground colour, which is why only one
# of the two can ever be set): material 5 rate-limits its punch sound with it
# and material 6 animates the switched-on tile on it. The renderer at
# 0x444573 does a bare
#
#     mov ebp,[esi+0xa8] ; ... ; xor edx,edx ; div ebp
#
# so a zero there is an integer divide by zero (confirmed: wine reports
# c0000094 at addr=00444573 with ebp=0) the frame after a material-6 punch
# sets tile flag 0x40 -- punching a Boombox or the Olde Timey Radio killed
# the client outright.
#
# The sound is the item's THIRD STRING (ItemInfo+0x88, played by 0x4445ea and
# by the material-6 branch at 0x4445d3). item_definitions.txt has no column
# for either value, so the server supplies them, the same way it supplies
# set_max_can_hold. The build ships audio/mp3/{boombox,old_timey}.mp3 and the
# only two material-6 items in the file are Boombox and Olde Timey Radio, so
# the pairing is not a guess.
BOOMBOX_SOUND = {
    "Boombox":          "audio/mp3/boombox.mp3",
    "Olde Timey Radio": "audio/mp3/old_timey.mp3",
}
SOUND_MATERIALS = (5, 6)    # the two that read ItemInfo+0x88 / +0xa8
ANIM_PERIOD_MS  = 250       # frame flip / sound retrigger period

# Every setup_seed line in item_definitions.txt ships `seconds_to_bloom|0` and
# `max_fruit|0`, so with the field in the right slot a tree is ripe the instant
# it is planted and yields nothing. That is what the shipped data says, not a
# bug -- these are placeholder values in a prototype. BUILDO_BLOOM sets a
# growing time so the mechanic is actually visible; it is OURS, not restored.
# Default to what the file says -- 0, ripe on arrival -- so the shipped data is
# what you get. BUILDO_BLOOM makes a plant take time, which is ours.
DEFAULT_BLOOM = int(os.environ.get("BUILDO_BLOOM", "0"))

# The client hard-codes ONE item id: 112. The object-collect path at 0x434206 is
#     cmp ax, 0x70 / jne normal ; add [app+0x130], count
# i.e. picking up an object whose item id is 112 adds straight to the bux/gem
# counter that RenderBuxComponent draws, instead of going into the inventory.
# item_definitions.txt has no entry for it, and tiles_bux.rttex is one of the
# textures no item claims, so the pairing is inferred from those two facts
# (plus audio/gem_pickup.wav) rather than pinned by the binary.
GEM_ITEM_ID = 112

FORCE_STORAGE = os.environ.get("FORCE_STORAGE")
ZERO_ENUMS    = os.environ.get("ZERO_ENUMS")   # bisect helper: null every guessed enum
# per-field bisect knobs; "1" = emit the real value, otherwise 0
KEEP_MAT  = os.environ.get("KEEP_MATERIAL")
KEEP_VIS  = os.environ.get("KEEP_VISUAL")
KEEP_COL  = os.environ.get("KEEP_COLLISION")
KEEP_BODY = os.environ.get("KEEP_BODY")

def rgba(spec):
    """"r,g,b,a" -> the packed uint32 the client stores at ItemInfo+0xa4/+0xa8,
    same byte order as set_color below."""
    try:
        r, g, b, a = [int(v) for v in spec.split(",")[:4]]
    except (ValueError, IndexError):
        return 0
    return ((a & 0xFF) << 24) | ((b & 0xFF) << 16) | ((g & 0xFF) << 8) | (r & 0xFF)

def enum_id(table, name):
    if name not in table: table[name] = len(table)
    return table[name]

def proton_hash(b):
    h = 0x55555555
    for c in b: h = ((h >> 27) + ((h << 5) & 0xFFFFFFFF) + c) & 0xFFFFFFFF
    return h

class Item:
    def __init__(self, iid):
        self.id = iid
        self.material = self.visual = self.storage = 0
        self.name = ""; self.file = FILLER; self.texhash = 0
        self.color = 0xFFFFFFFF
        self.fx = self.fy = 0
        self.layer = 0; self.collision = 0
        self.hp = 4; self.heal = 8
        self.maxhold = 0; self.body = 0
        self.sound = ""             # field 18, mem+0x88 (material 5 plays it)
        self.rarity = 0             # field 16, mem+0x84 (shown on selection)
        self.seed1 = self.seed2 = 0 # fields 21, 22
        self.bloom = 0              # field 25
        self.seedbg = self.seedfg = 0   # fields 19, 20
        self.tail = [0]*13          # fields 16,17,19..29 (semantics unknown)

items = {}
def get(iid):
    if iid not in items: items[iid] = Item(iid)
    return items[iid]

for raw in SRC.read_text(errors="replace").splitlines():
    line = raw.split("//")[0].strip()
    if not line: continue
    f = line.split("|"); cmd = f[0]
    try:
        if cmd == "add_tile" and len(f) >= 13:
            it = get(int(f[1]))
            it.name     = f[2]
            it.material = MATERIAL.get(f[3], NEUTRAL_MATERIAL)
            it.visual   = enum_id(VISUAL,   f[4])
            it.storage  = STORAGE.get(f[5], 1)
            it.fx, it.fy = int(f[6]), int(f[7])
            it.file     = f[8] or FILLER
            it.texhash  = int(f[9])
            it.layer    = int(f[10])
            it.collision= COLLISION.get(f[11], 1)
            it.hp       = int(f[12])
            if len(f) > 13 and f[13]: it.heal = int(f[13])
        elif cmd == "add_clothes" and len(f) >= 10:
            it = get(int(f[1]))
            it.name     = f[2]
            it.material = MATERIAL.get(f[3], NEUTRAL_MATERIAL)
            it.visual   = enum_id(VISUAL,   f[4])
            it.storage  = STORAGE.get(f[5], 1)
            it.fx, it.fy = int(f[6]), int(f[7])
            it.file     = f[8] or FILLER
            it.texhash  = int(f[9])
            it.body     = BODY.get(f[10].strip(), 0)
        elif cmd == "setup_seed" and len(f) >= 2:
            # setup_seed|id|seed1|N|seed2|N|seconds_to_bloom|N|max_fruit|N|
            #            bg_color|r,g,b,a|fg_color|r,g,b,a|
            it = get(int(f[1]))     # a seed item, material 13
            it.material = MATERIAL["TILE_MATERIAL_SEED"]
            if not it.name:
                it.name = f"Seed {f[1]}"
            it.file = "seed.rttex"
            it.storage = STORAGE["TILE_STORAGE_SINGLE_FRAME_IN_TILESHEET"]
            it.collision = COLLISION["TILE_COLLISION_NONE"]
            kv = {f[i]: f[i + 1] for i in range(2, len(f) - 1, 2)}
            it.seed1 = int(kv.get("seed1", 0) or 0)
            it.seed2 = int(kv.get("seed2", 0) or 0)
            it.bloom = int(kv.get("seconds_to_bloom", 0) or 0)
            it.seedbg = rgba(kv.get("bg_color", ""))
            it.seedfg = rgba(kv.get("fg_color", ""))
        elif cmd == "set_max_can_hold" and len(f) >= 3:
            get(int(f[1])).maxhold = int(f[2])
        elif cmd == "set_color" and len(f) >= 5 and items:
            it = items[max(items)]
            it.color = ((int(f[4]) & 0xFF) << 24) | ((int(f[3]) & 0xFF) << 16) \
                     | ((int(f[2]) & 0xFF) << 8) | (int(f[1]) & 0xFF)
    except (ValueError, IndexError):
        continue

# Give every material 5/6 item its track and a non-zero period. The period is
# mandatory: 0 there is the divide by zero at 0x444573 described above.
for _it in items.values():
    if _it.material not in SOUND_MATERIALS:
        continue
    if not _it.sound:
        _it.sound = BOOMBOX_SOUND.get(_it.name, "")
    if not _it.seedfg:
        _it.seedfg = ANIM_PERIOD_MS

# Seeds: give them a bloom time so a planted seed is a growing tree.
if DEFAULT_BLOOM:
    for _it in items.values():
        if _it.material == MATERIAL["TILE_MATERIAL_SEED"] and not _it.bloom:
            _it.bloom = DEFAULT_BLOOM

# The gem pickup. Material is the inert one -- it is never a tile, only ever a
# dropped object -- and tiles_bux.rttex is the sheet nothing else uses.
_gem = get(GEM_ITEM_ID)
if not _gem.name:
    _gem.name      = "Gems"
    _gem.material  = NEUTRAL_MATERIAL
    _gem.storage   = STORAGE["TILE_STORAGE_SINGLE_FRAME_IN_TILESHEET"]
    _gem.file      = "tiles_bux.rttex"
    _gem.fx, _gem.fy = 0, 0
    _gem.collision = COLLISION["TILE_COLLISION_NONE"]
    _gem.hp        = 1

# The wood platform. This is the item that explains the last two enum values
# nothing else claims: collision 2, the one-way platform whose box the query at
# 0x4420e0 shrinks to a 1-pixel strip at the tile's top edge, and storage 3, the
# left/right smart edge dispatched at 0x440390. tiles_woodplatform.rttex is
# 128x32 -- exactly four frames, a left cap, two middles and a right cap, which
# is what a left/right smart edge needs. Every property here is pinned by the
# binary and the art; only the ITEM ID and the name are ours, because
# item_definitions.txt does not list it and nothing in the client hard-codes it
# (unlike the gem's 112).
PLATFORM_ITEM_ID = int(os.environ.get("BUILDO_PLATFORM_ID", "102"))
_plat = get(PLATFORM_ITEM_ID)
if not _plat.name:
    _plat.name      = "Wood Platform"
    _plat.material  = NEUTRAL_MATERIAL
    _plat.storage   = STORAGE["TILE_STORAGE_SMART_EDGE_LEFT_RIGHT"]
    _plat.file      = "tiles_woodplatform.rttex"
    _plat.fx, _plat.fy = 0, 0
    _plat.collision = 2          # stand on top, walk through from any other side
    _plat.hp        = 3
    _plat.heal      = 8

# ---------------------------------------------------------------------------
# Tiles the shipped ART proves existed, which item_definitions.txt does not
# list. Every texture below is one nothing else in the file claims, so the tile
# was built and then left out of the copy of the item list Seth shipped.
#
# What is evidence and what is not: the TEXTURE and its frame count are facts,
# and the toilet earns its material the same way the platform earned its
# collision -- audio/toilet_flush.wav is a sound the exe never names, and
# material 5 (punch plays the item's third string, rate limited by +0xa8) is a
# material nothing shipped uses. One orphan explains the other. The ITEM IDS,
# names and HP are ours: only the gem's 112 is hard-coded by the client.
# BUILDO_NO_EXTRA_ITEMS leaves them all out.
EXTRA_ITEMS = not os.environ.get("BUILDO_NO_EXTRA_ITEMS")
if EXTRA_ITEMS:
    def _extra(iid, name, tex, mat, coll, fx=0, fy=0, stor=1, hp=3, snd=""):
        it = get(iid)
        if it.name: return
        it.name, it.file = name, tex
        it.material, it.collision, it.storage = mat, coll, stor
        it.fx, it.fy, it.hp, it.sound = fx, fy, hp, snd

    _extra(104, "Toilet", "tiles_toilet.rttex", 5,
           COLLISION["TILE_COLLISION_NONE"], 0, 0, 1, 4,
           "audio/toilet_flush.wav")
    _extra(106, "Grass", "tiles_grass.rttex", NEUTRAL_MATERIAL,
           COLLISION["TILE_COLLISION_NONE"], 0, 0, 1, 1)
    _extra(108, "Flower", "tiles_flowers.rttex", NEUTRAL_MATERIAL,
           COLLISION["TILE_COLLISION_NONE"], 0, 0, 1, 1)
    _extra(110, "Painting", "tiles_paintings.rttex",
           MATERIAL["TILE_MATERIAL_BACKGROUND"],
           COLLISION["TILE_COLLISION_NONE"], 0, 0, 1, 2)
    _extra(114, "Rock Background", "tiles_rockbackgd.rttex",
           MATERIAL["TILE_MATERIAL_BACKGROUND"],
           COLLISION["TILE_COLLISION_NONE"], 0, 0,
           STORAGE["TILE_STORAGE_SMART_EDGE"], 3)

maxid = max(items)
dense = []
for i in range(maxid + 1):
    it = items.get(i)
    if it is None:
        it = Item(i); it.name = ""
    it.id = i
    dense.append(it)

def s(v):
    b = v.encode("latin-1", "replace")
    return struct.pack("<H", len(b)) + b

out = bytearray()
out += struct.pack("<H", VERSION)
out += struct.pack("<I", len(dense))
for it in dense:
    t = it.tail
    out += struct.pack("<i", it.id)                              # 0
    # fields 1/2 crash the tile loader when non-zero; not yet identified
    mat = 0 if os.environ.get('ZERO_MATERIAL') else it.material
    vis = it.visual   if KEEP_VIS else 0
    out += struct.pack("<BB", mat & 0xFF, vis & 0xFF)             # 1,2
    out += s(it.name)                                            # 3
    out += s(it.file)                                            # 4
    out += struct.pack("<i", it.texhash)                         # 5
    out += struct.pack("<B", 0)                                  # 6 (unknown)
    out += struct.pack("<I", it.color & 0xFFFFFFFF)              # 7
    out += struct.pack("<BB", it.fx & 0xFF, it.fy & 0xFF)        # 8,9
    st = int(FORCE_STORAGE) if FORCE_STORAGE is not None else it.storage
    out += struct.pack("<B", st & 0xFF)                          # 10 eTileStorage
                                                                 #   ([item+0x54],
                                                                 #    switch 0..3 at 0x440FF8)
    # Slot 11 is mem+0x58 and slot 12 is mem+0x5c. Collision lives in 12 --
    # it used to be written into 11, which put item HP where the collision
    # value belongs. No item has HP 2, so every tile in the world came out
    # solid and the avatar could not move in any direction (not even fall).
    out += struct.pack("<B", 0)                                   # 11 mem+0x58
    col = 2 if os.environ.get('ZERO_COLLISION') else it.collision
    out += struct.pack("<B", col & 0xFF)                          # 12 mem+0x5c
    out += struct.pack("<B", it.hp & 0xFF)                       # 13 mem+0x60
    # Tile::Damage (0x43e4a0) reads ItemInfo+0x60 as the HP the damage counter
    # is clamped to and ItemInfo+0x64 as the number of seconds until it heals
    # (tile+0x2c = now_ms + [+0x64]*1000). That is exactly the trailing
    # "|HP|Seconds before healing|" pair in item_definitions.txt. max_can_hold
    # used to be written here, which put 0 in every heal timer.
    out += struct.pack("<i", it.heal)                            # 14 mem+0x64
    bod = it.body
    out += struct.pack("<B", bod & 0xFF)                          # 15 mem+0x68
    # Field 16 is the RARITY the client prints on selection: 0x4355df reads
    # it as `movzx ecx, word ptr [esi+0x84]` and passes it straight to
    # 'Selected `w%s``. Rarity: `w%d``' (0x4cb9d0). item_definitions.txt has
    # no column for it, so it stays 0 and the client says "Rarity: 0".
    out += struct.pack("<H", it.rarity & 0xFFFF)                  # 16 rarity
    out += struct.pack("<B", t[1] & 0xFF)                        # 17
    # ItemInfo+0x88 is a sound path: the material-5 branch at 0x4445ea plays
    # it when the tile is punched. item_definitions.txt has no column for it,
    # so it stays empty -- putting the texture filename here made a punch try
    # to play "dirt_tiles.rttex".
    out += s(it.sound)                                           # 18 mem+0x88
    out += struct.pack("<I", it.seedbg & 0xFFFFFFFF)             # 19 mem+0xa4
    out += struct.pack("<I", it.seedfg & 0xFFFFFFFF)             # 20 mem+0xa8
    out += struct.pack("<BBBB", it.seed1 & 0xFF, it.seed2 & 0xFF,
                       t[6] & 0xFF, t[7] & 0xFF)                 # 21-24
    out += struct.pack("<i", t[8]); out += struct.pack("<i", t[9])     # 25,26
    out += struct.pack("<H", t[10]&0xFFFF); out += struct.pack("<H", t[11]&0xFFFF)  # 27,28
    # Field 29 (+0x7c) is SECONDS TO BLOOM. The tree label code reads exactly
    # this slot: 0x43eaa8 `mov edi,[edi+0x7c]` on &ItemInfo[id], then subtracts
    # Tile::GetPlantAge (0x43ed30 = (now_ms - tile+0x60)/1000 + tile+0x64) and
    # shows "<time> to harvest" while positive, "(`wPunch to harvest``)" once
    # it goes negative. seconds_to_bloom used to be written into field 25
    # (+0x70), which nothing reads, so every seed was instantly ripe.
    out += struct.pack("<i", it.bloom)                                # 29 bloom

OUT.write_bytes(bytes(out))
h = proton_hash(out)
print(f"{OUT}: version={VERSION} entries={len(dense)} (dense 0..{maxid}) "
      f"defined={len(items)} bytes={len(out)} hash={h if h>>31==0 else h-(1<<32)}")
