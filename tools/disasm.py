#!/usr/bin/env python3
"""Disassemble UADE player binaries with IRA.

Usage: disasm.py install
       disasm.py seed PLAYER
       disasm.py listing PLAYER

  install  download IRA from Aminet, build it, copy it to .venv/bin/ira
  seed     create data/disasm/PLAYER.cnf; refuses to overwrite it
  listing  write build/disasm/PLAYER.asm from the config

Players are EaglePlayer binaries. Their code is reached only through a tag
list of function pointers, which IRA does not follow. `seed` reads that list,
runs `ira -preproc` once from each code tag, and merges the CODE areas. Every
pointer tag also becomes a LABEL named after the tag, e.g. DTP_Interrupt.

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

HUNK_HEADER = 0x3F3
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


def hunks(data):
    """Return (base address, contents, {offset: target hunk}) per hunk.

    IRA places hunks back to back from address 0, sized by the header.
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
                p += words[p] + 2
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


def seed(player):
    cnf = CONFIGS / f"{player}.cnf"
    if cnf.exists():
        sys.exit(f"{cnf.relative_to(ROOT)} exists; edit it or delete it first")
    found = tags(PLAYERS / player)
    labels, seen = [], set()
    for name, addr in found:
        if addr not in seen:  # one routine may serve several tags
            labels.append((name, addr))
            seen.add(addr)
    entries = sorted({a for n, a in found if n not in DATA_TAGS})
    areas, header = [], []
    with tempfile.TemporaryDirectory() as tmp:
        # IRA names the config after the input minus its extension.
        shutil.copy(PLAYERS / player, Path(tmp) / "p")
        for addr in entries:
            (Path(tmp) / "p.cnf").unlink(missing_ok=True)
            run_ira(tmp, *FLAGS, "-preproc", f"-entry=${addr:x}", "p", "p.asm")
            for line in (Path(tmp) / "p.cnf").read_text().splitlines():
                m = re.fullmatch(r"CODE \$(\w+) - \$(\w+)", line)
                if m:
                    areas.append((int(m.group(1), 16), int(m.group(2), 16)))
                elif line.split()[0] in ("MACHINE", "OFFSET"):
                    header = header if line in header else header + [line]
    lines = header + ["ENTRY $00000000"]
    lines += [f"CODE ${a:08X} - ${b:08X}" for a, b in merge(areas)]
    lines += [f"LABEL {n} ${a:08X}" for n, a in sorted(labels, key=lambda x: x[1])]
    CONFIGS.mkdir(parents=True, exist_ok=True)
    cnf.write_text("\n".join(lines + ["END"]) + "\n")
    print(f"{cnf.relative_to(ROOT)}: {len(entries)} entries, {len(labels)} labels")


def listing(player):
    cnf = CONFIGS / f"{player}.cnf"
    if not cnf.exists():
        sys.exit(f"{cnf.relative_to(ROOT)} missing; run: disasm.py seed {player}")
    LISTINGS.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        shutil.copy(PLAYERS / player, Path(tmp) / "p")
        shutil.copy(cnf, Path(tmp) / "p.cnf")
        run_ira(tmp, *FLAGS, "-config", "p", "p.asm")
        out = LISTINGS / f"{player}.asm"
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
        if not (PLAYERS / argv[1]).is_file():
            sys.exit(f"{argv[1]} is not in ext/uade/players")
        if not IRA.exists():
            sys.exit("IRA missing; run: source ./activate")
        return {"seed": seed, "listing": listing}[argv[0]](argv[1])
    sys.exit(__doc__)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
