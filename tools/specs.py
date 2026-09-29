#!/usr/bin/env python3
"""Check the player specs in specs/ and the hardware model in hardware/.

Usage: specs.py [DIR]

DIR defaults to specs/, checked with hardware/. Checks:
  - `mypy --strict` passes; a body of `...` is a stub, so empty-body is
    off. Ruff runs as its own pre-commit hook.
  - each spec is named by a player's `spec` in data/players.yaml, except
    the shared ones in SHARED
  - each top-level CamelCase function in a player's spec is a new name
    in `labels:`, and each CamelCase class is in `types:`, of
    data/annot/<player>.yaml or, for a player with several sources,
    data/annot/<player>-*.yaml (see tools/annot.py); functions may also
    be labels in data/disasm/<player>.cnf
  - comments and strings name no label of the source, only new names
    and types: no label it defines, and no disassembler name it uses;
    words in PLAIN_WORDS are read as English
  - comments and strings name no command by number, and no hex number
    equal to a constant of the spec; see tools/numbered.py. A constant's
    definition line may, and so may a hex number that starts a comment,
    an offset or a table entry's value, and a comment that lists offsets
  - snake_case helpers need no label
  - the module docstring names the card, `Card: players/<player>.md`,
    and each data/annot/ file of the player

Prints `file:line: rule: detail` for each problem; exits 1 if any.
"""

import ast
import io
import re
import sys
import tokenize
from pathlib import Path

import annot
import numbered
import players
from mypy import api as mypy_api

ROOT = Path(__file__).resolve().parent.parent
SPECS = ROOT / "specs"
HARDWARE = ROOT / "hardware"
SHARED = {"__init__.py", "controls.py"}
CAMEL = re.compile(r"[A-Z][A-Za-z0-9]*[a-z][A-Za-z0-9]*")
MYPY_LINE = re.compile(r"^(.+?):(\d+): error: (.*)$")
WORD = re.compile(r"[A-Za-z_]\w*(?:\.\w+)*")
LEADING_HEX = re.compile(r"^#\s*[-+]?(?:\$|0x)[0-9A-Fa-f]+\b")  # an offset or a value
GENERATED = re.compile(r"L_[0-9A-Fa-f]+|lb[A-Z][0-9A-F]+")  # disassembler names
# Source labels that are also English words in our prose.
PLAIN_WORDS = {
    "at", "copy", "custom", "envelope", "even", "flags", "loop", "mixer",
    "new", "old", "patterns", "period", "priority", "random", "repeat",
    "return", "samples", "song", "speed", "start", "tables", "tracks",
    "transpose", "volume",
}  # fmt: skip


def annot_files(player):
    annots = ROOT / "data/annot"
    paths = [annots / f"{player}.yaml", *sorted(annots.glob(f"{player}-*.yaml"))]
    return [path for path in paths if path.is_file()]


def anchors(player):
    """(labels, types) a player's spec may use: new names and types."""
    labels, types = set(), set()
    for path in annot_files(player):
        spec = annot.load(path)
        labels |= set((spec.get("labels") or {}).values())
        types |= set(spec.get("types") or {})
    cnf = ROOT / "data/disasm" / f"{player}.cnf"
    if cnf.is_file():
        labels |= annot.cited_labels(cnf)
    return labels - types, types


def old_labels(player):
    """Labels of the player's sources that a spec may not name."""
    old = set()
    for path in annot_files(player):
        if annot.is_config(annot.load(path)):
            continue  # the config's labels are new names
        lines = annot.source_lines(annot.load(path))[1]
        old |= annot.defined(lines)
        code = (annot.code_part(line)[0] for line in lines)
        old |= {
            w for line in code for w in WORD.findall(line) if GENERATED.fullmatch(w)
        }
    labels, types = anchors(player)
    return old - labels - types - PLAIN_WORDS


def check_docstring(path, player):
    """Yield (line, rule, detail) for what the module docstring leaves out."""
    doc = ast.get_docstring(ast.parse(path.read_text(encoding="utf-8"))) or ""
    card = f"players/{player}.md"
    wanted = [f"Card: {card}"]
    wanted += [p.relative_to(ROOT).as_posix() for p in annot_files(player)]
    for text in wanted:
        if text not in " ".join(doc.split()):
            yield 1, "docstring", f"does not name {text}"
    if not (ROOT / card).is_file():
        yield 1, "docstring", f"{card} does not exist"


def check_prose(path, player):
    """Yield (line, rule, detail) for old labels and numbers standing in for
    names in comments and strings."""
    old = old_labels(player)
    consts = numbered.constants(path)
    defining = numbered.definition_lines(path)
    text = path.read_text(encoding="utf-8")
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        if token.type not in (tokenize.COMMENT, tokenize.STRING):
            continue
        for n, line in enumerate(token.string.split("\n")):
            for word in sorted(set(WORD.findall(line)) & old):
                yield token.start[0] + n, "old", f"{word} is not a new name"
        if token.start[0] in defining:
            continue
        prose = token.string
        if token.type == tokenize.COMMENT:
            prose = LEADING_HEX.sub("#", prose)
            if numbered.layout(prose.lstrip("# ")):
                continue
        for n, line in enumerate(prose.split("\n")):
            for _, detail in numbered.find(line, consts):
                yield token.start[0] + n, "number", detail


def defined(path):
    """Top-level CamelCase functions and classes in a spec, as AST nodes."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [n for n in tree.body if CAMEL.fullmatch(getattr(n, "name", ""))]


def check_names(path, player):
    """Yield (line, rule, detail) for CamelCase names without an anchor."""
    labels, types = anchors(player)
    for node in defined(path):
        if isinstance(node, ast.ClassDef) and node.name not in types:
            yield node.lineno, "type", f"{node.name} is not in types of {player}"
        elif isinstance(node, ast.FunctionDef) and node.name not in labels:
            yield node.lineno, "label", f"{node.name} is not a label of {player}"


def check_types(*roots):
    args = ["--strict", "--disable-error-code", "empty-body"]
    args += ["--no-error-summary", "--hide-error-context"]
    args += ["--cache-dir", str(ROOT / "build" / "mypy"), *map(str, roots)]
    out, _, _ = mypy_api.run(args)
    for line in out.splitlines():
        if m := MYPY_LINE.match(line):
            yield f"{m[1]}:{m[2]}: types: {m[3]}"


def spec_players(data=None):
    """{spec path relative to the repo root: player}."""
    data = players.load() if data is None else data
    return {str(f["spec"]): p for p, f in data.items() if "spec" in f}


def main(argv):
    root = Path(argv[0]) if argv else SPECS
    owners = spec_players()
    errors = list(check_types(root, HARDWARE) if root == SPECS else check_types(root))
    for path in sorted(root.glob("*.py")):
        rel = path.resolve().relative_to(ROOT).as_posix()
        if path.name in SHARED:
            continue
        player = owners.get(rel)
        if player is None:
            errors.append(f"{rel}:1: owner: no player in data/players.yaml has it")
            continue
        checks = [check_names, check_docstring, check_prose]
        for n, rule, detail in [x for check in checks for x in check(path, player)]:
            errors.append(f"{rel}:{n}: {rule}: {detail}")
    for e in errors:
        print(e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
