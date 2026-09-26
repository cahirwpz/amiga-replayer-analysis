#!/usr/bin/env python3
"""Check the structure of player cards against docs/card-template.md.

Usage: cards.py FILE.md|DIR...

A card is a Markdown file whose front matter has a `player` key. Checks:
  - front matter keys and their allowed values
  - file name matches `player`; `player` is a UADE binary, or has
    `replay: source`, and has a provenance in data/players.yaml
  - sections present and in order
  - Streams table: header, scope, role, name's first word, and Control/Rate
    words from data/glossary.yaml
  - Sequencer table: the aspects in order; each value word from the
    aspect's glossary section
  - Generators table: scope, Rate and Note-on words; Set by names a stream
  - Channel outputs table: output words; each writer is `Name (mode)` with a
    name from the card and a write mode from the glossary
  - Interactions table: From and To name the card's streams or generators,
    or an `ends` word from the glossary
  - State table: header and scope names

Legacy forms stay accepted until all cards are migrated (see TODO.md): a
single `control` level, the Streams table without Role, and the section
"Generators and interactions".

Prints `file:line: rule: detail` for each problem; exits 1 if any.
"""

import re
import sys
from pathlib import Path

import glossary
import players
from mdtools import heading_lines, read, sections, table

ROOT = Path(__file__).resolve().parent.parent

# Analysis only. Facts about the player live in data/players.yaml.
KEYS = ["player", "control", "themes", "ideas", "streams"]
LEVELS = {"tables", "commands", "program", "none"}
ROLES = ["sequencer", "instrument"]
THEMES = {"synthesis", "mixing", "tricks", "emulation"}
SCOPES = ["song", "track", "voice", "instrument"]
STATE_SCOPES = {"Voice", "Instrument", "Global"}

# (heading, required), in the required order.
SECTIONS = [
    ("Key ideas", True),
    ("Streams", True),
    ("Sequencer", False),
    ("Generators", False),
    ("Generators and interactions", False),  # legacy
    ("Channel outputs", False),
    ("Interactions", False),
    ("State", True),
    ("Open questions", True),
]
STREAMS_HEADER = ["Stream", "Scope", "Role", "Carries", "Control", "Rate"]
LEGACY_STREAMS_HEADER = ["Stream", "Scope", "Carries", "Control", "Rate"]
GENERATORS_HEADER = [
    "Generator",
    "Scope",
    "States",
    "Writes",
    "Rate",
    "Set by",
    "Note-on",
]
OUTPUTS_HEADER = ["Output", "Writers, in tick order"]
INTERACTIONS_HEADER = ["From", "To", "Event"]
SEQUENCER_HEADER = ["Aspect", "Value", "Label"]
# Aspect: its glossary section, in the required row order.
ASPECTS = {
    "Time": "seq_time",
    "Unit": "seq_unit",
    "Note end": "seq_note_end",
    "Routing": "seq_routing",
    "Reuse": "seq_reuse",
    "Tempo": "seq_tempo",
}
WRITER_RE = re.compile(r"(.+?) \((.+)\)")
STATE_HEADER = ["Scope", "Fields"]


def is_text_list(value):
    return isinstance(value, list) and all(isinstance(x, str) for x in value)


def words(cell):
    return [w.strip() for w in cell.split(",") if w.strip()]


