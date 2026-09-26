#!/usr/bin/env python3
"""List UADE replayers and locate their assembler source.

Usage: inventory.py [--write | --check]

  (no option)  print the CSV to stdout
  --write      write data/inventory.csv and the counts block of docs/inventory.md
  --check      exit 1 if either file is out of date

One row per binary in ext/uade/players. The source is found by, in order:
  hash     - a byte-identical binary exists inside a source directory
  name     - normalised binary name matches a source file or directory name
  manual   - `source` in data/players.yaml
  none     - no source found; searched by name and version string

The `replay` column says where the replay logic is:
  uade     - in the UADE source (original or disassembled)
  module   - in the music file; the UADE source only patches it
  check    - patch markers found, but not clearly a wrapper; read the source
  port     - a port outside UADE, under ext/
  disasm   - no source; data/disasm/<player>.cnf drives an IRA disassembly
"""

import csv
import difflib
import hashlib
import io
import re
import sys
from pathlib import Path

import players
from mdtools import format_table

ROOT = Path(__file__).resolve().parent.parent
UADE = ROOT / "ext" / "uade"
PLAYERS = UADE / "players"
SOURCES = UADE / "amigasrc" / "players"
CONF = UADE / "eagleplayer.conf"

SOURCE_EXT = {".s", ".asm", ".a", ".i"}
# Sources outside UADE, e.g. ports, live under ext/ and may be in C.
EXT_SOURCE_EXT = SOURCE_EXT | {".c", ".h"}
HUNK_HEADER = bytes.fromhex("000003f3")  # AmigaOS executable

DISASM = ROOT / "data" / "disasm"
CSV = ROOT / "data" / "inventory.csv"
DOC = ROOT / "docs" / "inventory.md"
BEGIN, END = "<!-- counts:begin -->", "<!-- counts:end -->"

# Wrappers find code inside the module and patch it.
PATCH_RE = re.compile(r"PatchTable|FindIt\d|^Patch\d", re.M)
ROUTINE_RE = re.compile(r"^lbC", re.M)  # disassembler routine labels

# Hand-written overrides and notes: data/players.yaml (`source`, `replay`, `note`).
FACTS = players.load()
REPLAY = {p: f["replay"] for p, f in FACTS.items() if "replay" in f}
OVERRIDES = {p: f["source"] for p, f in FACTS.items() if "source" in f}
NOTES = {p: f["note"] for p, f in FACTS.items() if "note" in f}


def norm(name):
    return re.sub(r"[^a-z0-9]", "", name.lower())


def digest(path):
    return hashlib.sha1(path.read_bytes()).hexdigest()


def version(path):
    m = re.search(rb"\$VER:\s*([\x20-\x7e]+)", path.read_bytes())
    return m.group(1).decode("ascii").strip() if m else ""


def prefixes():
    out = {}
    for line in CONF.read_text(encoding="latin-1").splitlines():
        parts = line.split()
        if not parts or line.startswith("#"):
            continue
        for p in parts[1:]:
            if p.startswith("prefixes="):
                out[parts[0]] = p[len("prefixes=") :]
    return out


def source_unit(path):
    """Smallest directory that holds a player's own sources."""
    rel = path.relative_to(SOURCES)
    # Group directory + player directory, e.g. wanted_team/DaveLowe.
    return Path(*rel.parts[:2]) if len(rel.parts) > 2 else rel.parent


def index_sources():
    by_hash, by_name = {}, {}
    for f in SOURCES.rglob("*"):
        if not f.is_file():
            continue
        unit = source_unit(f)
        if f.suffix.lower() in SOURCE_EXT:
            by_name.setdefault(norm(f.stem), set()).add(unit)
        elif f.read_bytes()[:4] == HUNK_HEADER:
            by_hash.setdefault(digest(f), set()).add(unit)
    for d in SOURCES.rglob("*"):
        if d.is_dir():
            by_name.setdefault(norm(d.name), set()).add(source_unit(d / "x"))
    return by_hash, by_name


def stats(unit):
    if unit.parts[0] == "ext":
        base, exts = ROOT / unit, EXT_SOURCE_EXT
    else:
        base, exts = SOURCES / unit, SOURCE_EXT
    files = [
        f
        for f in base.rglob("*")
        if f.is_file() and f.suffix.lower() in exts and ".git" not in f.parts
    ]
    lines = sum(len(f.read_bytes().splitlines()) for f in files)
    return len(files), lines


