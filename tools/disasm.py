#!/usr/bin/env python3
"""Disassemble UADE player binaries and other 68k hunk files with IRA.

Usage: disasm.py seed PLAYER|FILE
       disasm.py listing PLAYER|FILE
       disasm.py trace PLAYER|FILE ADDR|START-END...

  seed     create data/disasm/NAME.cnf; refuses to overwrite it
  listing  write build/disasm/NAME.asm from the config, then check that vasm
           rebuilds the input from it
  trace    add to the config the code IRA finds from each ADDR, or from each
           long pointer in the table START-END; for code reached through
           tables that IRA does not follow. Hex, with or without `$`.

PLAYER is a binary in ext/uade/players; NAME is the player. FILE is a path
under ext/ to an executable or an object file; NAME is its stem, e.g.
ext/oktalyzer/original/sources/okplay2.o gives okplay2. `listing` takes the
same argument as `seed`.

A player whose replay ships inside the module has `module` in
data/players.yaml. PLAYER then reads that module, NAME is still the player.
The module must be in data/modules.yaml with its sha1; Git LFS stores it.

Players are EaglePlayer binaries. Their code is reached only through a tag
list of function pointers, which IRA does not follow. `seed` reads that list,
runs `ira -preproc` once from each code tag, and merges the CODE areas. Every
pointer tag also becomes a LABEL named after the tag, e.g. DTP_Interrupt.

Object files (HUNK_UNIT) call even their own routines through external
references, which IRA leaves unresolved. So vlink links them first. Other
executables go to IRA as they are. For both, HUNK_SYMBOL names become
LABELs; entries are offset 0 and every symbol in a code hunk.

Raw code, e.g. a module, has no hunk header. vasm wraps it into one code
hunk at address 0, so offsets are file offsets. Entries are offset 0 and
the targets of a leading table of `bra.w` or `jmp (d16,pc)`, labelled
Jump0, Jump1 and on. Without one, a leading row of short stubs that call a
routine with `bsr.w` and end in `rts` gives the entries, labelled Stub0,
Stub1 and on.

`seed` drops an entry whose code would run past the end of its hunk: it is
data. It prints each entry and whether it was kept. A data symbol whose
trace stays inside the hunk slips through; delete its CODE range by hand.

The round trip in `listing` proves that the listing rebuilds the input
bytes and relocations. It does not prove the split into code and data.

The config is the committed artefact. Add CODE ranges IRA missed and rename
labels by hand; cards cite them as `data/disasm/PLAYER.cnf:Label`. Listings
are generated, never committed. With a config, `tools/inventory.py` lists
a player without source as `replay: disasm`.
"""

import hashlib
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

import cli
import players

ROOT = Path(__file__).resolve().parent.parent
PLAYERS = ROOT / "ext" / "uade" / "players"
INCLUDES = ROOT / "ext" / "uade" / "amigasrc" / "score" / "misc"
CONFIGS = ROOT / "data" / "disasm"
LISTINGS = ROOT / "build" / "disasm"
BIN = ROOT / ".venv" / "bin"
IRA = BIN / "ira"
VLINK = BIN / "vlink"
VASM = BIN / "vasmm68k_mot"

# -a: address and data in comments; -label=1: labels named by address.
FLAGS = ["-a", "-label=1"]
TAG_LIST_PTR = 12  # after `moveq #-1,d0; rts` and "DELIRIUM" or "EPPLAYER"

# Tags whose data is a value, string or structure, not a routine.
DATA_TAGS = {
    "DTP_InternalPlayer",
    "DTP_CustomPlayer",
    "DTP_RequestDTVersion",
    "DTP_RequestKickVersion",
    "DTP_PlayerVersion",
    "DTP_PlayerName",
    "DTP_Creator",
    "DTP_DeliBase",
    "DTP_Flags",
    "DTP_CheckLen",
    "DTP_Description",
    "DTP_NotePlayer",
    "DTP_NoteStruct",
    "DTP_NoteInfo",
    "DTP_Priority",
    "DTP_StackSize",
    "DTP_MsgPort",
    "DTP_ModuleName",
    "DTP_NewSubSongRange",
    "DTP_FormatName",
    "DTP_AuthorName",
    "EP_Flags",
    "EP_KickVersion",
    "EP_PlayerVersion",
    "EP_Date",
    "EP_NewModuleInfo",
    "EP_CreatorLNr",
    "EP_PlayerNameLNr",
    "EP_PlayerInfo",
    "EP_LocaleTable",
    "EP_Helpnodename",
    "EP_AttnFlags",
    "EP_EagleBase",
}

