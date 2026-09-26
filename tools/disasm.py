#!/usr/bin/env python3
"""Disassemble UADE player binaries and other 68k hunk files with IRA.

Usage: disasm.py install
       disasm.py seed PLAYER|FILE
       disasm.py listing PLAYER|FILE

  install  download IRA from Aminet, build it, copy it to .venv/bin/ira
  seed     create data/disasm/NAME.cnf; refuses to overwrite it
  listing  write build/disasm/NAME.asm from the config

PLAYER is a binary in ext/uade/players; NAME is the player. FILE is a path
under ext/ to an executable or an object file; NAME is its stem, e.g.
ext/oktalyzer/original/sources/okplay2.o gives okplay2. `listing` takes the
same argument as `seed`.

Players are EaglePlayer binaries. Their code is reached only through a tag
list of function pointers, which IRA does not follow. `seed` reads that list,
runs `ira -preproc` once from each code tag, and merges the CODE areas. Every
pointer tag also becomes a LABEL named after the tag, e.g. DTP_Interrupt.

Object files (HUNK_UNIT) call even their own routines through external
references, which IRA leaves unresolved. Both commands first link the unit
into an executable: references to its own symbols are patched, 32-bit ones
become relocations. Entries are the symbols that a branch or jump reaches,
and those that nothing in the unit references (the exported API). Every
defined symbol becomes a LABEL. Other executables start at offset 0; their
HUNK_SYMBOL names become labels.

`seed` drops an entry whose code would run past the end of its hunk: it is
data. It prints each entry and whether it was kept.

The config is the committed artefact. Add CODE ranges IRA missed and rename
labels by hand; cards cite them as `data/disasm/PLAYER.cnf:Label`. Listings
are generated, never committed. With a config, `tools/inventory.py` lists
the player as `replay: disasm`. If the
replay code turns out to be in the module, delete the config and set the
player to `replay: module` in data/players.yaml.

Only binary-only players are in scope; `replay: module` players are deferred.
"""

