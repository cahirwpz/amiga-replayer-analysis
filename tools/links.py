#!/usr/bin/env python3
"""Check that Markdown links and source citations resolve.

Usage: links.py [--fix-rows] FILE.md|DIR...

  --fix-rows  rewrite `#L<n>` of titled links to the row that starts with the
              title; run after data/inventory.csv changes

Checks:
  - relative Markdown links point to existing files
  - `#L<n>` links name an existing line; a link title must start that line,
    e.g. [Future Composer](data/inventory.csv?plain=1#L60 "FutureComposer1.3")
  - player cards (front matter has `player`): `source` exists; `related` players are in the inventory
  - player cards: `file:line` citations name an existing line in `source`;
    a bare `:line` refers to the file of the previous citation
  - `path.cnf:Label` citations name a LABEL or SYMBOL in an IRA config;
    the path is relative to the repo root, e.g. data/disasm/X.cnf:Play

Prints `file:line: rule: detail` for each problem; exits 1 if any.
"""

import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "ext" / "uade" / "amigasrc" / "players"
INVENTORY = ROOT / "data" / "inventory.csv"

# [text](target "title"); the title is optional.
LINK_RE = re.compile(r'(?<!!)\[[^\]]*\]\(([^)\s]+)(?:\s+"([^"]*)")?\)')
CITE_RE = re.compile(r"`([^`]*?):(\d+)(?:-(\d+))?`")
LABEL_CITE_RE = re.compile(r"`([\w./+-]+\.cnf):([A-Za-z_]\w*)`")
FENCE_RE = re.compile(r"^\s*(```|~~~)")


def front_matter(lines):
    """Return ({key: raw value}, index of first body line)."""
    if not lines or lines[0].strip() != "---":
        return {}, 0
    meta = {}
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return meta, i + 1
        if lines[i][:1].isspace() and meta:
            # Continuation, e.g. a list that prettier wrapped.
            last = next(reversed(meta))
            meta[last] = f"{meta[last]} {lines[i].strip()}".strip()
            continue
        key, _, value = lines[i].partition(":")
        meta[key.strip()] = value.strip()
    return meta, 0


def source_dir(value):
    """`ext/` and `data/` are relative to the repo root; the rest to SOURCES."""
    return ROOT / value if value.startswith(("ext/", "data/")) else SOURCES / value


def cnf_labels(path, cache={}):
    if path not in cache:
        cache[path] = {
            m.group(1)
            for m in re.finditer(r"^(?:LABEL|SYMBOL)\s+(\S+)\s", path.read_text(), re.M)
        }
    return cache[path]


def players():
    with INVENTORY.open(encoding="utf-8") as f:
        return {row["player"] for row in csv.DictReader(f)}


def line_count(path, cache={}):
    if path not in cache:
        cache[path] = len(path.read_bytes().splitlines())
    return cache[path]


def starts(row, title):
    """Row begins with title as a whole field: TFMX must not match TFMX-Pro."""
    rest = row[len(title) :]
    return row.startswith(title) and (not rest or rest[0] in ",\t |")


def check_row(dest, num, title, report):
    """A `#L<n>` link must hit an existing line; with a title, that line
    must start with it. Titles keep row links right when files change."""
    rows = dest.read_text(encoding="utf-8", errors="replace").splitlines()
    if not 1 <= num <= len(rows):
        report(f"{dest.name}#L{num} beyond {len(rows)} lines")
    elif title and not starts(rows[num - 1], title):
        report(f'{dest.name}#L{num} does not start with "{title}"')


def check(path, known_players):
    rel = path.resolve().relative_to(ROOT).as_posix()
    lines = path.read_text(encoding="utf-8").splitlines()
    errors = []

    def err(n, rule, detail):
        errors.append(f"{rel}:{n}: {rule}: {detail}")

    meta, body = front_matter(lines)
    is_card = "player" in meta and "source" in meta
    src = source_dir(meta["source"]) if is_card else None
    if is_card and not src.exists():
        err(1, "source", f"{meta['source']} does not exist")
    if is_card and not src.is_dir():
        src = None  # a missing source, or an IRA config cited by label
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
        for target, title in LINK_RE.findall(line):
            if re.match(r"[a-z]+:", target) or target.startswith("#"):
                continue  # URL or in-page anchor
            target, _, anchor = target.partition("#")
            target = target.split("?")[0]
            dest = path.parent / target
            if not dest.exists():
                err(n, "link", f"{target} does not exist")
                continue
            row = re.fullmatch(r"L(\d+)", anchor)
            if row:
                check_row(dest, int(row.group(1)), title, lambda d: err(n, "link", d))
        for name, label in LABEL_CITE_RE.findall(line):
            cnf = ROOT / name
            if not cnf.is_file():
                err(n, "cite", f"{name} does not exist")
            elif label not in cnf_labels(cnf):
                err(n, "cite", f"{name} has no label {label}")
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


ROW_LINK_RE = re.compile(r'(\]\(([^)\s#?]+)(?:\?[^)\s#]*)?#L)(\d+)(\s+"([^"]+)"\))')


def fix_rows(path):
    """Point each titled `#L<n>` link at the row that starts with its title."""
    text = path.read_text(encoding="utf-8")

    def repl(m):
        dest = path.parent / m.group(2)
        if not dest.is_file():
            return m.group(0)
        rows = dest.read_text(encoding="utf-8", errors="replace").splitlines()
        for i, row in enumerate(rows, start=1):
            if starts(row, m.group(5)):
                return f"{m.group(1)}{i}{m.group(4)}"
        return m.group(0)

    new = ROW_LINK_RE.sub(repl, text)
    if new != text:
        path.write_text(new, encoding="utf-8")


def main(argv):
    fix = argv[:1] == ["--fix-rows"]
    argv = argv[1:] if fix else argv
    known = players()
    errors = []
    for arg in map(Path, argv):
        for path in sorted(arg.rglob("*.md")) if arg.is_dir() else [arg]:
            if fix:
                fix_rows(path)
            errors += check(path, known)
    for e in errors:
        print(e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
