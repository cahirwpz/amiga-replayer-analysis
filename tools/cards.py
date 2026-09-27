#!/usr/bin/env python3
"""Check the structure of player cards against docs/card-template.md.

Usage: cards.py [--write | --check] FILE.md|DIR...

  --check  (default) report problems
  --write  regenerate the Context table of template 2 cards from
           data/players.yaml and tools/inventory.py

A card is a Markdown file whose front matter has a `player` key. Both
templates check that the file name matches `player`; `player` is a UADE binary,
or has `replay: source`, and has a provenance in data/players.yaml.

Template 2 (`template: 2`), a prose card; its model is the player's spec
(tools/specs.py):
  - front matter keys; sections present and in order
  - Context matches what --write would generate, with the spec's link
  - Composer's view: the aspects Notation and Cost, in order; each may
    repeat
  - no code blocks
  - no `;` in table cells; cited labels are readable CamelCase names
  - `base`: names another card; Composer's view becomes optional

Template 1 (no `template` key), until its cards are migrated:
  - front matter keys and their allowed values
  - sections present and in order; Sequencer and Channel outputs are required
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
  - `base`, on a delta card: names another card. Streams, Sequencer and
    State become optional, and names may come from the base card.

Prints `file:line: rule: detail` for each problem; exits 1 if any.
"""

import os
import re
import sys
from pathlib import Path