import io
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLAYERS = ROOT / "ext" / "uade" / "players"
INCLUDES = ROOT / "ext" / "uade" / "amigasrc" / "score" / "misc"
CONFIGS = ROOT / "data" / "disasm"
LISTINGS = ROOT / "build" / "disasm"
IRA = ROOT / ".venv" / "bin" / "ira"
URL = "https://aminet.net/dev/asm/ira.lha"

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
HUNK_EXT = 0x3EF
# HUNK_EXT entry types: definitions are below 128, references above.
EXT_REF32, EXT_REF16, EXT_REF8 = 129, 131, 132
# Opcodes of a branch or jump whose target is the reference that follows:
# Bcc.W and BSR.W ($6x00), JMP/JSR (d16,PC), JMP/JSR abs.l.
BRANCH16 = re.compile(rb"[\x60-\x6f]\x00|\x4e[\xba\xfa]", re.S)
BRANCH32 = {b"\x4e\xb9", b"\x4e\xf9"}


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
    Appends (name, address) of each HUNK_SYMBOL entry to `symbols`.
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
    out, cur = [], None
    while p < len(words):
        kind = words[p] & 0x3FFFFFFF
        p += 1
        if kind in (HUNK_CODE, HUNK_DATA):
            n = words[p]
            cur = [bytes(data[4 * (p + 1) : 4 * (p + 1 + n)]), {}]
            out.append(cur)
            p += 1 + n
        elif kind == HUNK_BSS:
            cur = [b"", {}]
            out.append(cur)
            p += 1
        elif kind == HUNK_RELOC32:
            while words[p]:
                n, target = words[p], words[p + 1]
                for off in words[p + 2 : p + 2 + n]:
                    cur[1][off] = target
                p += 2 + n
            p += 1
        elif kind in (HUNK_RELOC32SHORT, HUNK_DREL32):
            rest = data[4 * p : 4 * p + (len(data) - 4 * p) // 2 * 2]
            half = struct.unpack(f">{len(rest) // 2}H", rest)
            q = 0
            while half[q]:
                n, target = half[q], half[q + 1]
                for off in half[q + 2 : q + 2 + n]:
                    cur[1][off] = target
                q += 2 + n
            q += 1
            p += (q + 1) // 2
        elif kind == HUNK_SYMBOL:
            while words[p]:
                n = words[p]
                if symbols is not None:
                    name = data[4 * (p + 1) : 4 * (p + 1 + n)].rstrip(b"\0")
                    symbols.append(
                        (name.decode("latin-1"), bases[len(out) - 1] + words[p + 1 + n])
                    )
                p += n + 2
            p += 1
        elif kind in (HUNK_DEBUG, HUNK_NAME):
            p += words[p] + 1
        elif kind == HUNK_END:
            pass
        else:
            raise ValueError(f"unsupported hunk type ${kind:x}")
    return [(bases[i], c, r) for i, (c, r) in enumerate(out)]


def unit(data):
    """Parse an object file; return its hunks as dicts.

    Keys: type (hunk type word, memory flags kept), size (longwords),
    contents, relocs {offset: target hunk}, defs [(name, offset)],
    refs [(ext type, name, [offsets])], symbols [(name, offset)].
    """
    words = struct.unpack(f">{len(data) // 4}I", data[: len(data) // 4 * 4])
    if words[0] != HUNK_UNIT:
        raise ValueError("not an object file")
    p = 2 + words[1]
    out, cur = [], None

    def name_at(q, n):
        return data[4 * q : 4 * (q + n)].rstrip(b"\0").decode("latin-1")

    while p < len(words):
        kind = words[p] & 0x3FFFFFFF
        if kind in (HUNK_CODE, HUNK_DATA, HUNK_BSS):
            n = words[p + 1] & 0x3FFFFFFF
            body = (
                b"" if kind == HUNK_BSS else bytes(data[4 * (p + 2) : 4 * (p + 2 + n)])
            )
            cur = dict(type=words[p], size=n, contents=body, relocs={})
            cur.update(defs=[], refs=[], symbols=[])
            out.append(cur)
            p += 2 if kind == HUNK_BSS else 2 + n
        elif kind == HUNK_RELOC32:
            p += 1
            while words[p]:
                n, target = words[p], words[p + 1]
                for off in words[p + 2 : p + 2 + n]:
                    cur["relocs"][off] = target
                p += 2 + n
            p += 1
        elif kind == HUNK_EXT:
            p += 1
            while words[p]:
                ext, n = words[p] >> 24, words[p] & 0xFFFFFF
                name = name_at(p + 1, n)
                p += 1 + n
                if ext < 128:
                    if ext == 1:  # EXT_DEF; absolute and resident values are no offsets
                        cur["defs"].append((name, words[p]))
                    p += 1
                else:
                    if ext == 130:  # EXT_COMMON: a size comes first
                        p += 1
                    count = words[p]
                    cur["refs"].append((ext, name, list(words[p + 1 : p + 1 + count])))
                    p += 1 + count
            p += 1
        elif kind == HUNK_SYMBOL:
            p += 1
            while words[p]:
                n = words[p]
                cur["symbols"].append((name_at(p + 1, n), words[p + 1 + n]))
                p += n + 2
            p += 1
        elif kind in (HUNK_DEBUG, HUNK_NAME):
            p += 2 + words[p + 1]
        elif kind == HUNK_END:
            p += 1
        else:
            raise ValueError(f"unsupported hunk type ${kind:x} in object file")
    return out


def link(data):
    """Link an object file into an executable, as IRA would load it.

    Returns (executable bytes, labels [(name, address)], entries {address}).
    References to symbols the unit does not define stay unresolved.
    """
    hs = unit(data)
    bases = [4 * sum(h["size"] for h in hs[:i]) for i in range(len(hs))]
    defs = {name: (i, off) for i, h in enumerate(hs) for name, off in h["defs"]}
    labels = [(name, bases[i] + off) for name, (i, off) in defs.items()]
    labels += [
        (name, bases[i] + off) for i, h in enumerate(hs) for name, off in h["symbols"]
    ]
    referenced, branched = set(), set()
    for i, h in enumerate(hs):
        code = bytearray(h["contents"])
        for ext, name, offsets in h["refs"]:
            if name not in defs:
                continue
            target, value = defs[name]
            referenced.add(name)
            for off in offsets:
                if ext == EXT_REF32:
                    old = int.from_bytes(code[off : off + 4], "big")
                    code[off : off + 4] = ((old + value) & 0xFFFFFFFF).to_bytes(
                        4, "big"
                    )
                    h["relocs"][off] = target
                    if bytes(code[off - 2 : off]) in BRANCH32:
                        branched.add(name)
                elif ext == EXT_REF16 and target == i:
                    old = int.from_bytes(code[off : off + 2], "big", signed=True)
                    code[off : off + 2] = ((old + value - off) & 0xFFFF).to_bytes(
                        2, "big"
                    )
                    if BRANCH16.fullmatch(bytes(code[off - 2 : off])):
                        branched.add(name)
                elif ext == EXT_REF8 and target == i:
                    code[off] = (code[off] + value - off - 1) & 0xFF
                    if 0x60 <= code[off - 1] <= 0x6F:  # Bcc.S or BSR.S
                        branched.add(name)
                else:
                    raise ValueError(f"cannot resolve {name}: EXT type {ext}")
        h["contents"] = bytes(code)
    entries = {
        bases[i] + off
        for name, (i, off) in defs.items()
        if hs[i]["type"] & 0x3FFFFFFF == HUNK_CODE
        and (name in branched or name not in referenced)
    }
    out = [HUNK_HEADER, 0, len(hs), 0, len(hs) - 1]
    out += [h["size"] | (h["type"] & 0xC0000000) for h in hs]
    for h in hs:
        kind = h["type"] & 0x3FFFFFFF
        if kind == HUNK_BSS:
            out += [kind, h["size"]]
        else:
            body = h["contents"].ljust(4 * h["size"], b"\0")
            out += [kind, h["size"], *struct.unpack(f">{h['size']}I", body)]
        by_target = {}
        for off, target in sorted(h["relocs"].items()):
            by_target.setdefault(target, []).append(off)
        if by_target:
            out.append(HUNK_RELOC32)
            for target, offsets in sorted(by_target.items()):
                out += [len(offsets), target, *offsets]
            out.append(0)
        out.append(HUNK_END)
    return struct.pack(f">{len(out)}I", *out), labels, entries


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
    out, off = [], start - hs[hunk][0]
    while True:
        tag, _ = struct.unpack(">II", hs[hunk][1][off : off + 8])
        if tag == 0:  # TAG_DONE
            return out
        addr = pointer(hs, hunk, off + 4)
        if tag in names and addr is not None:
            out.append((names[tag], addr))
        off += 8


def run_ira(workdir, *args):
    proc = subprocess.run(
        [str(IRA), *args], cwd=workdir, capture_output=True, text=True
    )
    if proc.returncode:
        sys.exit(f"ira {' '.join(args)} failed:\n{proc.stdout}{proc.stderr}")


def merge(areas):
    out = []
    for a, b in sorted(areas):
        if b <= a:
            continue
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def resolve(arg):
    """(config name, input path) for a player name or a file under ext/."""
    if "/" not in arg and (PLAYERS / arg).is_file():
        return arg, PLAYERS / arg
    path = (ROOT / arg).resolve()
    if not path.is_file() or not path.is_relative_to(ROOT / "ext"):
        sys.exit(f"{arg} is neither a player in ext/uade/players nor a file under ext/")
    if (PLAYERS / path.stem).is_file() and path != PLAYERS / path.stem:
        sys.exit(f"{path.stem} is also a player; its config name would clash")
    return path.stem, path


def load(path):
    """(executable bytes, labels [(name, address)], entry addresses)."""
    data = path.read_bytes()
    if data[:4] == HUNK_UNIT.to_bytes(4, "big"):
        exe, labels, entries = link(data)
        return exe, labels, sorted(entries)
    if path.parent == PLAYERS:
        found = tags(path)
        entries = {a for n, a in found if n not in DATA_TAGS}
        return data, found, sorted(entries)
    symbols = []
    hunks(data, symbols)
    return data, symbols, [0]


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
    bounds = [(base, base + len(body)) for base, body, _ in hunks(exe)]
    areas, header, rejected = [], [], []
    with tempfile.TemporaryDirectory() as tmp:
        # IRA names the config after the input minus its extension.
        (Path(tmp) / "p").write_bytes(exe)
        for addr in entries:
            (Path(tmp) / "p.cnf").unlink(missing_ok=True)
            run_ira(tmp, *FLAGS, "-preproc", f"-entry=${addr:x}", "p", "p.asm")
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


def listing(arg):
    name, path = resolve(arg)
    cnf = CONFIGS / f"{name}.cnf"
    if not cnf.exists():
        sys.exit(f"{cnf.relative_to(ROOT)} missing; run: disasm.py seed {arg}")
    LISTINGS.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "p").write_bytes(load(path)[0])
        shutil.copy(cnf, Path(tmp) / "p.cnf")
        run_ira(tmp, *FLAGS, "-config", "p", "p.asm")
        out = LISTINGS / f"{name}.asm"
        shutil.copy(Path(tmp) / "p.asm", out)
    print(out.relative_to(ROOT))


def install():
    import lhafile

    with tempfile.TemporaryDirectory() as tmp:
        with urllib.request.urlopen(URL) as r:
            archive = lhafile.Lhafile(io.BytesIO(r.read()))
        for info in archive.infolist():
            name = info.filename.replace("\\", "/")
            if name.endswith("/"):
                continue
            path = Path(tmp) / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(archive.read(info.filename))
        src = Path(tmp) / "ira"
        proc = subprocess.run(["make"], cwd=src, capture_output=True, text=True)
        if proc.returncode:
            sys.exit(f"building IRA failed:\n{proc.stdout}{proc.stderr}")
        IRA.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src / "ira", IRA)
        h = (src / "ira.h").read_text(encoding="latin-1")
        v = [re.search(rf'{k}\s+"(\d+)"', h).group(1) for k in ("VERSION", "REVISION")]
    print(f"installed IRA {'.'.join(v)} as {IRA.relative_to(ROOT)}")


def main(argv):
    if argv == ["install"]:
        return install()
    if len(argv) == 2 and argv[0] in ("seed", "listing"):
        if not IRA.exists():
            sys.exit("IRA missing; run: source ./activate")
        return {"seed": seed, "listing": listing}[argv[0]](argv[1])
    sys.exit(__doc__)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
