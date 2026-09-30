#!/usr/bin/env python3
"""Check the structure of player cards against docs/card-template.md.

Usage: cards.py [--write | --check] FILE.md|DIR...

  --check  (default) report problems
  --write  regenerate the Context table of cards from
           data/players.yaml and tools/inventory.py

A card is a Markdown file whose front matter has a `player` key. Checks, per
docs/card-template.md; its model is the player's spec (tools/specs.py):
  - the file name matches `player`; `player` is a UADE binary, or has
    `replay: source`, and has a provenance in data/players.yaml
  - front matter keys, with `template: 2`; sections present and in order
  - Context matches what --write would generate, with the spec's link
  - Composer's view: the aspects Notation and Cost, in order; each may
    repeat
  - no code blocks
  - no `;` in table cells; cited labels are readable CamelCase names
  - `base`: names another card; Composer's view becomes optional

Prints `file:line: rule: detail` for each problem; exits 1 if any.
"""

import os
import re
import sys
from pathlib import Path

import cli
import players
import inventory
from links import citation
from mdtools import (
    CODE,
    children,
    format_table,
    heading_lines,
    read,
    sections,
    table,
    tables,
)

ROOT = Path(__file__).resolve().parent.parent

# Analysis only. Facts about the player live in data/players.yaml.
KEYS = ["player", "template", "ideas"]
SECTIONS = [
    ("Context", True),
    ("Key ideas", True),
    ("Composer's view", True),
    ("What is unique", True),
    ("Open questions", False),
]
BASE_COVERS = {"Composer's view"}
CONTEXT_HEADER = ["Fact", "Value"]
COMPOSER_HEADER = ["Aspect", "Answer", "Source"]
COMPOSER_ASPECTS = ["Notation", "Cost"]
# A Composer's view source: the manual, or labels in the spec.
SOURCE_RE = re.compile(rf"\(manual\)|{CODE}( {CODE})*")
UADE_SOURCES = "ext/uade/amigasrc/players"
# A cited label on a card: CamelCase, no underscores. Raw source
# labels get a readable name in data/annot/ or data/disasm/ first.
LABEL_RE = re.compile(r"[A-Z][A-Za-z0-9]*[a-z][A-Za-z0-9]*")


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


def check(path, known, facts, sources):
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
    if meta.get("template") != 2:
        err(1, "front-matter", "`template` must be 2")
        return errors
    check_card(path, doc, known, facts, sources, err)
    return errors


def card_link(name, cards):
    """A player name, linked to its card if there is one."""
    if (cards / f"{name}.md").is_file():
        return f"[{name}]({name}.md)"
    return f"`{name}`"


def context_rows(player, facts, sources, cards):
    """Rows of a card's Context table, from data/players.yaml."""
    f = facts.get(player, {})
    rows = [["Player", f"`{player}`"]]
    for key in ("author", "year", "game"):
        if key in f:
            rows.append([key.capitalize(), str(f[key])])
    if "family" in f:
        rows.append(["Family", str(f["family"])])
    if "after" in f:
        rows.append(["Grew from", card_link(f["after"]["player"], cards)])
    if "influences" in f:
        names = [
            card_link(i["player"], cards) if "player" in i else i["name"]
            for i in f["influences"]
        ]
        rows.append(["Influences", ", ".join(names)])
    if "provenance" in f:
        code = f["provenance"]
        src = sources.get(player, {}).get("source") or f.get("source", "")
        if src:
            path = src if src.startswith(("ext/", "data/")) else f"{UADE_SOURCES}/{src}"
            code += f": `{path}`"
        rows.append(["Code read", code])
    if "spec" in f:
        href = os.path.relpath(ROOT / f["spec"], cards)
        rows.append(["Spec", f"[{f['spec']}]({href})"])
    if "links" in f:
        hosts = [f"[{u.split('/')[2]}]({u})" for u in f["links"]]
        rows.append(["Links", ", ".join(hosts)])
    return rows


