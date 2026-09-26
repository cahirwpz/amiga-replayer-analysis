#!/usr/bin/env python3
"""Check that Markdown links and source citations resolve.

Usage: links.py FILE.md|DIR...

Checks:
  - relative Markdown links point to existing files
  - player cards: `source` exists; `related` players are in the inventory
  - player cards: `file:line` citations name an existing line in `source`;
    a bare `:line` refers to the file of the previous citation

Prints `file:line: rule: detail` for each problem; exits 1 if any.
"""

import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "uade" / "amigasrc" / "players"
INVENTORY = ROOT / "data" / "inventory.csv"

LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)\)")
CITE_RE = re.compile(r"`([^`]*?):(\d+)(?:-(\d+))?`")
FENCE_RE = re.compile(r"^\s*(```|~~~)")


def front_matter(lines):
    """Return ({key: raw value}, index of first body line)."""
    if not lines or lines[0].strip() != "---":
        return {}, 0
    meta = {}
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return meta, i + 1
        key, _, value = lines[i].partition(":")
        meta[key.strip()] = value.strip()
    return meta, 0


def source_dir(value):
    """`ext/...` is relative to the repo root; anything else to SOURCES."""
    return ROOT / value if value.startswith("ext/") else SOURCES / value


def players():
    with INVENTORY.open(encoding="utf-8") as f:
        return {row["player"] for row in csv.DictReader(f)}


def line_count(path, cache={}):
    if path not in cache:
        cache[path] = len(path.read_bytes().splitlines())
    return cache[path]


def check(path, known_players):
    rel = path.resolve().relative_to(ROOT).as_posix()
    lines = path.read_text(encoding="utf-8").splitlines()
    errors = []

    def err(n, rule, detail):
        errors.append(f"{rel}:{n}: {rule}: {detail}")

    meta, body = front_matter(lines)
    is_card = rel.startswith("players/") and "source" in meta
    src = source_dir(meta["source"]) if is_card else None
    if is_card and not src.is_dir():
        err(1, "source", f"{meta['source']} does not exist")
        src = None
    if is_card:
        for name in re.findall(r"[\w.+-]+", meta.get("related", "")):
            if name not in known_players:
                err(1, "related", f"{name} not in data/inventory.csv")

    in_code = False
    last_file = None
    for n, line in enumerate(lines[body:], start=body + 1):
        if FENCE_RE.match(line):
            in_code = not in_code
            continue
        if in_code:
            continue
        for target in LINK_RE.findall(line):
            if re.match(r"[a-z]+:", target) or target.startswith("#"):
                continue  # URL or in-page anchor
            target = target.split("#")[0]
            if not (path.parent / target).exists():
                err(n, "link", f"{target} does not exist")
        if not src:
            continue
        for name, first, last in CITE_RE.findall(line):
            if name:
                last_file = src / name
            elif last_file is None:
                err(n, "cite", f":{first} has no preceding file")
                continue
            if not last_file.is_file():
                err(n, "cite", f"{name} not found under {meta['source']}")
                last_file = None
                continue
            count = line_count(last_file)
            for num in filter(None, (first, last)):
                if not 1 <= int(num) <= count:
                    err(n, "cite", f"{last_file.name}:{num} beyond {count} lines")
    return errors


def main(argv):
    known = players()
    errors = []
    for arg in map(Path, argv):
        for path in sorted(arg.rglob("*.md")) if arg.is_dir() else [arg]:
            errors += check(path, known)
    for e in errors:
        print(e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
