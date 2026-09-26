#!/usr/bin/env python3
"""Check that Markdown links and source citations resolve.

Usage: links.py [--fix-rows] FILE.md|DIR...

  --fix-rows  rewrite `#L<n>` of titled links to the row that starts with the
              title; run after data/inventory.csv changes

Checks:
  - relative Markdown links point to existing files
  - `#L<n>` links name an existing line; a link title must start that line,
    e.g. [Future Composer](data/inventory.csv?plain=1#L60 "FutureComposer1.3")
  - player cards (front matter has `player`): `file:line` citations name an
    existing line under the player's source in data/inventory.csv; a bare
    `:line` refers to the file of the previous citation
  - `path.cnf:Label` citations name a LABEL or SYMBOL in an IRA config;
    the path is relative to the repo root, e.g. data/disasm/X.cnf:Play

Markdown is parsed by tools/mdtools.py. Prints `file:line: rule: detail`
for each problem; exits 1 if any.
"""

import csv
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

from mdtools import children, read

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "ext" / "uade" / "amigasrc" / "players"
INVENTORY = ROOT / "data" / "inventory.csv"


def citation(code):
    """Split a code span like `file.s:12`, `:12-14` or `x.cnf:Label`.

    Returns (file, first, last, label); (None, ...) if it is no citation.
    """
    name, sep, tail = code.rpartition(":")
    if not sep:
        return None, None, None, None
    first, _, last = tail.partition("-")
    if first.isdigit() and (not last or last.isdigit()):
        return name, int(first), int(last) if last else None, None
    if name.endswith(".cnf") and tail.isidentifier():
        return name, None, None, tail
    return None, None, None, None


def spans(doc):
    """Yield (line, child) for every inline child in the document body."""
    for token in doc.tokens:
        if token.type == "inline":
            yield from children(token)


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


def sources():
    """{player: source path} from data/inventory.csv."""
    with INVENTORY.open(encoding="utf-8") as f:
        return {row["player"]: row["source"] for row in csv.DictReader(f)}


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


def row_anchor(href):
    """(file part, row) of a link like `data/inventory.csv?plain=1#L60`."""
    target, _, anchor = href.partition("#")
    target = target.split("?")[0]
    row = int(anchor[1:]) if anchor[:1] == "L" and anchor[1:].isdigit() else None
    return target, row


def links(doc):
    """Yield (line, href, title) for each link in the document."""
    for n, child in spans(doc):
        if child.type == "link_open":
            yield n, child.attrs.get("href", ""), child.attrs.get("title")


def check(path, known_sources):
    rel = path.resolve().relative_to(ROOT).as_posix()
    doc = read(path)
    meta = doc.meta
    errors = []

    def err(n, rule, detail):
        errors.append(f"{rel}:{n}: {rule}: {detail}")

    source = known_sources.get(str(meta.get("player", ""))) or ""
    src = source_dir(source) if source else None
    if "player" in meta and not source:
        err(1, "source", f"{meta['player']} has no source in data/inventory.csv")
    if src and not src.is_dir():
        src = None  # an IRA config, cited by label

    for n, href, title in links(doc):
        if urlsplit(href).scheme or href.startswith("#"):
            continue  # URL or in-page anchor
        target, row = row_anchor(href)
        dest = path.parent / target
        if not dest.exists():
            err(n, "link", f"{target} does not exist")
        elif row is not None:
            check_row(dest, row, title, lambda d: err(n, "link", d))

    last_file = None
    for n, child in spans(doc):
        if child.type != "code_inline":
            continue
        name, first, last, label = citation(child.content)
        if name is None:
            continue
        if label:
            cnf = ROOT / name
            if not cnf.is_file():
                err(n, "cite", f"{name} does not exist")
            elif label not in cnf_labels(cnf):
                err(n, "cite", f"{name} has no label {label}")
            continue
        if not src:
            continue
        if name:
            last_file = src / name
        elif last_file is None:
            err(n, "cite", f":{first} has no preceding file")
            continue
        if not last_file.is_file():
            err(n, "cite", f"{name} not found under {source}")
            last_file = None
            continue
        count = line_count(last_file)
        for num in filter(None, (first, last)):
            if not 1 <= num <= count:
                err(n, "cite", f"{last_file.name}:{num} beyond {count} lines")
    return errors


def fix_rows(path):
    """Point each titled `#L<n>` link at the row that starts with its title."""
    text = path.read_text(encoding="utf-8")
    new = text
    for _, href, title in links(read(path)):
        target, row = row_anchor(href)
        dest = path.parent / target
        if row is None or not title or not dest.is_file():
            continue
        rows = dest.read_text(encoding="utf-8", errors="replace").splitlines()
        for i, line in enumerate(rows, start=1):
            if starts(line, title):
                fixed = href[: href.rindex("#L")] + f"#L{i}"
                new = new.replace(f'({href} "{title}")', f'({fixed} "{title}")')
                break
    if new != text:
        path.write_text(new, encoding="utf-8")


def main(argv):
    fix = argv[:1] == ["--fix-rows"]
    argv = argv[1:] if fix else argv
    known = sources()
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