def with_context(text, doc, rows):
    """The card's text with its Context section replaced by rows."""
    heads = heading_lines(doc)
    starts = [n for n, name in heads if name == "Context"]
    if not starts:
        return text
    start = starts[0]
    after = [n for n, _ in heads if n > start]
    lines = text.split("\n")
    end = after[0] - 1 if after else len(lines)
    tail = lines[end:] if after else [""]
    return "\n".join(
        lines[:start] + [""] + format_table(CONTEXT_HEADER, rows) + [""] + tail
    )


def grouped(values, order):
    """True if values hold each item of order, in that order; items may repeat."""
    return set(values) == set(order) and values == sorted(values, key=order.index)


def check_rows(rows, header, rule, err):
    """Rows after a correct header; reports a wrong header or width."""
    if not rows or rows[0][1] != header:
        err(rows[0][0] if rows else 1, rule, f"header must be {header}")
        return []
    good = []
    for n, cells in rows[1:]:
        if len(cells) != len(header):
            err(n, rule, "wrong number of columns")
        else:
            good.append((n, cells))
    return good


def check_card(path, doc, known, facts, sources, err):
    meta = doc.meta
    for key in KEYS:
        if key not in meta:
            err(1, "front-matter", f"missing `{key}`")
    for key in meta:
        if key not in KEYS + ["base"]:
            err(1, "front-matter", f"unknown `{key}`")
    if not is_text_list(meta.get("ideas", [])):
        err(1, "front-matter", "`ideas` must be a list")
    delta = False
    if "base" in meta:
        base = path.parent / f"{meta['base']}.md"
        if meta["base"] == meta.get("player") or not base.is_file():
            err(1, "base", f"`{meta['base']}` is no other card in {path.parent.name}/")
        else:
            delta = True
    check_player(path, meta, known, facts, err)

    found = heading_lines(doc)
    order = [name for name, _ in SECTIONS]
    present = [name for _, name in found]
    for name, required in SECTIONS:
        if required and name not in present and not (delta and name in BASE_COVERS):
            err(1, "section", f"missing `## {name}`")
    for n, name in found:
        if name not in order:
            err(n, "section", f"unknown `## {name}`")
    known_found = [name for name in present if name in order]
    if known_found != sorted(known_found, key=order.index):
        err(1, "section", f"order should be {order}")

    body = sections(doc)
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

    if "Context" in body:
        text = path.read_text(encoding="utf-8")
        rows = context_rows(str(meta["player"]), facts, sources, path.parent)
        if with_context(text, doc, rows) != text:
            n = next(n for n, name in found if name == "Context")
            err(n, "context", "out of date; run tools/cards.py --write")

    if "Composer's view" in body:
        rows = check_rows(
            table(body["Composer's view"]), COMPOSER_HEADER, "composer", err
        )
        if rows and not grouped([cells[0] for _, cells in rows], COMPOSER_ASPECTS):
            err(rows[0][0], "composer", f"aspects must be {COMPOSER_ASPECTS}, in order")
        for n, cells in rows:
            if not SOURCE_RE.fullmatch(cells[2]):
                err(n, "composer", f"source `{cells[2]}` must be (manual) or labels")

    if "What is unique" in body:
        for token in body["What is unique"]:
            if token.type == "heading_open":
                err(token.map[0] + 1, "unique", "one flat list, no subheadings")


def write_context(path, facts, sources):
    """Regenerate a card's Context; return True if it changed."""
    doc = read(path)
    if doc.meta.get("template") != 2 or "player" not in doc.meta:
        return False
    text = path.read_text(encoding="utf-8")
    rows = context_rows(str(doc.meta["player"]), facts, sources, path.parent)
    new = with_context(text, doc, rows)
    if new != text:
        path.write_text(new, encoding="utf-8")
    return new != text


def main(argv):
    parser = cli.parser(__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args(argv)
    known = players.binaries()
    facts = players.load()
    sources = inventory.table()
    paths = [
        path
        for arg in args.paths
        for path in (sorted(arg.rglob("*.md")) if arg.is_dir() else [arg])
    ]
    if args.write:
        for path in paths:
            if write_context(path, facts, sources):
                print(f"wrote {path}")
        return 0
    errors = []
    for path in paths:
        errors += check(path, known, facts, sources)
    for e in errors:
        print(e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