def check(path, known, vocab, facts):
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
        if key not in meta:
            err(1, "front-matter", f"missing `{key}`")
    for key in meta:
        if key not in KEYS:
            err(1, "front-matter", f"unknown `{key}`")
    control = meta.get("control")
    if isinstance(control, dict):
        if set(control) != set(ROLES) or not set(control.values()) <= LEVELS:
            err(1, "front-matter", f"`control` must map {ROLES} to {sorted(LEVELS)}")
    elif control is not None and control not in LEVELS - {"none"}:
        err(1, "front-matter", f"`control: {control}` not in {sorted(LEVELS)}")

    player = str(meta["player"])
    if path.stem != player:
        err(1, "player", f"file name should be {player}.md")
    source_only = facts.get(player, {}).get("replay") == "source"
    if player not in known and not source_only:
        err(1, "player", f"{player} is not a binary in ext/uade/players")
    if "provenance" not in facts.get(player, {}):
        err(1, "player", f"{player} has no provenance in data/players.yaml")

    themes = meta.get("themes", [])
    if not is_text_list(themes) or not set(themes) <= THEMES:
        err(1, "front-matter", f"`themes` must be a list from {sorted(THEMES)}")
    if not is_text_list(meta.get("ideas", [])):
        err(1, "front-matter", "`ideas` must be a list")
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
    names = set()  # streams and generators on this card
    if "Streams" in body:
        rows = table(body["Streams"])
        header = rows[0][1] if rows else None
        if header not in (STREAMS_HEADER, LEGACY_STREAMS_HEADER):
            err(
                rows[0][0] if rows else 1, "streams", f"header must be {STREAMS_HEADER}"
            )
        else:
            counts = dict.fromkeys(SCOPES, 0)
            for n, cells in rows[1:]:
                if len(cells) != len(header):
                    err(n, "streams", "wrong number of columns")
                    continue
                if header == STREAMS_HEADER:
                    name, scope, role, _, control, rate = cells
                    if role not in vocab["roles"]:
                        err(n, "streams", f"role `{role}` not in the glossary")
                else:
                    name, scope, _, control, rate = cells
                names.add(name)
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

    if "Sequencer" in body:
        rows = table(body["Sequencer"])
        if not rows or rows[0][1] != SEQUENCER_HEADER:
            n = rows[0][0] if rows else 1
            err(n, "sequencer", f"header must be {SEQUENCER_HEADER}")
        else:
            aspects = [cells[0] for _, cells in rows[1:]]
            if aspects != list(ASPECTS):
                err(rows[0][0], "sequencer", f"aspects must be {list(ASPECTS)}")
            for n, cells in rows[1:]:
                if len(cells) != len(SEQUENCER_HEADER):
                    err(n, "sequencer", "wrong number of columns")
                    continue
                aspect, value, _ = cells
                allowed = vocab.get(ASPECTS.get(aspect), set())
                for w in words(value):
                    if w not in allowed:
                        err(
                            n,
                            "sequencer",
                            f"{aspect.lower()} `{w}` not in the glossary",
                        )

    if "Generators" in body:
        rows = table(body["Generators"])
        if not rows or rows[0][1] != GENERATORS_HEADER:
            n = rows[0][0] if rows else 1
            err(n, "generators", f"header must be {GENERATORS_HEADER}")
        else:
            streams_found = set(names)
            for n, cells in rows[1:]:
                if len(cells) != len(GENERATORS_HEADER):
                    err(n, "generators", "wrong number of columns")
                    continue
                name, scope, _, _, rate, set_by, note_on = cells
                names.add(name)
                if scope not in SCOPES:
                    err(n, "generators", f"scope `{scope}` not in {SCOPES}")
                if rate not in vocab["rate"]:
                    err(n, "generators", f"rate `{rate}` not in the glossary")
                if note_on not in vocab["note_on"]:
                    err(n, "generators", f"note-on `{note_on}` not in the glossary")
                for w in words(set_by):
                    if w not in streams_found | {"instrument"}:
                        err(n, "generators", f"set by `{w}`: not a stream on the card")

    if "Channel outputs" in body:
        rows = table(body["Channel outputs"])
        if not rows or rows[0][1] != OUTPUTS_HEADER:
            n = rows[0][0] if rows else 1
            err(n, "outputs", f"header must be {OUTPUTS_HEADER}")
        else:
            for n, cells in rows[1:]:
                if len(cells) != len(OUTPUTS_HEADER):
                    err(n, "outputs", "wrong number of columns")
                    continue
                output, writers = cells
                if output not in vocab["outputs"]:
                    err(n, "outputs", f"output `{output}` not in the glossary")
                for w in words(writers):
                    m = WRITER_RE.fullmatch(w)
                    if not m:
                        err(n, "outputs", f"writer `{w}` must be `Name (mode)`")
                        continue
                    if m[1] not in names:
                        err(n, "outputs", f"writer `{m[1]}` is not on the card")
                    if m[2] not in vocab["write_modes"]:
                        err(n, "outputs", f"mode `{m[2]}` not in the glossary")

    if "Interactions" in body:
        rows = table(body["Interactions"])
        if not rows or rows[0][1] != INTERACTIONS_HEADER:
            n = rows[0][0] if rows else 1
            err(n, "interactions", f"header must be {INTERACTIONS_HEADER}")
        else:
            for n, cells in rows[1:]:
                if len(cells) != len(INTERACTIONS_HEADER):
                    err(n, "interactions", "wrong number of columns")
                    continue
                for end in cells[:2]:
                    if end not in names | vocab["ends"]:
                        err(n, "interactions", f"`{end}` is not on the card")

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
    known = players.binaries()
    keys = ["control", "rate", "stream_names", "roles"]
    keys += ["note_on", "outputs", "write_modes", "ends"]
    keys += list(ASPECTS.values())
    vocab = {key: glossary.words(key) for key in keys}
    facts = players.load()
    errors = []
    for arg in map(Path, argv):
        for path in sorted(arg.rglob("*.md")) if arg.is_dir() else [arg]:
            errors += check(path, known, vocab, facts)
    for e in errors:
        print(e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
