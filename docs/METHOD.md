# Method — how to prove a claim about this build

There are no dev notes, no readme and no `.pdb`. So nothing here is *read*; it
is *enumerated* and then *confirmed on screen*. This page is the working
method, because a restoration project lives or dies on the difference between
knowing and guessing.

If you contribute one finding to this repo, contribute it in this shape.

---

## The two rules that keep paying off

**1. If a feature exists, it left a string.** A name, a sound path, a texture
filename, or a printf format. The 2012 build has no dead-stripped resources —
anything the code can do, it can name.

**2. If the client has to be told something, the name is in one of the two
registration blocks.** Every server→client call is registered by string.
That makes "does this exist?" a one-line answer instead of an afternoon.

---

## Four closed lists

These are exhaustive. If a name is not in them, the client **cannot** do it,
and implementing it server-side is invention, not restoration. All four are
enumerated in [WHAT-EXISTS.md](WHAT-EXISTS.md).

| list | where | answers |
|---|---|---|
| handler registration blocks | GameLogicComponent 0x4349d1..0x4351a5, NetAvatar 0x4cc454..0x4cc4c4 | every server→client call that exists |
| the packetType jump table | 0x434418 | every packet the client can **receive** |
| `something\|` protocol keys | `.data` | every key name in the text protocol |
| material / storage / collision constants | compare sites in the renderer and click handler | every enum value the client branches on |

**The one trap in this method:** the jump table is what the client can
*receive*. What it *sends* is a different question and only the wire answers
it. packetTypes 7 and 10 both hit the receive table's `default` case, and the
client sends both — doors and the wear gesture were sitting there looking
unimplemented. To enumerate the send side, find the four outgoing packet
builders instead: `push 0x38` followed by `call 0x4a1b30`.

---

## The static-analysis loop

`ra.py` is a small capstone/pefile harness over the unpatched `Buildo.exe`.

```bash
source .venv/bin/activate
python3 ra.py strings SomeName     # does the name exist at all?
python3 ra.py xref 0xADDR          # who references it?
python3 ra.py dis 0xADDR 40        # what does it do?
python3 ra.py fn 0xADDR            # the whole function
python3 ra.py callers 0xADDR       # who calls it
python3 ra.py find 'REGEX'         # every instruction matching a pattern
python3 ra.py classes              # every class with a vtable
python3 ra.py str2fn SomeString    # string -> the function that uses it
```

`find` is the one that pins layouts. The record serialiser was found with a
pattern for `add $N,(%esi)`; the four outgoing packet builders were found with
`push 0x38`.

**Prefer a symmetric (de)serializer over either direction alone.** 0x43ACC0
uses a single `bl` register to select read versus write, so one function
describes the whole on-disk format — and reading only the write path is how
the 61-byte record miscount happened (the final field's read and write
branches each carry their own cursor advance).

---

## The dynamic-confirmation loop

Static analysis proposes; the running client disposes. Nothing goes in the
docs as fact until it has been seen.

```bash
tools/run.sh WORLDNAME      # launch into a world without regenerating items
./shot.sh out.png           # what is on screen
tools/probe.sh av           # the avatar and the tile column under it
tools/probe.sh world        # every non-empty tile as the CLIENT parsed it
tools/probe.sh inv          # what the client thinks you are holding
tools/probe.sh items        # the ItemInfo array as the client built it
```

`probe.sh` dumps the **client's own parsed structures**, not the bytes the
server sent. That distinction is the whole point: it shows you what the client
*understood*, which is where a misread field shows up as a wrong value rather
than as silence.

Three techniques worth reusing:

* **Bisect a field.** `tools/itemsdat.py` rewrites one field of a compiled
  `items.dat` and leaves everything else alone. Change one byte, relaunch,
  look. Every enum in [PROTOCOL.md](PROTOCOL.md) was pinned this way.
* **Feed the parser a deliberately short line.** The dialog parser at 0x417e40
  logs `Error with <cmd> parms` when a line has too few tokens, which names
  every command's argument count without reading a single instruction.
* **Measure the shape by byte count.** The world blob's TileExtra type 1 has
  two possible shapes. With the right one, the size the server sent and the
  size the client reports decompressing are identical and every later tile
  survives; with the wrong one the cursor runs off the end. That is a decisive
  test that needs no disassembly at all.

---

## Reading the unclaimed assets

`item_definitions.txt` is a subset of what the art and audio were built for, so
the leftovers are evidence:

* **A texture no item claims** proves an item existed. `tiles_bux.rttex` pairs
  with the hard-coded gem id 112; `tiles_woodplatform.rttex` is 128×32 = four
  frames, exactly what a left/right smart edge consumes.
* **A sound the exe never names** proves *original-server* behaviour, because
  the only way to reach it is an item's sound string or `OnPlayPositioned`.
  `punch_locked.wav` is proof that the original server refused punches inside
  a lock — behaviour the client does not implement.
* **An orphan enum value plus an orphan asset explain each other.** Collision 2
  (one-way platform) had no item, and the wood platform texture had no item:
  one answer. Material 5 (punch plays a sound) had no item, and
  `toilet_flush.wav` had no owner: one answer.

This is inference, not proof, and it is labelled as such in
[WHAT-EXISTS.md §6](WHAT-EXISTS.md#6-things-we-implemented-that-the-binary-does-not-pin).

---

## Where the addresses point

Every VA in these docs is into the **unpatched** `Buildo.exe`,
SHA-256 `fbec5a3c16af17c44c4eb54d43fc048df9f18fc9c3f0bc6fcef4ea8a7a933945`.
If yours differs, say so before filing anything address-shaped.

---

## The honesty rule

Anything not pinned by the binary gets written down as ours, in
[WHAT-EXISTS.md §6](WHAT-EXISTS.md#6-things-we-implemented-that-the-binary-does-not-pin),
with an env knob to turn it off wherever that is possible
(`BUILDO_GEM_CHANCE=0`, `BUILDO_NO_EXTRA_ITEMS`, `BUILDO_BLOOM=0`). Two
invented behaviours have already been **deleted** rather than kept — refusing
to place a solid tile on a player, and a tree handing back a spare seed.

A restoration that quietly includes inventions is worth less than one that
includes fewer things and says which is which.