import glossary
import players
import inventory
from links import citation
from mdtools import (
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
KEYS = ["player", "control", "themes", "ideas", "streams"]
OPTIONAL_KEYS = ["base", "template"]
# Sections a delta card may leave to its base card.
BASE_COVERS = {"Streams", "Sequencer", "State"}
LEVELS = {"tables", "commands", "program", "none"}
ROLES = ["sequencer", "instrument"]
THEMES = {"synthesis", "mixing", "tricks", "emulation"}
SCOPES = ["song", "track", "voice", "instrument"]
STATE_SCOPES = {"Voice", "Instrument", "Global"}

# (heading, required), in the required order.
SECTIONS = [
    ("Key ideas", True),
    ("Streams", True),
    ("Sequencer", True),
    ("Generators", False),
    ("Channel outputs", True),
    ("Interactions", False),
    ("State", True),
    ("Open questions", True),
]
STREAMS_HEADER = ["Stream", "Scope", "Role", "Carries", "Control", "Rate"]
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


# Template 2. Old cards keep template 1 until they are migrated.
V2_KEYS = ["player", "template", "ideas"]
V2_SECTIONS = [
    ("Context", True),
    ("Key ideas", True),
    ("Composer's view", True),
    ("What is unique", True),
    ("Open questions", False),
]
V2_BASE_COVERS = {"Composer's view"}
CONTEXT_HEADER = ["Fact", "Value"]
COMPOSER_HEADER = ["Aspect", "Answer", "Source"]
COMPOSER_ASPECTS = ["Notation", "Cost"]
UADE_SOURCES = "ext/uade/amigasrc/players"
# A cited label on a template 2 card: CamelCase, no underscores. Raw source
# labels get a readable name in data/annot/ or data/disasm/ first.
LABEL_RE = re.compile(r"[A-Z][A-Za-z0-9]*[a-z][A-Za-z0-9]*")


def is_text_list(value):
    return isinstance(value, list) and all(isinstance(x, str) for x in value)


def words(cell):
    return [w.strip() for w in cell.split(",") if w.strip()]


def own_names(doc):
    """Names of the streams, generators or controllers a card defines."""
    if doc.meta.get("template") == 2:
        return set()
    body = sections(doc)
    return {
        cells[0]
        for name in ("Streams", "Generators")
        if name in body
        for _, cells in table(body[name])[1:]
    }


def check_player(path, meta, known, facts, err):
    player = str(meta["player"])
    if path.stem != player:
        err(1, "player", f"file name should be {player}.md")
    source_only = facts.get(player, {}).get("replay") == "source"
    if player not in known and not source_only:
        err(1, "player", f"{player} is not a binary in ext/uade/players")
    if "provenance" not in facts.get(player, {}):
        err(1, "player", f"{player} has no provenance in data/players.yaml")


def check(path, known, vocab, facts, sources):
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
    template = meta.get("template", 1)
    if template == 2:
        check_v2(path, doc, known, vocab, facts, sources, err)
        return errors
    if template != 1:
        err(1, "front-matter", "`template` must be 1 or 2")
        return errors

    for key in KEYS:
        if key not in meta:
            err(1, "front-matter", f"missing `{key}`")
    for key in meta:
        if key not in KEYS + OPTIONAL_KEYS:
            err(1, "front-matter", f"unknown `{key}`")
    inherited = None  # streams and generators of a valid base card
    if "base" in meta:
        base = path.parent / f"{meta['base']}.md"
        if meta["base"] == meta.get("player") or not base.is_file():
            err(1, "base", f"`{meta['base']}` is no other card in {path.parent.name}/")
        else:
            inherited = own_names(read(base))
    control = meta.get("control")
    if control is not None and (
        not isinstance(control, dict)
        or set(control) != set(ROLES)
        or not set(control.values()) <= LEVELS
    ):
        err(1, "front-matter", f"`control` must map {ROLES} to {sorted(LEVELS)}")

    check_player(path, meta, known, facts, err)

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
        if inherited is not None and name in BASE_COVERS:
            continue
        if required and name not in names:
            err(1, "section", f"missing `## {name}`")
    for n, name in found:
        if name not in order:
            err(n, "section", f"unknown `## {name}`")
    known_found = [name for name in names if name in order]
    if known_found != sorted(known_found, key=order.index):
        err(1, "section", f"order should be {order}")

    body = sections(doc)
    names = set(inherited or ())  # streams and generators this card may name
    if "Streams" in body:
        rows = table(body["Streams"])
        if not rows or rows[0][1] != STREAMS_HEADER:
            n = rows[0][0] if rows else 1
            err(n, "streams", f"header must be {STREAMS_HEADER}")
        else:
            counts = dict.fromkeys(SCOPES, 0)
            for n, cells in rows[1:]:
                if len(cells) != len(STREAMS_HEADER):
                    err(n, "streams", "wrong number of columns")
                    continue
                name, scope, role, _, control, rate = cells
                if role not in vocab["roles"]:
                    err(n, "streams", f"role `{role}` not in the glossary")
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
        code = f["provenance"] + (" (guess)" if f.get("provenance_guess") else "")
        src = sources.get(player, {}).get("source") or f.get("source", "")
        if src:
            path = src if src.startswith("ext/") else f"{UADE_SOURCES}/{src}"
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


def check_v2(path, doc, known, vocab, facts, sources, err):
    meta = doc.meta
    for key in V2_KEYS:
        if key not in meta:
            err(1, "front-matter", f"missing `{key}`")
    for key in meta:
        if key not in V2_KEYS + ["base"]:
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
    order = [name for name, _ in V2_SECTIONS]
    present = [name for _, name in found]
    for name, required in V2_SECTIONS:
        if required and name not in present and not (delta and name in V2_BASE_COVERS):
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


def write_context(path, facts, sources):
    """Regenerate a template 2 card's Context; return True if it changed."""
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
    write = "--write" in argv
    argv = [a for a in argv if a not in ("--write", "--check")]
    known = players.binaries()
    keys = ["control", "rate", "stream_names", "roles"]
    keys += ["note_on", "outputs", "write_modes", "ends"]
    keys += list(ASPECTS.values())
    vocab = {key: glossary.words(key) for key in keys}
    facts = players.load()
    sources = inventory.table()
    paths = [
        path
        for arg in map(Path, argv)
        for path in (sorted(arg.rglob("*.md")) if arg.is_dir() else [arg])
    ]
    if write:
        for path in paths:
            if write_context(path, facts, sources):
                print(f"wrote {path}")
        return 0
    errors = []
    for path in paths:
        errors += check(path, known, vocab, facts, sources)
    for e in errors:
        print(e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
