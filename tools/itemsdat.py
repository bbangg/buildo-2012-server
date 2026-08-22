#!/usr/bin/env python3
"""Read / rewrite items.dat, the compiled item database this build loads.

Layout is transcribed from the client's own symmetric (de)serializer at
VA 0x43ACC0 -- 30 fields, 57 fixed bytes plus three length-prefixed strings.
The on-disk order and the in-memory offsets it copies to:

    disk#  type    mem      meaning (where established)
      0    int32   +0x00    item id
      1    uint8   +0x04    eTileMaterial   (switch at 0x43e7ac)
      2    uint8   +0x08    eTileVisualEffect
      3    string  +0x0c    display name
      4    string  +0x2c    texture file    (0x44393b prefixes "game/")
      5    int32   +0x28    texture hash
      6    uint8   +0x48
      7    int32   +0x4c    colour RGBA
      8    uint8   +0x50    frameX          (0x44452f)
      9    uint8   +0x51    frameY          (0x444528)
     10    uint8   +0x54    eTileStorage    (0x444522 / dispatch 0x440fe8)
     11    uint8   +0x58
     12    uint8   +0x5c    eCollisionType  (copied to Tile+0x10, 0x43e793)
     13    uint8   +0x60    HP
     14    int32   +0x64    max can hold
     15    uint8   +0x68    clothing body part
     16    uint16  +0x84
     17    uint8   +0x86
     18    string  +0x88
     19    int32   +0xa4    seed bg colour
     20    int32   +0xa8    seed fg colour
     21-24 uint8   +0x6c..+0x6f
     25    int32   +0x70
     26    int32   +0x74
     27    uint16  +0x78
     28    uint16  +0x7a
     29    int32   +0x7c

Container: uint16 version, uint32 count, then count records (0x43C090).
The array is indexed BY ITEM ID (imul 0xac at 0x443916), so it must be dense.

  itemsdat.py show FILE [id ...]
  itemsdat.py set  IN OUT field=value[,field=value...] [id|all ...]
  itemsdat.py hash FILE
"""
import struct, sys, pathlib

FIELDS = [
    ("id",       "i"), ("material", "B"), ("visual",  "B"),
    ("name",     "s"), ("file",     "s"), ("texhash", "i"),
    ("u48",      "B"), ("color",    "I"),
    ("fx",       "B"), ("fy",       "B"), ("storage", "B"),
    ("u58",      "B"), ("collision","B"), ("hp",      "B"),
    ("healsecs", "i"), ("body",     "B"),
    ("u84",      "H"), ("u86",      "B"), ("file2",   "s"),
    ("seedbg",   "i"), ("seedfg",   "i"),
    ("seed1",    "B"), ("seed2",    "B"), ("u6e",     "B"), ("u6f", "B"),
    ("bloom",    "i"), ("u74",      "i"), ("u78",     "H"), ("u7a", "H"),
    ("u7c",      "i"),
]
SZ = {"B": 1, "H": 2, "i": 4, "I": 4}


def proton_hash(b):
    h = 0x55555555
    for c in b:
        h = ((h >> 27) + ((h << 5) & 0xFFFFFFFF) + c) & 0xFFFFFFFF
    return h


def load(path):
    d = pathlib.Path(path).read_bytes()
    ver, count = struct.unpack_from("<HI", d, 0)
    p = 6
    items = []
    for _ in range(count):
        rec = {}
        for name, t in FIELDS:
            if t == "s":
                n = struct.unpack_from("<H", d, p)[0]; p += 2
                rec[name] = d[p:p + n].decode("latin-1"); p += n
            else:
                rec[name] = struct.unpack_from("<" + t, d, p)[0]; p += SZ[t]
        items.append(rec)
    if p != len(d):
        raise SystemExit(f"parse desync: consumed {p} of {len(d)} bytes")
    return ver, items


def dump(ver, items):
    out = bytearray(struct.pack("<HI", ver, len(items)))
    for rec in items:
        for name, t in FIELDS:
            if t == "s":
                b = rec[name].encode("latin-1", "replace")
                out += struct.pack("<H", len(b)) + b
            else:
                out += struct.pack("<" + t, rec[name])
    return bytes(out)


def main():
    if len(sys.argv) < 3:
        print(__doc__); return 2
    cmd, path = sys.argv[1], sys.argv[2]
    if cmd == "hash":
        d = pathlib.Path(path).read_bytes()
        h = proton_hash(d)
        print(f"{len(d)} bytes  hash={h} / {h - (1 << 32)} / 0x{h:08x}")
        return 0
    if cmd == "show":
        ver, items = load(path)
        want = [int(a) for a in sys.argv[3:]]
        print(f"version={ver} count={len(items)}")
        for rec in items:
            if want and rec["id"] not in want:
                continue
            if not want and not rec["name"]:
                continue
            print(" ".join(f"{k}={rec[k]!r}" if t == "s" else f"{k}={rec[k]}"
                           for k, t in FIELDS))
        return 0
    if cmd == "set":
        out_path = sys.argv[3]
        assigns = [a.split("=", 1) for a in sys.argv[4].split(",")]
        targets = sys.argv[5:] or ["all"]
        ver, items = load(path)
        ids = None if "all" in targets else {int(t) for t in targets}
        n = 0
        for rec in items:
            if ids is not None and rec["id"] not in ids:
                continue
            for k, v in assigns:
                # "storage:1>2" means only rewrite where the value is 1
                if ">" in v:
                    old, new = v.split(">")
                    if rec[k] != int(old):
                        continue
                    rec[k] = int(new)
                else:
                    rec[k] = int(v)
                n += 1
        blob = dump(ver, items)
        pathlib.Path(out_path).write_bytes(blob)
        h = proton_hash(blob)
        print(f"{out_path}: {len(blob)} bytes, {n} changes, hash={h - (1 << 32)}")
        return 0
    print(__doc__); return 2


if __name__ == "__main__":
    sys.exit(main())
