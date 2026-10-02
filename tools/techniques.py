#!/usr/bin/env python3
"""Paula techniques: the "Seen in" lists come from the cards' links.

Usage: techniques.py [--write | --check]

  (no option)  print docs/paula-techniques.md with its lists rebuilt
  --write      write docs/paula-techniques.md
  --check      exit 1 if a list is out of date, or a card links a
               technique that has no `##` section

A card that links `paula-techniques.md#<anchor>` uses that technique. Each
`##` section of the page ends in one paragraph, "Seen in:", that links
those cards by their titles. A section that no card links has none.
"""

# mypy: disallow-untyped-defs

import sys
from pathlib import Path

import cli
from links import links
from mdtools import Doc, plain, read, slug, wrap

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "docs" / "paula-techniques.md"
CARDS = ROOT / "players"
LEAD = "Seen in:"


def title(doc: Doc) -> str:
    """A card's `#` title."""
    tokens = doc.tokens
    return next(
        plain(tokens[i + 1])
        for i, t in enumerate(tokens)
        if t.type == "heading_open" and t.tag == "h1"
    )


def users(page: Path, cards: Path) -> dict[str, list[tuple[str, str]]]:
    """{anchor: [(title, card path)]} for each card that links page#anchor."""
    found: dict[str, list[tuple[str, str]]] = {}
    for card in sorted(cards.glob("*.md")):
        doc = read(card)
        for _, href in links(doc):
            file, _, anchor = str(href).partition("#")
            if anchor and file and (card.parent / file).resolve() == page.resolve():
                entry = (title(doc), card.name)
                if entry not in found.setdefault(anchor, []):
                    found[anchor].append(entry)
    return found


def rebuild(page: Path, cards: Path) -> tuple[str, list[str]]:
    """The page with its lists rebuilt, and the anchors no section has."""
    doc = read(page)
    lines = page.read_text(encoding="utf-8").split("\n")
    tokens = doc.tokens
    rel = Path("..") / cards.relative_to(page.parent.parent)
    starts = [
        (t.map[0], slug(plain(tokens[i + 1])))
        for i, t in enumerate(tokens)
        if t.type == "heading_open" and t.tag == "h2" and t.map
    ]
    old = [
        range(t.map[0], t.map[1])
        for i, t in enumerate(tokens)
        if t.type == "paragraph_open"
        and t.map
        and plain(tokens[i + 1]).startswith(LEAD)
    ]
    drop = {n for span in old for n in span}
    used = users(page, cards)
    ends = [start for start, _ in starts[1:]] + [len(lines)]
    out: list[str] = lines[: starts[0][0]] if starts else lines
    for (start, anchor), end in zip(starts, ends):
        body = [lines[n] for n in range(start, end) if n not in drop]
        while body and not body[-1]:
            body.pop()
        out += body
        if anchor in used:
            names = [f"[{name}]({rel / file})" for name, file in sorted(used[anchor])]
            out += ["", wrap(f"{LEAD} {', '.join(names)}.")]
        out.append("")
    text = "\n".join(out).rstrip("\n") + "\n"
    missing = sorted(set(used) - {anchor for _, anchor in starts})
    return text, missing


def main(argv: list[str]) -> int:
    parser = cli.parser(__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    text, missing = rebuild(PAGE, CARDS)
    rel = PAGE.relative_to(ROOT)
    for anchor in missing:
        print(f"{rel}:1: technique: a card links #{anchor}, which no section has")
    if args.write:
        PAGE.write_text(text, encoding="utf-8")
    elif args.check:
        if text != PAGE.read_text(encoding="utf-8"):
            print(f"{rel}:1: seen-in: out of date; run tools/techniques.py --write")
            return 1
    else:
        print(text, end="")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
