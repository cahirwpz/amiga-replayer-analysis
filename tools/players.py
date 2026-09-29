#!/usr/bin/env python3
"""Per-player facts: data/players.yaml is the source.

Usage: players.py --check

  --check  exit 1 if data/players.yaml is invalid

Other tools import this module:
  load()        {player: facts}, as written in data/players.yaml
  modules()     {path: facts}, as written in data/modules.yaml
  binaries()    names of the player binaries in ext/uade/players
  validate()    problems in the file, as text; takes other data for tests
"""

import sys
from functools import cache
from pathlib import Path

import annot
import glossary
import yaml

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "data" / "players.yaml"
MODULES = ROOT / "data" / "modules.yaml"
BINARIES = ROOT / "ext" / "uade" / "players"
SOURCES = ROOT / "ext" / "uade" / "amigasrc" / "players"

FIELDS = {
    "source": str,
    "replay": str,
    "note": str,
    "provenance": str,
    "provenance_guess": bool,
    "author": str,
    "year": int,
    "game": str,
    "family": str,
    "after": dict,
    "head": bool,
    "distinct": str,
    "influences": list,
    "ports": list,
    "related": list,
    "links": list,
    "spec": str,
    "module": str,
    "skip": str,
    "covered_by": list,
}
REPLAY = {"uade", "module", "check", "port", "ext", "disasm", "source"}


@cache
def load():
    return yaml.safe_load(SOURCE.read_text(encoding="utf-8")) or {}


@cache
def modules():
    return yaml.safe_load(MODULES.read_text(encoding="utf-8")) or {}


def binaries():
    return {p.name for p in BINARIES.iterdir() if p.is_file()}


def validate(data=None):
    data = load() if data is None else data
    binaries_ = binaries()
    provenance = glossary.words("provenance")
    evidence = glossary.words("lineage_evidence")
    reasons = glossary.words("skip_reasons")
    errors = []

    def err(player, detail):
        errors.append(f"{SOURCE.relative_to(ROOT)}: {player}: {detail}")

    for player, facts in data.items():
        if not isinstance(facts, dict):
            err(player, "facts must be a mapping")
            continue
        if facts.get("replay") == "source":
            # Original source without a UADE binary, e.g. MaxTrax.
            src = str(facts.get("source", ""))
            base = ROOT if src.startswith("ext/") else SOURCES
            if player in binaries_:
                err(player, "`replay: source` is for players without a binary")
            if not src or not (base / src).exists():
                err(player, "`replay: source` needs an existing `source`")
        elif player not in binaries_:
            err(player, "not a binary in ext/uade/players")
        for key, value in facts.items():
            if key not in FIELDS:
                err(player, f"unknown field `{key}`")
            elif not isinstance(value, FIELDS[key]):
                err(player, f"`{key}` must be {FIELDS[key].__name__}")
        if facts.get("replay", "uade") not in REPLAY:
            err(player, f"`replay` not in {sorted(REPLAY)}")
        if facts.get("provenance", "original") not in provenance:
            err(player, f"`provenance` not in {sorted(provenance)}")
        links = [facts.get("after") or {}] + list(facts.get("influences") or [])
        for link in links:
            if not isinstance(link, dict):
                continue
            if link.get("evidence", "name") not in evidence:
                err(player, f"evidence `{link['evidence']}` not in {sorted(evidence)}")
            if "player" in link and link["player"] not in binaries_:
                err(player, f"`{link['player']}` is not a binary")
        spec = str(facts.get("spec", ""))
        if spec and not (spec.startswith("specs/") and (ROOT / spec).is_file()):
            err(player, f"spec `{spec}` is not a file under specs/")
        module = str(facts.get("module", ""))
        if module and module not in modules():
            err(player, f"module `{module}` is not in data/modules.yaml")
        elif module and not (ROOT / module).is_file():
            err(player, f"module `{module}` does not exist")
        for port in facts.get("ports") or []:
            if not str(port).startswith("ext/") or not (ROOT / str(port)).exists():
                err(player, f"port `{port}` is not a path under ext/")
        for name in facts.get("related") or []:
            if name not in binaries_:
                err(player, f"related `{name}` is not a binary")
        for link in links:
            if isinstance(link, dict) and "cite" in link:
                name, _, label = str(link["cite"]).rpartition(":")
                path = ROOT / name
                if not path.is_file():
                    err(player, f"cite: {name} does not exist")
                elif label not in (annot.cited_labels(path) or ()):
                    err(player, f"cite: {path.name} has no label {label}")
        skip = facts.get("skip")
        if skip is not None and skip not in reasons:
            err(player, f"`skip` not in {sorted(reasons)}")
        if skip and (ROOT / "players" / f"{player}.md").is_file():
            err(player, "`skip` but players/ has its card")
        for key in ("distinct", "head"):
            if skip and key in facts:
                err(player, f"`skip` and `{key}` contradict each other")
        if (skip == "covered") != ("covered_by" in facts):
            err(player, "`skip: covered` and `covered_by` go together")
        for name in facts.get("covered_by") or []:
            if not (ROOT / "players" / f"{name}.md").is_file():
                err(player, f"covered_by `{name}` has no card in players/")
        if skip == "lineage" and not any(
            f.get("head") and f.get("family") == facts.get("family")
            for f in data.values()
            if isinstance(f, dict)
        ):
            err(player, "`skip: lineage` needs a family with a head")
        after = facts.get("after") or {}
        if after and "family" not in facts:
            err(player, "`after` needs `family`")
        before = data.get(after.get("player"), {})
        if after.get("player") and before.get("family") != facts.get("family"):
            err(player, "`after` must name a player of the same family")
    return errors


def main(argv):
    if argv != ["--check"]:
        sys.exit(__doc__)
    errors = validate()
    for e in errors:
        print(e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