HUNK_HEADER, HUNK_UNIT = 0x3F3, 0x3E7
HUNK_CODE, HUNK_DATA, HUNK_BSS = 0x3E9, 0x3EA, 0x3EB
HUNK_RELOC32, HUNK_RELOC32SHORT, HUNK_DREL32 = 0x3EC, 0x3FC, 0x3F7
HUNK_SYMBOL, HUNK_DEBUG, HUNK_END, HUNK_NAME = 0x3F0, 0x3F1, 0x3F2, 0x3E8
# Jump table entries: a 16-bit displacement from the second word follows.
JUMPS = (b"\x60\x00", b"\x4e\xfa")  # bra.w, jmp (d16,pc)
BSR_W, RTS = b"\x61\x00", b"\x4e\x75"
STUB_MAX = 16  # bytes in an entry stub, e.g. movem.l, bsr.w, movem.l, rts
LFS_POINTER = b"version https://git-lfs"


def tag_names():
    """Tag value -> name, from the ENUM/EITEM lists of the UADE includes."""
    names = {}
    for inc, prefix, base in (
        ("DeliPlayer.i", "DTP_", b"DT"),
        ("EaglePlayer.i", "EP_", b"EP"),
    ):
        value = None
        for line in (INCLUDES / inc).read_text(encoding="latin-1").splitlines():
            m = re.match(r"\s+(ENUM|EITEM)\s+(\w+)", line)
            if not m:
                continue
            if m.group(1) == "ENUM":
                value = 0x80000000 + int.from_bytes(base, "big")
                if not m.group(2).startswith(prefix):
                    value = None
            elif value is not None:
                names[value] = m.group(2)
                value += 1
    return names


