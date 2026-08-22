# Contributing

This is a preservation project, so the bar is a little unusual: **the standard
is not "does it work", it is "how do you know the original did this".**

Read [docs/METHOD.md](docs/METHOD.md) first — it is the whole working method in
one page.

---

## Before you start

Check you have the same binary everyone else is reading:

    shasum -a 256 Buildo.exe
    fbec5a3c16af17c44c4eb54d43fc048df9f18fc9c3f0bc6fcef4ea8a7a933945

Every virtual address in the docs points into that exact file, unpatched. If
yours differs, say so up front — a different build makes every address on these
pages wrong.

Then check the thing you want to add actually exists:
[docs/WHAT-EXISTS.md](docs/WHAT-EXISTS.md) enumerates four closed lists. If a
name is not in them, the client cannot do it, and implementing it server-side
is invention rather than restoration. That is allowed — but it has to be
labelled.

---

## The shape of a good finding

Three parts, and the third is the one people skip:

1. **The static evidence.** A virtual address and what is there — the compare,
   the jump table entry, the string, the field offset.
2. **The dynamic confirmation.** What you saw on a running client. A
   `shot.sh` PNG, a `probe.sh` dump, a line out of `log.txt`. Before and after
   if it is a fix.
3. **What it is *not*.** The boundary of the claim. "This pins the field, not
   the value." "The texture proves the item existed; the id is mine."

A finding with only part 1 is a hypothesis. Say so, and it is still welcome —
just do not write it into the docs as fact.

### Example, from the log

> **Claim:** `eCollisionType` has three values, not two.
>
> **Static:** `Tile::SetItem` 0x43e793 writes `tile+0x10 = ItemInfo+0x5c` and
> `tile+0x0e = (collision != 0)`. The collision query at 0x44207f skips any
> tile whose +0x0e is 0; 0x4420e0 then picks a full 32×32 box unless collision
> is exactly 2, in which case a 1-pixel strip at the tile's top edge.
>
> **Dynamic:** `probe.sh av` before and after —
> `(50,28) fg=0 bg=0 blocked=1 coll=2` became
> `(50,28) fg=0 bg=0 blocked=0 coll=0`, and the avatar stopped floating.
>
> **Not:** this does not tell us which collision value any *shipped* item used
> — no item in `item_definitions.txt` uses 2. The Wood Platform is our
> attribution, argued separately from the texture's frame count.

---

## If it is not pinned, label it

Anything the binary does not prove goes in
[WHAT-EXISTS.md §6](docs/WHAT-EXISTS.md#6-things-we-implemented-that-the-binary-does-not-pin),
in the table, in your own words — and wherever it can be, behind an env knob
that turns it off (`BUILDO_GEM_CHANCE=0`, `BUILDO_NO_EXTRA_ITEMS`,
`BUILDO_BLOOM=0`) so anyone can run a build of only what is proven.

Two invented behaviours have already been deleted rather than kept. That is the
right instinct here: a restoration with fewer things in it that says which is
which is worth more than a complete-looking one that does not.

---

## Practical notes

- **Never modify `Buildo.exe`.** `patch_client.py` writes a copy and asserts
  the original bytes before every write.
- **No game files in commits.** No exe, no `game/`, no `interface/`, no
  `audio/` — `.gitignore` covers these, please do not force past it.
- **No build output either.** `gs`, `*.exe`, `*.dll`, `items.dat` and the logs
  are all rebuilt by commands in [docs/SETUP.md](docs/SETUP.md#4-build).
- **Do not send ESC or SPACE from a test script.** ESC quits to the main menu
  and SPACE opens the chat keyboard, either of which silently ends the run.
- **Match the surrounding style.** `server.cpp` explains *why* at each
  non-obvious decision, usually with the address that settled it. Keep that.

---

## Opening work

[docs/OPEN-QUESTIONS.md](docs/OPEN-QUESTIONS.md) lists what is available, with
the evidence already gathered, roughly ordered by value. Say in an issue if you
take one.

The single highest-value contribution anyone could make is not code: **a
server-side capture, a build with symbols, or any 2012-era Growtopia server
artefact.** Several of the things currently labelled "ours" would stop being
guesses.