def replay(player, unit):
    if player in REPLAY:
        return REPLAY[player]
    if unit.parts[0] == "ext":
        return "port"
    text = "".join(
        f.read_bytes().decode("latin-1")
        for f in (SOURCES / unit).rglob("*")
        if f.is_file() and f.suffix.lower() in SOURCE_EXT and "AMP" not in f.name
    )
    patches = len(PATCH_RE.findall(text))
    if patches >= 5 and len(ROUTINE_RE.findall(text)) < 20:
        return "module"
    return "check" if patches else "uade"


def closest(name, units):
    """Some source directories carry copies of other players' binaries."""
    return max(
        sorted(units),
        key=lambda u: difflib.SequenceMatcher(None, norm(name), norm(u.name)).ratio(),
    )


def locate(binary, by_hash, by_name):
    if binary.name in OVERRIDES:
        return OVERRIDES[binary.name], "manual"
    units = by_hash.get(digest(binary))
    if units:
        return closest(binary.name, units).as_posix(), "hash"
    key = norm(binary.name)
    units = by_name.get(key)
    if units:
        return closest(binary.name, units).as_posix(), "name"
    return "", "none"


def rows():
    by_hash, by_name = index_sources()
    pref = prefixes()
    out = [
        [
            "player",
            "version",
            "source",
            "match",
            "replay",
            "files",
            "lines",
            "note",
            "prefixes",  # last: very long for some players
        ]
    ]
    for b in sorted(PLAYERS.iterdir(), key=lambda p: p.name.lower()):
        if not b.is_file():
            continue
        src, how = locate(b, by_hash, by_name)
        files, lines = stats(Path(src)) if src else (0, 0)
        where = replay(b.name, Path(src)) if files else REPLAY.get(b.name, "")
        cnf = DISASM / f"{b.name}.cnf"
        if not files and not where and cnf.exists():
            src, where = cnf.relative_to(ROOT).as_posix(), "disasm"
        note = NOTES.get(b.name, "")
        out.append(
            [
                b.name,
                version(b),
                src,
                how,
                where,
                files,
                lines,
                note,
                pref.get(b.name, ""),
            ]
        )
    return out


def to_csv(table):
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(table)
    return buf.getvalue()


def counts(table):
    """Markdown block with the numbers quoted in docs/inventory.md."""
    col = {name: i for i, name in enumerate(table[0])}
    body = table[1:]
    with_src = [r for r in body if int(r[col["files"]]) > 0]
    units = {r[col["source"]] for r in with_src}

    def tally(name, values):
        return [(v, sum(1 for r in body if r[col[name]] == v)) for v in values]

    groups = [
        ["Binaries in UADE", str(len(body))],
        ["With source", str(len(with_src))],
        ["Binary only", str(len(body) - len(with_src))],
    ]
    found = [[v, str(n)] for v, n in tally("match", ["hash", "name", "manual", "none"])]
    replay = [
        [v, str(n)]
        for v, n in tally("replay", ["uade", "module", "check", "port", "disasm"])
    ]
    lines = [BEGIN, ""]
    lines += format_table(["Group", "Players"], groups)
    lines += ["", f"{len(with_src)} players map to {len(units)} source directories."]
    lines += [""] + format_table(["How source was found", "Players"], found)
    lines += [""] + format_table(["Where replay logic is", "Players"], replay)
    lines += ["", END]
    return "\n".join(lines)


def doc_with(block):
    doc = DOC.read_text(encoding="utf-8")
    a, b = doc.index(BEGIN), doc.index(END) + len(END)
    return doc[:a] + block + doc[b:], doc[a:b]


def main(argv):
    table = rows()
    text = to_csv(table)
    block = counts(table)
    if not argv:
        sys.stdout.write(text)
        return 0
    if argv == ["--write"]:
        CSV.write_text(text, encoding="utf-8")
        DOC.write_text(doc_with(block)[0], encoding="utf-8")
        return 0
    if argv == ["--check"]:
        stale = []
        if CSV.read_text(encoding="utf-8") != text:
            stale.append(str(CSV.relative_to(ROOT)))
        if doc_with(block)[1] != block:
            stale.append(str(DOC.relative_to(ROOT)))
        for path in stale:
            print(f"{path}: out of date; run tools/inventory.py --write")
        return 1 if stale else 0
    sys.exit(__doc__)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
