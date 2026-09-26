#!/usr/bin/env python3
"""Check the structure of player cards against docs/card-template.md.

Usage: cards.py FILE.md|DIR...

A card is a Markdown file whose front matter has a `player` key. Checks:
  - front matter keys and their allowed values; `links` is optional
  - file name matches `player`, and `player` is in data/inventory.csv
  - sections present and in order
  - Streams table: header, scope, and Control/Rate words from the glossary
  - State table: header and scope names

Prints `file:line: rule: detail` for each problem; exits 1 if any.
"""

import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GLOSSARY = ROOT / "docs" / "glossary.md"
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


def vocabulary(section):
    """Bold terms of one glossary section, e.g. "Control vocabulary"."""
    words, inside = set(), False
    for line in GLOSSARY.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            inside = line[3:].strip() == section
        elif inside:
            m = re.match(r"\|\s*\*\*(.+?)\*\*", line)
            if m:
                words.add(m.group(1))
    return words


def players():
    with INVENTORY.open(encoding="utf-8") as f:
        return {row["player"] for row in csv.DictReader(f)}


def front_matter(lines):
    if not lines or lines[0].strip() != "---":
        return None, 0
    meta = {}
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return meta, i + 1
        key, _, value = lines[i].partition(":")
        meta[key.strip()] = value.strip()
    return None, 0


def parse_list(value):
    m = re.fullmatch(r"\[(.*)\]", value)
    return (
        None if m is None else [x.strip() for x in m.group(1).split(",") if x.strip()]
    )


def parse_map(value):
    m = re.fullmatch(r"\{(.*)\}", value)
    if m is None:
        return None
    out = {}
    for pair in filter(None, (p.strip() for p in m.group(1).split(","))):
        key, _, num = pair.partition(":")
        if not num.strip().isdigit():
            return None
        out[key.strip()] = int(num)
    return out


def tables(lines, start, end):
    """Rows of the first table between two line indices, as (lineno, cells)."""
    rows = []
    for i in range(start, end):
        s = lines[i].strip()
        if s.startswith("|"):
            if not re.fullmatch(r"[|:\-\s]+", s):
                rows.append((i + 1, [c.strip() for c in s.strip("|").split("|")]))
        elif rows:
            break
    return rows


def words(cell):
    return [w.strip() for w in cell.split(",") if w.strip()]


def check(path, known, control_words, rate_words):
    rel = path.resolve().relative_to(ROOT).as_posix()
    lines = path.read_text(encoding="utf-8").splitlines()
    meta, body = front_matter(lines)
    if meta is None or "player" not in meta:
        return []
    errors = []

    def err(n, rule, detail):
        errors.append(f"{rel}:{n}: {rule}: {detail}")

    for key in KEYS:
        if key not in meta and key not in OPTIONAL:
            err(1, "front-matter", f"missing `{key}`")
    for key in meta:
        if key not in KEYS:
            err(1, "front-matter", f"unknown `{key}`")
    for key, allowed in ALLOWED.items():
        if key in meta and meta[key] not in allowed:
            err(1, "front-matter", f"`{key}: {meta[key]}` not in {sorted(allowed)}")

    player = meta.get("player", "")
    if path.stem != player:
        err(1, "player", f"file name should be {player}.md")
    if player not in known:
        err(1, "player", f"{player} not in data/inventory.csv")

    themes = parse_list(meta.get("themes", "[]"))
    if themes is None or not set(themes) <= THEMES:
        err(1, "front-matter", f"`themes` must be a list from {sorted(THEMES)}")
    for key in ("ideas", "related", "links"):
        if parse_list(meta.get(key, "[]")) is None:
            err(1, "front-matter", f"`{key}` must be a list")
    streams = parse_map(meta.get("streams", "{}"))
    if streams is None or not set(streams) <= set(SCOPES):
        err(1, "front-matter", f"`streams` must map {SCOPES} to numbers")
        streams = {}
    if streams.get("track") == 0:
        err(1, "front-matter", "omit `track` when tracks are bound to voices")

    # Sections, in order.
    found = [
        (i, line[3:].strip())
        for i, line in enumerate(lines)
        if i >= body and line.startswith("## ")
    ]
    names = [name for _, name in found]
    order = [name for name, _ in SECTIONS]
    for name, required in SECTIONS:
        if required and name not in names:
            err(1, "section", f"missing `## {name}`")
    for _, name in found:
        if name not in order:
            err(1, "section", f"unknown `## {name}`")
    known_found = [n for n in names if n in order]
    if known_found != sorted(known_found, key=order.index):
        err(1, "section", f"order should be {order}")

    def section_rows(name):
        for k, (i, n) in enumerate(found):
            if n == name:
                end = found[k + 1][0] if k + 1 < len(found) else len(lines)
                return tables(lines, i + 1, end)
        return None

    rows = section_rows("Streams")
    if rows is not None:
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
                _, scope, _, control, rate = cells
                if scope not in SCOPES:
                    err(n, "streams", f"scope `{scope}` not in {SCOPES}")
                else:
                    counts[scope] += 1
                for w in words(control):
                    if w not in control_words:
                        err(n, "streams", f"control `{w}` not in the glossary")
                if rate not in rate_words:
                    err(n, "streams", f"rate `{rate}` not in the glossary")
            for scope in SCOPES:
                if counts[scope] != streams.get(scope, 0):
                    err(
                        1,
                        "streams",
                        f"`{scope}: {streams.get(scope, 0)}` but table has {counts[scope]}",
                    )

    rows = section_rows("State")
    if rows is not None:
        if not rows or rows[0][1] != STATE_HEADER:
            err(rows[0][0] if rows else 1, "state", f"header must be {STATE_HEADER}")
        else:
            for n, cells in rows[1:]:
                if cells[0] not in STATE_SCOPES:
                    err(n, "state", f"scope `{cells[0]}` not in {sorted(STATE_SCOPES)}")
    return errors


def main(argv):
    known = players()
    control_words = vocabulary("Control vocabulary")
    rate_words = vocabulary("Rate vocabulary")
    errors = []
    for arg in map(Path, argv):
        for path in sorted(arg.rglob("*.md")) if arg.is_dir() else [arg]:
            errors += check(path, known, control_words, rate_words)
    for e in errors:
        print(e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