def hunks(data, symbols=None):
    """Return (base address, contents, {offset: target hunk}) per hunk.

    IRA places hunks back to back from address 0, sized by the header.
    Appends (name, address, in a code hunk) of each HUNK_SYMBOL entry to
    `symbols`.
    """
    words = struct.unpack(f">{len(data) // 4}I", data[: len(data) // 4 * 4])
    if words[0] != HUNK_HEADER:
        raise ValueError("not an AmigaOS executable")
    p = 1
    while words[p]:  # resident library names
        p += words[p] + 1
    first, last = words[p + 2], words[p + 3]
    sizes = [w & 0x3FFFFFFF for w in words[p + 4 : p + 5 + last - first]]
    p += 5 + last - first
    bases = [4 * sum(sizes[:i]) for i in range(len(sizes))]
    out: list[tuple[bytes, dict[int, int]]] = []
    relocs: dict[int, int] = {}
    code = False
    while p < len(words):
        kind = words[p] & 0x3FFFFFFF
        p += 1
        if kind in (HUNK_CODE, HUNK_DATA, HUNK_BSS):
            code = kind == HUNK_CODE
        if kind in (HUNK_CODE, HUNK_DATA):
            n = words[p]
            relocs = {}
            out.append((bytes(data[4 * (p + 1) : 4 * (p + 1 + n)]), relocs))
            p += 1 + n
        elif kind == HUNK_BSS:
            relocs = {}
            out.append((b"", relocs))
            p += 1
        elif kind == HUNK_RELOC32:
            while words[p]:
                n, target = words[p], words[p + 1]
                for off in words[p + 2 : p + 2 + n]:
                    relocs[off] = target
                p += 2 + n
            p += 1
        elif kind in (HUNK_RELOC32SHORT, HUNK_DREL32):
            rest = data[4 * p : 4 * p + (len(data) - 4 * p) // 2 * 2]
            half = struct.unpack(f">{len(rest) // 2}H", rest)
            q = 0
            while half[q]:
                n, target = half[q], half[q + 1]
                for off in half[q + 2 : q + 2 + n]:
                    relocs[off] = target
                q += 2 + n
            q += 1
            p += (q + 1) // 2
        elif kind == HUNK_SYMBOL:
            while words[p]:
                n = words[p]
                if symbols is not None:
                    name = data[4 * (p + 1) : 4 * (p + 1 + n)].rstrip(b"\0")
                    addr = bases[len(out) - 1] + words[p + 1 + n]
                    symbols.append((name.decode("latin-1"), addr, code))
                p += n + 2
            p += 1
        elif kind in (HUNK_DEBUG, HUNK_NAME):
            p += words[p] + 1
        elif kind == HUNK_END:
            pass
        else:
            raise ValueError(f"unsupported hunk type ${kind:x}")
    return [(bases[i], c, r) for i, (c, r) in enumerate(out)]


def pointer(hs, hunk, off):
    """Address a relocated longword points to, or None if not relocated."""
    _, contents, relocs = hs[hunk]
    if off not in relocs:
        return None
    (value,) = struct.unpack(">I", contents[off : off + 4])
    return hs[relocs[off]][0] + value


def tags(binary):
    """[(tag name, address)] for every pointer in the player's tag list."""
    hs = hunks(binary.read_bytes())
    start = pointer(hs, 0, TAG_LIST_PTR)
    if start is None:
        raise ValueError("no tag list pointer at offset 12")
    hunk = max(i for i, h in enumerate(hs) if h[0] <= start)
    names = tag_names()
    out: list[tuple[str, int]] = []
    off = start - hs[hunk][0]
    while True:
        tag, _ = struct.unpack(">II", hs[hunk][1][off : off + 8])
        if tag == 0:  # TAG_DONE
            return out
        addr = pointer(hs, hunk, off + 4)
        if tag in names and addr is not None:
            out.append((names[tag], addr))
        off += 8


def run(tool, *args, cwd=None):
    """Run one of our tools; exit with its output if it fails."""
    proc = subprocess.run([str(tool), *args], cwd=cwd, capture_output=True, text=True)
    if proc.returncode:
        sys.exit(f"{tool.name} {' '.join(args)} failed:\n{proc.stdout}{proc.stderr}")


def merge(areas):
    out: list[list[int]] = []
    for a, b in sorted(areas):
        if b <= a:
            continue
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def module_file(path):
    """Exit unless the module is fetched and matches data/modules.yaml."""
    rel = path.relative_to(ROOT).as_posix()
    data = path.read_bytes()
    if data.startswith(LFS_POINTER):
        sys.exit(f"{rel} is a Git LFS pointer; run: git lfs pull")
    want = players.modules()[rel]["sha1"]
    if hashlib.sha1(data).hexdigest() != want:
        sys.exit(f"{rel}: sha1 differs from data/modules.yaml")
    return path


def resolve(arg):
    """(config name, input path) for a player name or a file under ext/."""
    if "/" not in arg and (PLAYERS / arg).is_file():
        module = players.load().get(arg, {}).get("module")
        return arg, module_file(ROOT / module) if module else PLAYERS / arg
    path = (ROOT / arg).resolve()
    if not path.is_file() or not path.is_relative_to(ROOT / "ext"):
        sys.exit(f"{arg} is neither a player in ext/uade/players nor a file under ext/")
    if (PLAYERS / path.stem).is_file() and path != PLAYERS / path.stem:
        sys.exit(f"{path.stem} is also a player; its config name would clash")
    return path.stem, path


def jump_table(raw):
    """Targets of the jump table at the start of raw code."""
    out, off = [], 0
    while raw[off : off + 2] in JUMPS:
        (disp,) = struct.unpack(">h", raw[off + 2 : off + 4])
        out.append(off + 2 + disp)
        off += 4
    return out


def stubs(raw):
    """Starts of the entry stubs at the start of raw code: each calls a
    routine with `bsr.w` and ends in `rts`. One stub alone is no table."""
    out, off = [], 0
    while True:
        words = [raw[p : p + 2] for p in range(off, off + STUB_MAX, 2)]
        if RTS not in words or BSR_W not in words[: words.index(RTS)]:
            break
        out.append(off)
        off += 2 * words.index(RTS) + 2
    return out if len(out) > 1 else []


def wrap(path):
    """Raw code as an executable with one code hunk at address 0."""
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "w.s").write_text(f'\tsection code,code\n\tincbin "{path}"\n')
        run(VASM, "-Fhunkexe", "-no-opt", "-quiet", "-o", "exe", "w.s", cwd=tmp)
        return (Path(tmp) / "exe").read_bytes()


def load(path):
    """(executable bytes, labels [(name, address)], entry addresses)."""
    data = path.read_bytes()
    if data[:4] not in (HUNK_HEADER.to_bytes(4, "big"), HUNK_UNIT.to_bytes(4, "big")):
        targets = jump_table(data)
        labels = [(f"Jump{n}", addr) for n, addr in enumerate(targets)]
        if not targets:
            targets = stubs(data)
            labels = [(f"Stub{n}", addr) for n, addr in enumerate(targets)]
        return wrap(path.resolve()), labels, sorted({0, *targets})
    if path.parent == PLAYERS:
        found = tags(path)
        return data, found, sorted({a for n, a in found if n not in DATA_TAGS})
    if data[:4] == HUNK_UNIT.to_bytes(4, "big"):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "exe"
            run(VLINK, "-b", "amigahunk", "-o", str(exe), str(path))
            data = exe.read_bytes()
    symbols: list[tuple[str, int, bool]] = []
    hunks(data, symbols)
    labels = [(name, addr) for name, addr, _ in symbols]
    return data, labels, sorted({0} | {addr for _, addr, code in symbols if code})


def reassemble(tmp, exe):
    """Exit unless vasm turns the listing tmp/p.asm back into `exe`."""
    run(VASM, "-Fhunkexe", "-no-opt", "-quiet", "-o", "re", "p.asm", cwd=tmp)
    theirs, ours = hunks(exe), hunks((Path(tmp) / "re").read_bytes())
    if [h[0] for h in theirs] != [h[0] for h in ours]:
        sys.exit("round trip: the hunks differ in number or size")
    for i, ((_, a, ra), (_, b, rb)) in enumerate(zip(theirs, ours)):
        a, b = a.rstrip(b"\0"), b.rstrip(b"\0")  # trailing zeros may be implied
        if a != b:
            off = next((k for k, (x, y) in enumerate(zip(a, b)) if x != y), None)
            off = min(len(a), len(b)) if off is None else off
            sys.exit(f"round trip: hunk {i} differs at ${off:x}")
        if ra != rb:
            sys.exit(f"round trip: hunk {i} has other relocations")


def seed(arg):
    name, path = resolve(arg)
    cnf = CONFIGS / f"{name}.cnf"
    if cnf.exists():
        sys.exit(f"{cnf.relative_to(ROOT)} exists; edit it or delete it first")
    exe, found, entries = load(path)
    labels, seen = [], set()
    for label, addr in found:
        if addr not in seen:  # one routine may serve several tags
            labels.append((label, addr))
            seen.add(addr)
    areas, header, rejected = traced(exe, entries)
    lines = header + ["ENTRY $00000000"]
    lines += [f"CODE ${a:08X} - ${b:08X}" for a, b in merge(areas)]
    lines += [f"LABEL {n} ${a:08X}" for n, a in sorted(labels, key=lambda x: x[1])]
    CONFIGS.mkdir(parents=True, exist_ok=True)
    cnf.write_text("\n".join(lines + ["END"]) + "\n")
    print(
        f"{cnf.relative_to(ROOT)}: {len(entries) - len(rejected)} entries, {len(labels)} labels"
    )
    names = dict((addr, label) for label, addr in reversed(labels))
    for addr in entries:
        verdict = "rejected: runs past its hunk" if addr in rejected else "entry"
        print(f"  ${addr:08X} {names.get(addr, '')}: {verdict}")


def traced(exe, entries):
    """(CODE areas, config header, rejected entries) that `ira -preproc`
    finds from each entry of the executable."""
    bounds = [(base, base + len(body)) for base, body, _ in hunks(exe)]
    areas: list[tuple[int, int]] = []
    header: list[str] = []
    rejected: list[int] = []
    with tempfile.TemporaryDirectory() as tmp:
        # IRA names the config after the input minus its extension.
        (Path(tmp) / "p").write_bytes(exe)
        for addr in entries:
            (Path(tmp) / "p.cnf").unlink(missing_ok=True)
            run(IRA, *FLAGS, "-preproc", f"-entry=${addr:x}", "p", "p.asm", cwd=tmp)
            found = []
            for line in (Path(tmp) / "p.cnf").read_text().splitlines():
                m = re.fullmatch(r"CODE \$(\w+) - \$(\w+)", line)
                if m:
                    found.append((int(m.group(1), 16), int(m.group(2), 16)))
                elif line.split()[0] in ("MACHINE", "OFFSET"):
                    header = header if line in header else header + [line]
            # Code never runs past its hunk's contents; such an entry is data.
            # IRA also reports an empty area at each hunk start.
            inside = [
                any(lo <= a and b <= hi for lo, hi in bounds) for a, b in found if b > a
            ]
            if all(inside):
                areas += found
            else:
                rejected.append(addr)
    return areas, header, rejected


CODE_LINE = re.compile(r"CODE \$(\w+) - \$(\w+)")


def pointers(exe, start, end):
    """The long pointers in [start, end) of the executable's hunks."""
    for base, body, _ in hunks(exe):
        if base <= start and end <= base + len(body):
            data = body[start - base : end - base]
            return [
                int.from_bytes(data[i : i + 4], "big") for i in range(0, len(data), 4)
            ]
    sys.exit(f"${start:X}-${end:X} is not inside one hunk")


def trace(arg, specs):
    name, path = resolve(arg)
    cnf = CONFIGS / f"{name}.cnf"
    if not cnf.exists():
        sys.exit(f"{cnf.relative_to(ROOT)} missing; run: disasm.py seed {arg}")
    exe = load(path)[0]
    entries = []
    for spec in specs:
        lo, _, hi = spec.replace("$", "").partition("-")
        if hi:
            entries += pointers(exe, int(lo, 16), int(hi, 16))
        else:
            entries.append(int(lo, 16))
    entries = sorted(set(entries))
    areas, _, rejected = traced(exe, entries)
    lines = cnf.read_text().splitlines()
    old = [
        (int(m[1], 16), int(m[2], 16)) for x in lines if (m := CODE_LINE.fullmatch(x))
    ]
    first = next(i for i, x in enumerate(lines) if CODE_LINE.fullmatch(x))
    rest = [x for x in lines if not CODE_LINE.fullmatch(x)]
    code = [f"CODE ${a:08X} - ${b:08X}" for a, b in merge(old + areas)]
    cnf.write_text("\n".join(rest[:first] + code + rest[first:]) + "\n")
    added = sum(b - a for a, b in merge(old + areas)) - sum(
        b - a for a, b in merge(old)
    )
    print(f"{cnf.relative_to(ROOT)}: {len(entries)} entries, {added} bytes of new code")
    for addr in rejected:
        print(f"  ${addr:08X}: rejected: runs past its hunk")


def listing(arg):
    name, path = resolve(arg)
    cnf = CONFIGS / f"{name}.cnf"
    if not cnf.exists():
        sys.exit(f"{cnf.relative_to(ROOT)} missing; run: disasm.py seed {arg}")
    LISTINGS.mkdir(parents=True, exist_ok=True)
    exe = load(path)[0]
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "p").write_bytes(exe)
        shutil.copy(cnf, Path(tmp) / "p.cnf")
        run(IRA, *FLAGS, "-config", "p", "p.asm", cwd=tmp)
        out = LISTINGS / f"{name}.asm"
        shutil.copy(Path(tmp) / "p.asm", out)
        reassemble(tmp, exe)
    print(f"{out.relative_to(ROOT)}: vasm rebuilds the input")


def main(argv):
    parser = cli.parser(__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("seed", "listing", "trace"):
        command = commands.add_parser(name, description=__doc__)
        command.add_argument("target", metavar="PLAYER|FILE")
    commands.choices["trace"].add_argument("addrs", nargs="+", metavar="ADDR")
    args = parser.parse_args(argv)
    if not all(tool.exists() for tool in (IRA, VLINK, VASM)):
        sys.exit("IRA, vlink or vasm missing; run: source ./activate")
    if args.command == "trace":
        return trace(args.target, args.addrs)
    return {"seed": seed, "listing": listing}[args.command](args.target)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
