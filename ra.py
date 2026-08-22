#!/usr/bin/env python3
"""Static-analysis helper for Buildo.exe (PE32, x86, statically linked MSVC).

Everything here reads the pristine client; nothing is modified. Used to answer
"what does the real build actually do" instead of guessing.

    ra.py strings [substr]        list ASCII strings with their VAs
    ra.py xref VA                 find instructions embedding that VA as imm32
    ra.py dis VA [n]              disassemble n instructions at VA
    ra.py fn VA                   disassemble until ret/jmp-out (crude bounds)
    ra.py callers VA              find call sites targeting VA
    ra.py find REGEX             search all decoded instructions
    ra.py index                  index stats
    ra.py vt Class                vtable(s) for a class, via RTTI
    ra.py classes                 every class with a vtable
    ra.py str2fn substr           for each matching string, show functions
                                  (nearest preceding push-ebp) that reference it
"""
import os, sys, struct, bisect, pathlib
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

# The UNPATCHED exe -- every VA in the docs points into this one.
# Override the directory with BUILDO_SRC.
EXE = str(pathlib.Path(os.environ.get(
    "BUILDO_SRC", pathlib.Path.home()/"Downloads"/"OldAssBuildoWinFrom2012"))
    / "Buildo.exe")


class Img:
    def __init__(self, path=EXE):
        self.d = open(path, "rb").read()
        d = self.d
        pe = struct.unpack_from("<I", d, 0x3C)[0]
        nsec = struct.unpack_from("<H", d, pe + 6)[0]
        opthdr = struct.unpack_from("<H", d, pe + 20)[0]
        self.base = struct.unpack_from("<I", d, pe + 24 + 28)[0]
        self.secs = []
        for i in range(nsec):
            o = pe + 24 + opthdr + i * 40
            name = d[o:o + 8].rstrip(b"\0").decode(errors="replace")
            vsz, va, rsz, ptr = struct.unpack_from("<IIII", d, o + 8)
            self.secs.append((name, va, vsz, ptr, rsz))
        self.md = Cs(CS_ARCH_X86, CS_MODE_32)
        self.md.detail = True

    # ---- address conversion ----
    def va2off(self, va):
        rva = va - self.base
        for name, sva, vsz, ptr, rsz in self.secs:
            if sva <= rva < sva + max(vsz, rsz):
                off = ptr + (rva - sva)
                return off if off < len(self.d) else None
        return None

    def off2va(self, off):
        for name, sva, vsz, ptr, rsz in self.secs:
            if ptr <= off < ptr + rsz:
                return self.base + sva + (off - ptr)
        return None

    def sec_of(self, va):
        rva = va - self.base
        for name, sva, vsz, ptr, rsz in self.secs:
            if sva <= rva < sva + max(vsz, rsz):
                return name
        return None

    # ---- strings ----
    def strings(self, minlen=4):
        out = []
        d = self.d
        for name, sva, vsz, ptr, rsz in self.secs:
            if name not in (".rdata", ".data"):
                continue
            i = ptr
            end = ptr + rsz
            while i < end:
                j = i
                while j < end and 0x20 <= d[j] < 0x7F:
                    j += 1
                if j - i >= minlen and j < end and d[j] == 0:
                    out.append((self.off2va(i), d[i:j].decode()))
                i = j + 1
        return out

    # ---- xrefs to an immediate ----
    def imm_xrefs(self, target):
        """Every 4-byte little-endian occurrence of target inside .text,
        reported as the instruction containing it."""
        needle = struct.pack("<I", target)
        hits = []
        for name, sva, vsz, ptr, rsz in self.secs:
            if name != ".text":
                continue
            start = ptr
            end = ptr + rsz
            i = self.d.find(needle, start, end)
            while i != -1:
                # back up a little and disassemble forward to land on the insn
                for back in range(1, 8):
                    o = i - back
                    if o < start:
                        break
                    va = self.off2va(o)
                    for ins in self.md.disasm(self.d[o:o + 16], va):
                        if ins.address <= va < ins.address + ins.size and \
                           self.off2va(i) < ins.address + ins.size:
                            hits.append((ins.address,
                                         f"{ins.mnemonic} {ins.op_str}"))
                            break
                        break
                    if hits and hits[-1][0] == self.off2va(o):
                        break
                i = self.d.find(needle, i + 1, end)
        # dedupe
        seen, out = set(), []
        for a, t in hits:
            if a not in seen:
                seen.add(a)
                out.append((a, t))
        return out

    def dis(self, va, count=40):
        o = self.va2off(va)
        if o is None:
            return []
        return list(self.md.disasm(self.d[o:o + count * 16], va))[:count]

    def fn(self, va, maxins=400):
        """Disassemble until we hit a ret (crude, but enough to read code)."""
        out = []
        for ins in self.dis(va, maxins):
            out.append(ins)
            if ins.mnemonic in ("ret", "retn") or \
               (ins.mnemonic == "jmp" and ins.op_str.startswith("dword")):
                break
        return out

    def callers(self, target):
        """call sites whose direct target is `target`."""
        out = []
        for name, sva, vsz, ptr, rsz in self.secs:
            if name != ".text":
                continue
            va = self.base + sva
            code = self.d[ptr:ptr + rsz]
            for ins in self.md.disasm(code, va):
                if ins.mnemonic == "call" and ins.op_str.startswith("0x"):
                    try:
                        if int(ins.op_str, 16) == target:
                            out.append(ins.address)
                    except ValueError:
                        pass
        return out

    def fn_starts(self):
        """Addresses that look like function prologues (push ebp; mov ebp,esp
        or sub esp,N after push regs). Sorted, for 'which function is VA in'."""
        if hasattr(self, "_starts"):
            return self._starts
        starts = []
        for name, sva, vsz, ptr, rsz in self.secs:
            if name != ".text":
                continue
            va = self.base + sva
            code = self.d[ptr:ptr + rsz]
            prev = None
            for ins in self.md.disasm(code, va):
                if ins.mnemonic == "push" and ins.op_str == "ebp":
                    prev = ins.address
                elif prev is not None and ins.address == prev + 1 and \
                        ins.mnemonic == "mov" and ins.op_str == "ebp, esp":
                    starts.append(prev)
                    prev = None
                else:
                    prev = prev if ins.mnemonic == "push" and ins.op_str == "ebp" else None
        starts.sort()
        self._starts = starts
        return starts

    def owner_fn(self, va):
        st = self.fn_starts()
        i = bisect.bisect_right(st, va) - 1
        return st[i] if i >= 0 else None


    # ---- RTTI ----
    def _u32(self, va):
        o = self.va2off(va)
        return struct.unpack_from("<I", self.d, o)[0] if o is not None else None

    def type_descriptors(self):
        """{class name: type-descriptor VA}. MSVC TypeDescriptor is
        {void* vftable; void* spare; char name[];} so name VA - 8 is its start."""
        if hasattr(self, "_tds"):
            return self._tds
        out = {}
        for va, s in self.strings(minlen=4):
            if s.startswith(".?A"):
                out[s] = va - 8
        self._tds = out
        return out

    def vtables(self):
        """{class name: [vtable VAs]}. Walks TypeDescriptor -> Complete Object
        Locator -> vtable (the COL pointer sits at vtable-4)."""
        if hasattr(self, "_vts"):
            return self._vts
        tds = self.type_descriptors()
        td2name = {v: k for k, v in tds.items()}
        # every dword in .rdata/.data that points at a type descriptor, where
        # the containing struct looks like a COL (dword at -12 is 0 or 1)
        cols = {}
        for name, sva, vsz, ptr, rsz in self.secs:
            if name not in (".rdata", ".data"):
                continue
            for off in range(ptr, ptr + rsz - 4, 4):
                v = struct.unpack_from("<I", self.d, off)[0]
                if v in td2name:
                    col = self.off2va(off) - 12
                    o = self.va2off(col)
                    if o is None:
                        continue
                    sig = struct.unpack_from("<I", self.d, o)[0]
                    if sig in (0, 1):
                        cols[col] = td2name[v]
        out = {}
        for name, sva, vsz, ptr, rsz in self.secs:
            if name not in (".rdata", ".data"):
                continue
            for off in range(ptr, ptr + rsz - 4, 4):
                v = struct.unpack_from("<I", self.d, off)[0]
                if v in cols:
                    vt = self.off2va(off) + 4
                    out.setdefault(cols[v], []).append(vt)
        self._vts = out
        return out

    def vtable_of(self, cls):
        """cls may be a bare name ('NetMoving') or a mangled '.?AVX@@'."""
        vts = self.vtables()
        for k, v in vts.items():
            bare = k[4:].rstrip("@") if k.startswith(".?AV") else k
            if bare == cls or k == cls:
                return v
        return []

    def vtable_entries(self, vt, n=40):
        out = []
        for i in range(n):
            f = self._u32(vt + 4 * i)
            if f is None or self.sec_of(f) != ".text":
                break
            out.append((vt + 4 * i, f))
        return out

    # ---- recursive-descent code index ----
    def entry_point(self):
        pe = struct.unpack_from("<I", self.d, 0x3C)[0]
        return self.base + struct.unpack_from("<I", self.d, pe + 24 + 16)[0]

    def index(self):
        """Recursive-descent disassembly. Linear sweep desyncs on x86 padding
        and data, so seed from the entry point plus every vtable slot and
        follow calls/jumps. Returns {addr: (mnemonic, op_str, size)}."""
        if hasattr(self, "_idx"):
            return self._idx
        seeds = [self.entry_point()]
        for cls, vts in self.vtables().items():
            for vt in vts:
                for slot, fn in self.vtable_entries(vt, 64):
                    seeds.append(fn)
        # Any dword anywhere in the image that points into .text: vtables we
        # did not resolve, jump tables, and the boost::function targets that
        # most of the game's callbacks go through.
        for nm, sva, vsz, ptr, rsz in self.secs:
            for off in range(ptr, ptr + rsz - 4, 4):
                v = struct.unpack_from("<I", self.d, off)[0]
                if self.sec_of(v) == ".text":
                    seeds.append(v)
        insns = {}
        funcs = set()
        seen = set()
        work = list(seeds)
        while work:
            va = work.pop()
            if va in seen or self.sec_of(va) != ".text":
                continue
            seen.add(va)
            funcs.add(va)
            addr = va
            budget = 20000
            while budget > 0:
                budget -= 1
                if addr in insns:
                    break
                o = self.va2off(addr)
                if o is None:
                    break
                got = list(self.md.disasm(self.d[o:o + 16], addr, count=1))
                if not got:
                    break
                ins = got[0]
                insns[ins.address] = (ins.mnemonic, ins.op_str, ins.size)
                m, op = ins.mnemonic, ins.op_str
                if m == "call" and op.startswith("0x"):
                    try:
                        work.append(int(op, 16))
                    except ValueError:
                        pass
                elif m.startswith("j") and op.startswith("0x"):
                    try:
                        work.append(int(op, 16))
                    except ValueError:
                        pass
                    if m == "jmp":
                        break
                elif m in ("ret", "retn", "iret") or m == "jmp":
                    break
                elif m == "int3":
                    break
                addr = ins.address + ins.size
        self._idx = insns
        self._funcs = sorted(funcs)
        return insns

    def func_list(self):
        self.index()
        return self._funcs

    def owner(self, va):
        """Function containing va, using discovered function starts."""
        fl = self.func_list()
        i = bisect.bisect_right(fl, va) - 1
        return fl[i] if i >= 0 else None

    def find(self, pattern, mnemonic=None):
        """Search the index for instructions whose text matches a regex."""
        import re as _re
        rx = _re.compile(pattern)
        out = []
        for a in sorted(self.index()):
            m, op, sz = self._idx[a]
            if mnemonic and m != mnemonic:
                continue
            if rx.search(f"{m} {op}"):
                out.append((a, f"{m} {op}"))
        return out

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    img = Img()
    cmd = sys.argv[1]

    if cmd == "strings":
        sub = sys.argv[2] if len(sys.argv) > 2 else ""
        for va, s in img.strings():
            if sub.lower() in s.lower():
                print(f"{va:#010x}  {s!r}")

    elif cmd == "xref":
        t = int(sys.argv[2], 0)
        for a, txt in img.imm_xrefs(t):
            fn = img.owner_fn(a)
            print(f"{a:#010x}  {txt:<40} (in fn {fn:#010x})" if fn else
                  f"{a:#010x}  {txt}")

    elif cmd == "dis":
        n = int(sys.argv[3]) if len(sys.argv) > 3 else 40
        for ins in img.dis(int(sys.argv[2], 0), n):
            print(f"{ins.address:#010x}  {ins.mnemonic:<8} {ins.op_str}")

    elif cmd == "fn":
        for ins in img.fn(int(sys.argv[2], 0)):
            print(f"{ins.address:#010x}  {ins.mnemonic:<8} {ins.op_str}")

    elif cmd == "callers":
        for a in img.callers(int(sys.argv[2], 0)):
            fn = img.owner_fn(a)
            print(f"{a:#010x}  (in fn {fn:#010x})" if fn else f"{a:#010x}")

    elif cmd == "find":
        pat = sys.argv[2]
        for a, t in img.find(pat):
            fn = img.owner(a)
            print(f"{a:#010x}  {t:<44} fn={fn:#010x}" if fn else f"{a:#010x}  {t}")

    elif cmd == "index":
        idx = img.index()
        print(f"{len(idx)} instructions, {len(img.func_list())} function starts")

    elif cmd == "vt":
        cls = sys.argv[2]
        for vt in img.vtable_of(cls):
            print(f"\n{cls} vtable {vt:#010x}")
            for slot, fn in img.vtable_entries(vt):
                print(f"  [{(slot-vt)//4:>2}] {fn:#010x}")

    elif cmd == "classes":
        for cls, vts in sorted(img.vtables().items()):
            bare = cls[4:].rstrip("@") if cls.startswith(".?AV") else cls
            if "@" in bare:
                continue
            print(f"{bare:<40} " + " ".join(f"{v:#x}" for v in vts))

    elif cmd == "str2fn":
        sub = sys.argv[2]
        for va, s in img.strings():
            if sub.lower() in s.lower():
                refs = img.imm_xrefs(va)
                if refs:
                    print(f"\n{va:#010x} {s!r}")
                    for a, txt in refs:
                        fn = img.owner_fn(a)
                        print(f"    {a:#010x}  {txt:<36} fn={fn:#010x}"
                              if fn else f"    {a:#010x}  {txt}")
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
