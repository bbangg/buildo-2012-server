#!/usr/bin/env python3
"""Convert Proton SDK .rttex textures to .png.

Format (verified against this 2012 Buildo build):
  RTPACK container, 32-byte header:
      char[6] "RTPACK", uint8 version, uint8 reserved
      uint32 compressedSize, uint32 decompressedSize
      uint8  compressionType (1 = zlib), char[15] reserved
    -> zlib stream of decompressedSize bytes containing:

  RTTEX, 100-byte header:
      char[6] "RTTXTR", uint8 version, uint8 reserved
      int32 height, width, format, originalHeight, originalWidth
      uint8 bUsesAlpha, bAlreadyCompressed, uint8[2] reservedFlags
      int32 mipmapCount, int32[16] reserved
    then per mip a 24-byte header:
      int32 height, width, dataSize, mipLevel, int32[2] reserved
    followed by dataSize bytes of raw pixels, bottom-up (OpenGL order).

Writes PNG with a tiny built-in encoder so nothing needs installing.
"""
import struct, zlib, sys, pathlib

def png(width, height, rgba):
    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    raw = bytearray()
    stride = width * 4
    for y in range(height):
        raw.append(0)                      # filter: none
        raw += rgba[y*stride:(y+1)*stride]
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))

def convert(path):
    d = pathlib.Path(path).read_bytes()
    if d[:6] == b"RTPACK":
        csize, dsize = struct.unpack_from("<II", d, 8)
        raw = zlib.decompress(d[32:32+csize])
    elif d[:6] == b"RTTXTR":
        raw = d
    else:
        raise ValueError(f"not an rttex: {d[:6]!r}")
    if raw[:6] != b"RTTXTR":
        raise ValueError("no RTTXTR inside container")

    h, w, fmt, oh, ow = struct.unpack_from("<iiiii", raw, 8)
    uses_alpha = raw[28]
    mh, mw, dsz, lvl = struct.unpack_from("<iiii", raw, 100)
    pix = raw[124:124+dsz]
    bpp = 4 if uses_alpha else 3
    if len(pix) < mw*mh*bpp:
        raise ValueError(f"short pixel data {len(pix)} < {mw*mh*bpp}")

    if bpp == 3:                            # pad RGB out to RGBA
        out = bytearray()
        for i in range(mw*mh):
            out += pix[i*3:i*3+3] + b"\xff"
        pix = bytes(out)

    stride = mw*4
    flipped = b"".join(pix[(mh-1-y)*stride:(mh-y)*stride] for y in range(mh))
    return mw, mh, flipped, (ow, oh), uses_alpha

if __name__ == "__main__":
    src = pathlib.Path(sys.argv[1] if len(sys.argv) > 1
                       else pathlib.Path.home()/"Downloads"/"OldAssBuildoWinFrom2012")
    dst = pathlib.Path(sys.argv[2] if len(sys.argv) > 2
                       else pathlib.Path.home()/"buildo-assets")
    ok = bad = 0
    for f in sorted(src.rglob("*.rttex")):
        rel = f.relative_to(src).with_suffix(".png")
        out = dst/rel
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            w, h, rgba, orig, alpha = convert(f)
            out.write_bytes(png(w, h, rgba))
            ok += 1
        except Exception as e:
            print(f"  FAILED {rel}: {e}")
            bad += 1
    print(f"converted {ok} textures -> {dst}" + (f"  ({bad} failed)" if bad else ""))
