#!/usr/bin/env python3
"""Check the structure of player cards against docs/card-template.md.

Usage: cards.py FILE.md|DIR...

A card is a Markdown file whose front matter has a `player` key. Checks:
  - front matter keys and their allowed values; `links` is optional
  - file name matches `player`, and `player` is in data/inventory.csv
  - sections present and in order
  - Streams table: header, scope, name's first word, and Control/Rate words
    from data/glossary.yaml
  - State table: header and scope names

Prints `file:line: rule: detail` for each problem; exits 1 if any.
"""

import csv
import sys
from pathlib import Path

import glossary
from mdtools import heading_lines, read, sections, table

ROOT = Path(__file__).resolve().parent.parent
INVENTORY = ROOT / "data" / "inventory.csv"

KEYS = [
    "player",
    "source",
    "code",
    "control",
    "themes",
    "ideas",
    "related",
    "streams",
    "evidence",
    "links",
]
OPTIONAL = {"links"}
ALLOWED = {
    "code": {"uade", "module", "disasm"},
    "control": {"tables", "commands", "program"},
    "evidence": {"code", "port", "docs", "disasm"},
}
THEMES = {"synthesis", "mixing", "tricks", "emulation"}
SCOPES = ["song", "track", "voice", "instrument"]
STATE_SCOPES = {"Voice", "Instrument", "Global"}

# (heading, required), in the required order.
SECTIONS = [
    ("Key ideas", True),
    ("Streams", True),
    ("Generators and interactions", False),
    ("State", True),
    ("Open questions", True),
]
STREAMS_HEADER = ["Stream", "Scope", "Carries", "Control", "Rate"]
STATE_HEADER = ["Scope", "Fields"]


def players():
    with INVENTORY.open(encoding="utf-8") as f:
        return {row["player"] for row in csv.DictReader(f)}


def is_text_list(value):
    return isinstance(value, list) and all(isinstance(x, str) for x in value)


def words(cell):
    return [w.strip() for w in cell.split(",") if w.strip()]


def check(path, known, vocab):
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

    for key in KEYS:
        if key not in meta and key not in OPTIONAL:
            err(1, "front-matter", f"missing `{key}`")
    for key in meta:
        if key not in KEYS:
            err(1, "front-matter", f"unknown `{key}`")
    for key, allowed in ALLOWED.items():
        if key in meta and meta[key] not in allowed:
            err(1, "front-matter", f"`{key}: {meta[key]}` not in {sorted(allowed)}")

    player = str(meta["player"])
    if path.stem != player:
        err(1, "player", f"file name should be {player}.md")
    if player not in known:
        err(1, "player", f"{player} not in data/inventory.csv")

    themes = meta.get("themes", [])
    if not is_text_list(themes) or not set(themes) <= THEMES:
        err(1, "front-matter", f"`themes` must be a list from {sorted(THEMES)}")
    for key in ("ideas", "related", "links"):
        if not is_text_list(meta.get(key, [])):
            err(1, "front-matter", f"`{key}` must be a list")
    streams = meta.get("streams", {})
    if (
        not isinstance(streams, dict)
        or not set(streams) <= set(SCOPES)
        or not all(isinstance(v, int) for v in streams.values())
    ):
        err(1, "front-matter", f"`streams` must map {SCOPES} to numbers")
        streams = {}
    if streams.get("track") == 0:
        err(1, "front-matter", "omit `track` when tracks are bound to voices")

    # Sections, in order.
    found = heading_lines(doc)
    names = [name for _, name in found]
    order = [name for name, _ in SECTIONS]
    for name, required in SECTIONS:
        if required and name not in names:
            err(1, "section", f"missing `## {name}`")
    for n, name in found:
        if name not in order:
            err(n, "section", f"unknown `## {name}`")
    known_found = [name for name in names if name in order]
    if known_found != sorted(known_found, key=order.index):
        err(1, "section", f"order should be {order}")

    body = sections(doc)
    if "Streams" in body:
        rows = table(body["Streams"])
        if not rows or rows[0][1] != STREAMS_HEADER:
            err(
                rows[0][0] if rows else 1, "streams", f"header must be {STREAMS_HEADER}"
            )
        else:
            counts = dict.fromkeys(SCOPES, 0)
            for n, cells in rows[1:]:
                if len(cells) != len(STREAMS_HEADER):
                    err(n, "streams", "wrong number of columns")
                    continue
                name, scope, _, control, rate = cells
                head = name.split()[0] if name.split() else ""
                if head not in vocab["stream_names"]:
                    err(n, "streams", f"name `{head}` not in the glossary")
                if scope not in SCOPES:
                    err(n, "streams", f"scope `{scope}` not in {SCOPES}")
                else:
                    counts[scope] += 1
                for w in words(control):
                    if w not in vocab["control"]:
                        err(n, "streams", f"control `{w}` not in the glossary")
                if rate not in vocab["rate"]:
                    err(n, "streams", f"rate `{rate}` not in the glossary")
            for scope in SCOPES:
                if counts[scope] != streams.get(scope, 0):
                    err(
                        1,
                        "streams",
                        f"`{scope}: {streams.get(scope, 0)}` but table has {counts[scope]}",
                    )

    if "State" in body:
        rows = table(body["State"])
        if not rows or rows[0][1] != STATE_HEADER:
            err(rows[0][0] if rows else 1, "state", f"header must be {STATE_HEADER}")
        else:
            for n, cells in rows[1:]:
                if cells[0] not in STATE_SCOPES:
                    err(n, "state", f"scope `{cells[0]}` not in {sorted(STATE_SCOPES)}")
    return errors


def main(argv):
    known = players()
    vocab = {key: glossary.words(key) for key in ("control", "rate", "stream_names")}
    errors = []
    for arg in map(Path, argv):
        for path in sorted(arg.rglob("*.md")) if arg.is_dir() else [arg]:
            errors += check(path, known, vocab)
    for e in errors:
        print(e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
