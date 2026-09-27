#!/usr/bin/env python3
"""Check the player specs in specs/ and the hardware model in hardware/.

Usage: specs.py [DIR]

DIR defaults to specs/, checked with hardware/. Checks:
  - `mypy --strict` passes; a body of `...` is a stub, so empty-body is
    off. Ruff runs as its own pre-commit hook.
  - each spec is named by a player's `spec` in data/players.yaml, except
    the shared ones in SHARED
  - each top-level CamelCase function in a player's spec is a label, and
    each CamelCase class is a type, in data/annot/<player>.yaml (see
    tools/annot.py); functions may also be labels in
    data/disasm/<player>.cnf
  - snake_case helpers need no label

Prints `file:line: rule: detail` for each problem; exits 1 if any.
"""

import ast
import re
import sys
from pathlib import Path

import annot
import players
from mypy import api as mypy_api

ROOT = Path(__file__).resolve().parent.parent
SPECS = ROOT / "specs"
HARDWARE = ROOT / "hardware"
SHARED = {"__init__.py", "controls.py"}
CAMEL = re.compile(r"[A-Z][A-Za-z0-9]*[a-z][A-Za-z0-9]*")
MYPY_LINE = re.compile(r"^(.+?):(\d+): error: (.*)$")


def anchors(player):
    """(labels, types) a player's spec may use."""
    labels, types = set(), set()
    path = ROOT / "data/annot" / f"{player}.yaml"
    if path.is_file():
        labels = annot.listing_labels(path)
        types = set(annot.load(path).get("types") or {})
    cnf = ROOT / "data/disasm" / f"{player}.cnf"
    if cnf.is_file():
        labels |= annot.cited_labels(cnf)
    return labels - types, types


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
        for n, rule, detail in check_names(path, player):
            errors.append(f"{rel}:{n}: {rule}: {detail}")
    for e in errors:
        print(e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
