#!/usr/bin/env python3
"""Card reviews: data/reviews/<player>.yaml records what each review read.

Usage: reviews.py [--check | --record PLAYER REVIEW FINDINGS.yaml]

  (no option)  list each card's reviews: ok, stale with the changed
               inputs, or missing
  --check      exit 1 if a review file is invalid; a stale review passes
  --record     write REVIEW for PLAYER: today's date, the git blob hash
               of each input, and the open findings in FINDINGS.yaml

Two reviews, each run by an agent in .claude/agents/ when the user asks:

  coverage  card-coverage: the card against docs/control-dimensions.md
  writing   card-review: the card against the writing rules

Each review reads the card, its spec and AGENTS.md, plus:

  coverage  docs/control-dimensions.md, docs/card-template.md,
            data/annot/<player>*.yaml, data/disasm/<player>.cnf
  writing   data/glossary.yaml, docs/card-template.md,
            docs/paula-techniques.md

A change to any input makes the review stale. Run coverage first: fixing
the card after a writing review makes both stale.

FINDINGS.yaml is the agent's list of findings, maybe empty. Each finding
is a mapping of text fields:

  coverage  dimension, finding, evidence
  writing   section, quote, rule, fix

Delete a finding once it is fixed; git keeps it. A review file:

  coverage:
    date: 2026-09-30
    inputs: {players/Fred.md: <blob hash>, ...}
    open: [{dimension: gate, finding: ..., evidence: ...}]
"""

# mypy: disallow-untyped-defs

import datetime
import hashlib
import sys
from pathlib import Path
from typing import Any

import annot
import cli
import players
import yaml
from mdtools import read

ROOT = Path(__file__).resolve().parent.parent
REVIEWS = ROOT / "data" / "reviews"
CARDS = ROOT / "players"
FIELDS = {
    "coverage": ("dimension", "finding", "evidence"),
    "writing": ("section", "quote", "rule", "fix"),
}
Review = dict[str, Any]  # one review entry: date, inputs, open

SHARED = {
    "coverage": ["AGENTS.md", "docs/control-dimensions.md", "docs/card-template.md"],
    "writing": [
        "AGENTS.md",
        "data/glossary.yaml",
        "docs/card-template.md",
        "docs/paula-techniques.md",
    ],
}


def blob_hash(path: Path) -> str:
    """The hash `git hash-object` prints for the file."""
    data = path.read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def cards() -> dict[str, Path]:
    """{player: card path}, for each card with a `player` key."""
    found: dict[str, Path] = {}
    for path in sorted(CARDS.glob("*.md")):
        player = read(path).meta.get("player")
        if player:
            found[player] = path
    return found


def inputs(player: str, review: str, card: Path) -> list[str]:
    """Repo-relative paths that the review reads, in a fixed order."""
    paths = [card]
    spec = players.load().get(player, {}).get("spec")
    if spec:
        paths.append(ROOT / spec)
    paths += [ROOT / p for p in SHARED[review]]
    if review == "coverage":
        paths += annot.player_files(player)
        cnf = ROOT / "data" / "disasm" / f"{player}.cnf"
        if cnf.is_file():
            paths.append(cnf)
    return [p.relative_to(ROOT).as_posix() for p in paths]


def load(player: str) -> Any:
    path = REVIEWS / f"{player}.yaml"
    if not path.is_file():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def validate(player: str, data: Any) -> list[str]:
    """Problems in one review file, as text."""
    if not isinstance(data, dict):
        return ["not a mapping"]
    problems = []
    for review, entry in data.items():
        if review not in FIELDS:
            problems.append(f"unknown review `{review}`")
            continue
        if not isinstance(entry, dict) or set(entry) != {"date", "inputs", "open"}:
            problems.append(f"{review}: needs exactly date, inputs, open")
            continue
        if not isinstance(entry["inputs"], dict):
            problems.append(f"{review}: inputs is not a mapping")
        problems += [f"{review}: {p}" for p in check_findings(review, entry["open"])]
    return problems


def check_findings(review: str, findings: Any) -> list[str]:
    if not isinstance(findings, list):
        return ["findings are not a list"]
    problems = []
    for n, finding in enumerate(findings, 1):
        if not isinstance(finding, dict) or set(finding) != set(FIELDS[review]):
            problems.append(f"finding {n}: needs exactly {', '.join(FIELDS[review])}")
        elif not all(isinstance(v, str) and v for v in finding.values()):
            problems.append(f"finding {n}: a field is empty or not text")
    return problems


def status(player: str, review: str, card: Path, entry: Review | None) -> str:
    """'ok', 'missing', or 'stale: <changed inputs>'."""
    if not entry:
        return "missing"
    wanted = inputs(player, review, card)
    recorded = entry["inputs"]
    changed = [
        p
        for p in wanted
        if p not in recorded
        or not (ROOT / p).is_file()
        or blob_hash(ROOT / p) != recorded[p]
    ]
    changed += sorted(set(recorded) - set(wanted))
    return f"stale: {', '.join(changed)}" if changed else "ok"


def record(player: str, review: str, findings_path: str | Path) -> None:
    card = cards().get(player)
    if card is None:
        sys.exit(f"no card for player `{player}`")
    if review not in FIELDS:
        sys.exit(f"unknown review `{review}`; use {' or '.join(FIELDS)}")
    findings = yaml.safe_load(Path(findings_path).read_text(encoding="utf-8")) or []
    problems = check_findings(review, findings)
    if problems:
        sys.exit("\n".join(f"{findings_path}: {p}" for p in problems))
    data = load(player)
    data[review] = {
        "date": datetime.date.today(),
        "inputs": {p: blob_hash(ROOT / p) for p in inputs(player, review, card)},
        "open": findings,
    }
    REVIEWS.mkdir(exist_ok=True)
    out = REVIEWS / f"{player}.yaml"
    out.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
    print(f"wrote {out.relative_to(ROOT)}")


def main(argv: list[str]) -> int:
    parser = cli.parser(__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--record", nargs=3, metavar=("PLAYER", "REVIEW", "FINDINGS"))
    args = parser.parse_args(argv)
    if args.record:
        record(*args.record)
        return 0
    if args.check:
        errors = [
            f"{path.relative_to(ROOT)}: {p}"
            for path in sorted(REVIEWS.glob("*.yaml"))
            for p in validate(path.stem, load(path.stem))
        ]
        errors += [
            f"data/reviews/{path.stem}.yaml: no card for this player"
            for path in sorted(REVIEWS.glob("*.yaml"))
            if path.stem not in cards()
        ]
        print("\n".join(errors), end="\n" if errors else "")
        return 1 if errors else 0
    for player, card in cards().items():
        data = load(player)
        for review in FIELDS:
            entry = data.get(review)
            opened = f", {len(entry['open'])} open" if entry else ""
            print(f"{player}: {review}: {status(player, review, card, entry)}{opened}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
