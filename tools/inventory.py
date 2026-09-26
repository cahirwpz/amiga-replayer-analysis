#!/usr/bin/env python3
"""List UADE replayers and locate their assembler source.

Usage: inventory.py > data/inventory.csv

One row per binary in ext/uade/players. The source is found by, in order:
  hash     - a byte-identical binary exists inside a source directory
  name     - normalised binary name matches a source file or directory name
  manual   - entry in OVERRIDES
  none     - no source found; searched by name and version string
"""

import csv
import difflib
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UADE = ROOT / "ext" / "uade"
PLAYERS = UADE / "players"
SOURCES = UADE / "amigasrc" / "players"
CONF = UADE / "eagleplayer.conf"

SOURCE_EXT = {".s", ".asm", ".a", ".i"}
# Sources outside UADE, e.g. ports, live under ext/ and may be in C.
EXT_SOURCE_EXT = SOURCE_EXT | {".c", ".h"}
HUNK_HEADER = bytes.fromhex("000003f3")  # AmigaOS executable

# Binary name -> source path relative to SOURCES, when automatic matching fails.
# Paths starting with "ext/" are relative to the repo root instead.
OVERRIDES = {
    "AbyssHighestExperience": "ext/ahx2play",
    "ArtOfNoise-4V": "uade/artofnoise",
    "ArtOfNoise-8V": "uade/artofnoise",
    "FutureComposer1.4": "defect/fc14",
}

# Free-text remarks, e.g. a sibling player with source for the same format.
NOTES = {
    "AbyssHighestExperience": "C port of the AHX 2.3d-sp3 replayer (evidence: port)",
    "TFMX-TFHD": "same format as TFMX (has source)",
    "TFMX-7V-TFHD": "same format as TFMX-7V (has source)",
    "TFMX-Pro-TFHD": "same format as TFMX-Pro (has source)",
}


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


def main():
    by_hash, by_name = index_sources()
    pref = prefixes()
    w = csv.writer(sys.stdout, lineterminator="\n")
    w.writerow(
        ["player", "prefixes", "version", "source", "match", "files", "lines", "note"]
    )
    for b in sorted(PLAYERS.iterdir(), key=lambda p: p.name.lower()):
        if not b.is_file():
            continue
        src, how = locate(b, by_hash, by_name)
        files, lines = stats(Path(src)) if src else (0, 0)
        note = NOTES.get(b.name, "")
        w.writerow(
            [b.name, pref.get(b.name, ""), version(b), src, how, files, lines, note]
        )


if __name__ == "__main__":
    main()
