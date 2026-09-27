#!/usr/bin/env python3
"""Check that Markdown links and source citations resolve.

Usage: links.py FILE.md|DIR...

Checks:
  - relative Markdown links point to existing files
  - no link names a line, e.g. `x.asm#L60` or a GitHub URL with `#L60`
  - `file:Label` citations name a label in that file, as
    annot.cited_labels() finds it
    Paths starting with a repo folder, e.g. ext/, data/ or specs/, are
    relative to the repo root. In
    player cards (front matter has `player`), other paths are relative to
    the player's source, as tools/inventory.py finds it. A bare `:Label`
    refers to the file of the previous citation. In a player card, before
    any other citation, it refers to data/annot/<player>.yaml, else to
    data/disasm/<player>.cnf. If the card's player has a `spec` in
    data/players.yaml, a label cited from that file must also be a
    function or class in the spec.
  - no citation names a line number, e.g. `file.s:12`
  - code spans that start with a repo folder, e.g. `docs/x.md` or
    `ext/uade/y.s:12`, name a path that exists. Placeholders in angle
    brackets and globs are skipped.

Markdown is parsed by tools/mdtools.py. Prints `file:line: rule: detail`
for each problem; exits 1 if any.
"""

import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

import annot
import inventory
import players
import specs
from mdtools import children, read

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "ext" / "uade" / "amigasrc" / "players"


# Files a citation may name.
CITED = (".s", ".asm", ".a", ".i", ".c", ".h", ".cnf", ".yaml", ".py")


def citation(code):
    """Split a code span like `file.s:Label`, `:Label` or `file.s:12`.

    Returns (file, label, line); file is "" for a bare `:Label`. Returns
    None if the span is no citation.
    """
    name, sep, tail = code.rpartition(":")
    if not sep or (name and not name.lower().endswith(CITED)):
        return None
    if re.fullmatch(r"\d+(-\d+)?", tail):
        return name, None, tail
    if tail.isidentifier():
        return name, tail, None
    return None


# Code spans starting with these name repo paths, relative to the root.
REPO_DIRS = (
    "data/",
    "details/",
    "docs/",
    "ext/",
    "ideas/",
    "players/",
    "specs/",
    "tests/",
    "tools/",
)


def repo_path(code):
    """The path a code span names, without `:line`; None if it names none."""
    if not code.startswith(REPO_DIRS) or any(c in code for c in "<>*"):
        return None
    path = code.split(":")[0]
    if not (ROOT / path).exists() and (ROOT / path.split()[0]).exists():
        return path.split()[0]  # a command with arguments
    return path


def spans(doc):
    """Yield (line, child) for every inline child in the document body."""
    for token in doc.tokens:
        if token.type == "inline":
            yield from children(token)


def source_dir(value):
    """`ext/` and `data/` are relative to the repo root; the rest to SOURCES."""
    return ROOT / value if value.startswith(("ext/", "data/")) else SOURCES / value


def sources():
    """{player: source path}, as tools/inventory.py finds it."""
    return {player: row["source"] for player, row in inventory.table().items()}


def default_file(player):
    """The file a card's bare `:Label` names before any other citation: the
    player's annotation, else its IRA config."""
    for path in (
        ROOT / "data/annot" / f"{player}.yaml",
        ROOT / "data/disasm" / f"{player}.cnf",
    ):
        if path.is_file():
            return path
    return None


def names_line(href):
    """True for a link to a line, e.g. `x.asm?plain=1#L60` or `#L60-L64`."""
    return re.fullmatch(r"L\d+(-L?\d+)?", urlsplit(href).fragment) is not None


def links(doc):
    """Yield (line, href) for each link in the document."""
    for n, child in spans(doc):
        if child.type == "link_open":
            yield n, child.attrs.get("href", "")


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
        err(1, "source", f"{meta['player']} has no source in tools/inventory.py")
    if src and not src.is_dir():
        src = None  # an IRA config, cited by label

    for n, href in links(doc):
        if names_line(href):
            err(n, "link", f"{href} names a line; cite a label")
        if urlsplit(href).scheme or href.startswith("#"):
            continue  # URL or in-page anchor
        target = urlsplit(href).path
        if not (path.parent / target).exists():
            err(n, "link", f"{target} does not exist")

    last_file = default_file(str(meta["player"])) if "player" in meta else None
    own = last_file
    spec = players.load().get(str(meta.get("player")), {}).get("spec")
    in_spec = {n.name for n in specs.defined(ROOT / spec)} if spec else None
    for n, child in spans(doc):
        if child.type != "code_inline":
            continue
        path_ = repo_path(child.content)
        if path_ and not (ROOT / path_).exists():
            err(n, "path", f"{path_} does not exist")
        cite = citation(child.content)
        if cite is None:
            continue
        name, label, line = cite
        if line:
            err(n, "cite", f"`{child.content}` names a line; cite a label")
            continue
        if name.startswith(REPO_DIRS):
            last_file = ROOT / name
        elif name and src:
            last_file = src / name
        elif name:
            err(n, "cite", f"{name} must start with ext/ or data/")
            last_file = None
            continue
        elif last_file is None:
            err(n, "cite", f":{label} has no preceding file")
            continue
        if not last_file.is_file():
            where = f"under {source}" if src and not name.startswith(REPO_DIRS) else ""
            err(n, "cite", f"{name or last_file.name} not found {where}".rstrip())
            last_file = None
            continue
        known = annot.cited_labels(last_file)
        if known is None:
            err(n, "cite", f"{last_file.name} has no labels")
        elif label not in known:
            err(n, "cite", f"{last_file.name} has no label {label}")
        elif in_spec is not None and last_file == own and label not in in_spec:
            err(n, "cite", f"{label} is not a function or class in {spec}")
    return errors


def main(argv):
    known = sources()
    errors = []
    for arg in map(Path, argv):
        for path in sorted(arg.rglob("*.md")) if arg.is_dir() else [arg]:
            errors += check(path, known)
    for e in errors:
        print(e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
