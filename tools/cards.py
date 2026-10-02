#!/usr/bin/env python3
"""Check the structure of player cards against docs/card-template.md.

Usage: cards.py FILE.md|DIR...

A card is a Markdown file whose front matter has a `player` key. Checks, per
docs/card-template.md; its model is the player's spec (tools/specs.py):
  - the file name matches `player`; `player` is a UADE binary, or has
    `replay: source`, and has a provenance in data/players.yaml
  - front matter keys, with `template` 3; sections present and in order
  - no code blocks
  - no `;` in table cells; cited labels are readable CamelCase names
  - `base`: names another card
  - each `ideas` slug belongs to a family in data/ideas.yaml

Prints `file:line: rule: detail` for each problem; exits 1 if any.
"""

import re
import sys
from pathlib import Path

import cli
import players
import yaml
from links import citation
from mdtools import children, heading_lines, read, tables

ROOT = Path(__file__).resolve().parent.parent

# Analysis only. Facts about the player live in data/players.yaml.
KEYS = ["player", "template", "ideas"]
TEMPLATE = 3
# The author's view: ideas, then the flow by owner, with its traps.
SECTIONS = [
    ("Unique ideas", True),
    ("How it plays", True),
    ("Open questions", False),
]
# A cited label on a card: CamelCase, no underscores. Raw source
# labels get a readable name in data/annot/ or data/disasm/ first.
LABEL_RE = re.compile(r"[A-Z][A-Za-z0-9]*[a-z][A-Za-z0-9]*")
IDEAS = ROOT / "data" / "ideas.yaml"


def idea_slugs():
    """Every idea slug of a family in data/ideas.yaml."""
    families = yaml.safe_load(IDEAS.read_text(encoding="utf-8"))
    return {slug for family in families.values() for slug in family["ideas"]}


def is_text_list(value):
    return isinstance(value, list) and all(isinstance(x, str) for x in value)


def check_player(path, meta, known, facts, err):
    player = str(meta["player"])
    if path.stem != player:
        err(1, "player", f"file name should be {player}.md")
    source_only = facts.get(player, {}).get("replay") == "source"
    if player not in known and not source_only:
        err(1, "player", f"{player} is not a binary in ext/uade/players")
    if "provenance" not in facts.get(player, {}):
        err(1, "player", f"{player} has no provenance in data/players.yaml")


def check(path, known, facts):
    rel = path.resolve().relative_to(ROOT).as_posix()
    doc = read(path)
    meta = doc.meta
    errors = []

    def err(n, rule, detail):
        errors.append(f"{rel}:{n}: {rule}: {detail}")

    if doc.meta_error:
        err(1, "front-matter", doc.meta_error)
    if "player" not in meta:
        return errors
    if meta.get("template") != TEMPLATE:
        err(1, "front-matter", f"`template` must be {TEMPLATE}")
        return errors
    check_card(path, doc, known, facts, err)
    return errors


def check_card(path, doc, known, facts, err):
    meta = doc.meta
    for key in KEYS:
        if key not in meta:
            err(1, "front-matter", f"missing `{key}`")
    for key in meta:
        if key not in KEYS + ["base"]:
            err(1, "front-matter", f"unknown `{key}`")
    if not is_text_list(meta.get("ideas", [])):
        err(1, "front-matter", "`ideas` must be a list")
    else:
        for slug in sorted(set(meta.get("ideas", [])) - idea_slugs()):
            err(1, "ideas", f"`{slug}` is in no family of data/ideas.yaml")
    if "base" in meta:
        base = path.parent / f"{meta['base']}.md"
        if meta["base"] == meta.get("player") or not base.is_file():
            err(1, "base", f"`{meta['base']}` is no other card in {path.parent.name}/")
    check_player(path, meta, known, facts, err)

    found = heading_lines(doc)
    order = [name for name, _ in SECTIONS]
    present = [name for _, name in found]
    for name, required in SECTIONS:
        if required and name not in present:
            err(1, "section", f"missing `## {name}`")
    for n, name in found:
        if name not in order:
            err(n, "section", f"unknown `## {name}`")
    known_found = [name for name in present if name in order]
    if known_found != sorted(known_found, key=order.index):
        err(1, "section", f"order should be {order}")

    for token in doc.tokens:
        if token.type in ("fence", "code_block") and token.map:
            err(token.map[0] + 1, "code", "no code on a card; it goes to the spec")

    for rows in tables(doc.tokens):
        for n, cells in rows:
            for cell in cells:
                if ";" in cell:
                    err(n, "cell", f"one fact per cell, no `;`: {cell[:40]}")
    for token in doc.tokens:
        if token.type != "inline":
            continue
        for n, child in children(token):
            cited = citation(child.content) if child.type == "code_inline" else None
            if cited and cited[1] and not LABEL_RE.fullmatch(cited[1]):
                err(n, "label", f"`{cited[1]}` is no readable name; rename it")


def main(argv):
    parser = cli.parser(__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args(argv)
    known = players.binaries()
    facts = players.load()
    paths = [
        path
        for arg in args.paths
        for path in (sorted(arg.rglob("*.md")) if arg.is_dir() else [arg])
    ]
    errors = []
    for path in paths:
        errors += check(path, known, facts)
    for e in errors:
        print(e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
