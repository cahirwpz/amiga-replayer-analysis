#!/usr/bin/env python3
"""Disassemble UADE player binaries and other 68k hunk files with IRA.

Usage: disasm.py install
       disasm.py seed PLAYER|FILE
       disasm.py listing PLAYER|FILE

  install  build IRA (current Aminet release), vlink and vasm (pinned tags)
           into .venv/bin
  seed     create data/disasm/NAME.cnf; refuses to overwrite it
  listing  write build/disasm/NAME.asm from the config, then check that vasm
           rebuilds the input from it

PLAYER is a binary in ext/uade/players; NAME is the player. FILE is a path
under ext/ to an executable or an object file; NAME is its stem, e.g.
ext/oktalyzer/original/sources/okplay2.o gives okplay2. `listing` takes the
same argument as `seed`.

Players are EaglePlayer binaries. Their code is reached only through a tag
list of function pointers, which IRA does not follow. `seed` reads that list,
runs `ira -preproc` once from each code tag, and merges the CODE areas. Every
pointer tag also becomes a LABEL named after the tag, e.g. DTP_Interrupt.

Object files (HUNK_UNIT) call even their own routines through external
references, which IRA leaves unresolved. So vlink links them first. Other
executables go to IRA as they are. For both, HUNK_SYMBOL names become
LABELs; entries are offset 0 and every symbol in a code hunk.

`seed` drops an entry whose code would run past the end of its hunk: it is
data. It prints each entry and whether it was kept. A data symbol whose
trace stays inside the hunk slips through; delete its CODE range by hand.

The round trip in `listing` proves that the listing rebuilds the input
bytes and relocations. It does not prove the split into code and data.

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
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLAYERS = ROOT / "ext" / "uade" / "players"
INCLUDES = ROOT / "ext" / "uade" / "amigasrc" / "score" / "misc"
CONFIGS = ROOT / "data" / "disasm"
LISTINGS = ROOT / "build" / "disasm"
BIN = ROOT / ".venv" / "bin"
IRA = BIN / "ira"
VLINK = BIN / "vlink"
VASM = BIN / "vasmm68k_mot"
IRA_URL = "https://aminet.net/dev/asm/ira.lha"  # the current release
VLINK_URL = "http://phoenix.owl.de/tags/vlink0_18a.tar.gz"
VASM_URL = "http://phoenix.owl.de/tags/vasm2_0f.tar.gz"

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
    out, cur, code = [], None, False
    while p < len(words):
        kind = words[p] & 0x3FFFFFFF
        p += 1
        if kind in (HUNK_CODE, HUNK_DATA, HUNK_BSS):
            code = kind == HUNK_CODE
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
    out, off = [], start - hs[hunk][0]
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
    if path.parent == PLAYERS:
        found = tags(path)
        return data, found, sorted({a for n, a in found if n not in DATA_TAGS})
    if data[:4] == HUNK_UNIT.to_bytes(4, "big"):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "exe"
            run(VLINK, "-b", "amigahunk", "-o", str(exe), str(path))
            data = exe.read_bytes()
    symbols = []
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
    bounds = [(base, base + len(body)) for base, body, _ in hunks(exe)]
    areas, header, rejected = [], [], []
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
    exe = load(path)[0]
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "p").write_bytes(exe)
        shutil.copy(cnf, Path(tmp) / "p.cnf")
        run(IRA, *FLAGS, "-config", "p", "p.asm", cwd=tmp)
        out = LISTINGS / f"{name}.asm"
        shutil.copy(Path(tmp) / "p.asm", out)
        reassemble(tmp, exe)
    print(f"{out.relative_to(ROOT)}: vasm rebuilds the input")


def make(src, *args):
    proc = subprocess.run(["make", *args], cwd=src, capture_output=True, text=True)
    if proc.returncode:
        sys.exit(f"building {src.name} failed:\n{proc.stdout}{proc.stderr}")


def install_ira():
    import lhafile

    with tempfile.TemporaryDirectory() as tmp:
        with urllib.request.urlopen(IRA_URL) as r:
            archive = lhafile.Lhafile(io.BytesIO(r.read()))
        for info in archive.infolist():
            name = info.filename.replace("\\", "/")
            if name.endswith("/"):
                continue
            path = Path(tmp) / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(archive.read(info.filename))
        src = Path(tmp) / "ira"
        make(src)
        shutil.copy(src / "ira", IRA)
        h = (src / "ira.h").read_text(encoding="latin-1")
        v = [re.search(rf'{k}\s+"(\d+)"', h).group(1) for k in ("VERSION", "REVISION")]
    print(f"installed IRA {'.'.join(v)} as {IRA.relative_to(ROOT)}")


def install_tagged(url, tool, *make_args):
    """Build `tool` from a tagged source archive of Frank Wille's site."""
    with tempfile.TemporaryDirectory() as tmp:
        with urllib.request.urlopen(url) as r:
            with tarfile.open(fileobj=io.BytesIO(r.read()), mode="r:gz") as archive:
                archive.extractall(tmp, filter="data")
        (src,) = Path(tmp).iterdir()  # the archive holds one directory
        (src / "objects").mkdir(exist_ok=True)  # vlink's Makefile needs it
        make(src, *make_args)
        shutil.copy(src / tool.name, tool)
        # vasm -v goes on to assemble stdin into a.out: keep that in tmp.
        proc = subprocess.run(
            [str(tool), "-v"],
            cwd=tmp,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
        )
    version = (proc.stdout + proc.stderr).splitlines()[0].split(" (c)")[0]
    print(f"installed {version} as {tool.relative_to(ROOT)}")


def install():
    BIN.mkdir(parents=True, exist_ok=True)
    install_ira()
    install_tagged(VLINK_URL, VLINK)
    install_tagged(VASM_URL, VASM, "CPU=m68k", "SYNTAX=mot")


def main(argv):
    if argv == ["install"]:
        return install()
    if len(argv) == 2 and argv[0] in ("seed", "listing"):
        if not all(tool.exists() for tool in (IRA, VLINK, VASM)):
            sys.exit("IRA, vlink or vasm missing; run: source ./activate")
        return {"seed": seed, "listing": listing}[argv[0]](argv[1])
    sys.exit(__doc__)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
