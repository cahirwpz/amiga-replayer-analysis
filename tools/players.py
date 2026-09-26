#!/usr/bin/env python3
"""Per-player facts: data/players.yaml is the source.

Usage: players.py [--write | --check]

  --write  write the generated tables in docs/players.md and ext/README.md
  --check  exit 1 if data/players.yaml is invalid or a table is stale

Other tools import this module:
  load()        {player: facts}, as written in data/players.yaml
  validate()    problems in the file, as text; takes other data for tests
"""

import csv
import sys
from functools import cache
from pathlib import Path

import glossary
import yaml
from mdtools import block, format_table, replace_block

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "data" / "players.yaml"
DOC = ROOT / "docs" / "players.md"
EXT_README = ROOT / "ext" / "README.md"
BINARIES = ROOT / "ext" / "uade" / "players"
INVENTORY = ROOT / "data" / "inventory.csv"
CARDS = ROOT / "players"

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
}
REPLAY = {"uade", "module", "check", "port", "disasm"}


@cache
def load():
    return yaml.safe_load(SOURCE.read_text(encoding="utf-8")) or {}


def validate(data=None):
    data = load() if data is None else data
    binaries = {p.name for p in BINARIES.iterdir() if p.is_file()}
    provenance = glossary.words("provenance")
    evidence = glossary.words("lineage_evidence")
    errors = []

    def err(player, detail):
        errors.append(f"{SOURCE.relative_to(ROOT)}: {player}: {detail}")

    for player, facts in data.items():
        if player not in binaries:
            err(player, "not a binary in ext/uade/players")
        if not isinstance(facts, dict):
            err(player, "facts must be a mapping")
            continue
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
            if "player" in link and link["player"] not in binaries:
                err(player, f"`{link['player']}` is not a binary")
        for port in facts.get("ports") or []:
            if not str(port).startswith("ext/") or not (ROOT / str(port)).exists():
                err(player, f"port `{port}` is not a path under ext/")
        for name in facts.get("related") or []:
            if name not in binaries:
                err(player, f"related `{name}` is not a binary")
        after = facts.get("after") or {}
        if after and "family" not in facts:
            err(player, "`after` needs `family`")
        before = data.get(after.get("player"), {})
        if after.get("player") and before.get("family") != facts.get("family"):
            err(player, "`after` must name a player of the same family")
    return errors


@cache
def inventory():
    """{player: (row number, CSV row)} from data/inventory.csv."""
    with INVENTORY.open(encoding="utf-8") as f:
        return {r["player"]: (n, r) for n, r in enumerate(csv.DictReader(f), start=2)}


def row_links():
    """{player: Markdown link to its inventory row}, relative to docs/ or ext/."""
    rows = {p: n for p, (n, _) in inventory().items()}
    return {
        p: f'[`{p}`](../data/inventory.csv?plain=1#L{n} "{p}")' for p, n in rows.items()
    }


def card_link(player):
    if (CARDS / f"{player}.md").is_file():
        return f"[card](../players/{player}.md)"
    return ""


def families():
    """{family: [players]}, oldest first where `after` says so."""
    out = {}
    for player, facts in load().items():
        if "family" in facts:
            out.setdefault(facts["family"], []).append(player)
    for family, members in out.items():
        ordered = []

        def place(p):
            if p in ordered:
                return
            before = load()[p].get("after", {}).get("player")
            if before in members:
                place(before)
            ordered.append(p)

        for p in members:
            place(p)
        out[family] = ordered
    return out


def evidence_text(link):
    text = link.get("evidence", "")
    if link.get("why"):
        text += f": {link['why']}"
    if link.get("cite"):
        text += f", `{link['cite']}`"
    return text


def blocks():
    data, rows = load(), row_links()

    cards = []
    for player in sorted(data, key=str.lower):
        facts = data[player]
        if not card_link(player):
            continue
        prov = facts.get("provenance", "")
        if prov and facts.get("provenance_guess"):
            prov += " (guess)"
        who = ", ".join(str(facts[k]) for k in ("author", "year", "game") if k in facts)
        links = " ".join(f"[page]({url})" for url in facts.get("links", []))
        cards.append([rows[player], card_link(player), prov, who, links])

    shared, distinct, history = [], [], []
    for family, members in families().items():
        core = [p for p in members if "distinct" not in data[p]]
        heads = [p for p in core if data[p].get("head")]
        head = heads[0] if heads else ""
        card = f"`{head}` {card_link(head)}".strip() if head else "open"
        evidence = "; ".join(
            evidence_text(data[p]["after"]) for p in core if data[p].get("after")
        )
        shared.append([family, ", ".join(rows[p] for p in core), card, evidence or "—"])
        for p in members:
            if "distinct" in data[p]:
                distinct.append([rows[p], family, data[p]["distinct"]])
    for player, facts in data.items():
        for link in facts.get("influences", []):
            source = rows[link["player"]] if "player" in link else link["name"]
            page = f"[page]({link['link']})" if "link" in link else ""
            history.append(
                [source, rows[player], f"{link['evidence']}: {page}".strip(": ")]
            )

    ports = []
    for player in sorted(data, key=str.lower):
        _, row = inventory()[player]
        source = row["source"]
        for port in data[player].get("ports", []):
            use = "possible source" if row["replay"] == "module" else "cross-check"
            ports.append([rows[player], f"`{port}`", use])
        if source.startswith("ext/"):
            ports.append([rows[player], f"`{source}`", "source"])

    return {
        "ports": format_table(["Player", "Port", "Use"], ports),
        "cards": format_table(
            ["Player", "Card", "Provenance", "Who, when, where", "Links"], cards
        ),
        "lineages": format_table(["Lineage", "Versions", "Card", "Evidence"], shared),
        "distinct": format_table(["Player", "Lineage", "Distinct idea"], distinct),
        "history": format_table(["Older program", "Player", "Evidence"], history),
    }


# Page -> names of the generated blocks it holds.
PAGES = {DOC: ["cards", "lineages", "distinct", "history"], EXT_README: ["ports"]}


def main(argv):
    if argv not in (["--write"], ["--check"]):
        sys.exit(__doc__)
    errors = validate()
    tables = blocks()
    for page, names in PAGES.items():
        text = page.read_text(encoding="utf-8")
        new = text
        for name in names:
            new = replace_block(new, name, block(name, tables[name]))
        if argv == ["--write"]:
            page.write_text(new, encoding="utf-8")
        elif new != text:
            errors.append(f"{page.relative_to(ROOT)}: out of date; run --write")
    for e in errors:
        print(e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
