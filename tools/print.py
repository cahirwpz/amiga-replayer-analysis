#!/usr/bin/env python3
"""Print player cards as 80-column text, and check that each fits its pages.

Usage: print.py [--check] [--pdf OUT.pdf] FILE.md|DIR...

  (no option)  print each card as the text that goes on paper
  --check      exit 1 if a card needs more than PAGES pages
  --pdf        write the cards as one PDF: A4 landscape, two pages per
               side, each card from a new side

The paper: an A4 sheet in landscape holds two pages side by side, each 80
columns wide in JetBrains Mono. The font size and the lines per page follow
from the sheet, the margins and the font's advance width. A card may fill
one side: PAGES pages.

Text leaves out the front matter and the Context section, which
tools/cards.py generates. Headings print in bold, code spans without their
backticks, links as their text. Tables get columns wide enough for their
cells, then the widest columns shrink until the table fits 80 columns;
cells wrap inside their column.

The PDF embeds the font from .venv/share/fonts/; `source ./activate`
fetches it (setup/Makefile). The check needs no font.
"""

# mypy: disallow-untyped-defs

import math
import sys
import textwrap
from pathlib import Path

from markdown_it.token import Token
from mdtools import children, read

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / ".venv" / "share" / "fonts"

COLUMNS = 80
PAGES = 2  # pages per card: one side of the sheet
SHEET = (297.0, 210.0)  # A4 landscape, mm
MARGIN = 10.0  # mm, around the sheet and between the two pages
ADVANCE = 0.6  # JetBrains Mono's advance width, in em
LEADING = 1.2  # line height, in font sizes
PT = 25.4 / 72  # mm per point

PAGE_WIDTH = (SHEET[0] - 3 * MARGIN) / 2
FONT_SIZE = PAGE_WIDTH / COLUMNS / ADVANCE / PT  # points
LINE_HEIGHT = FONT_SIZE * LEADING * PT  # mm
LINES = int((SHEET[1] - 2 * MARGIN) / LINE_HEIGHT)  # per page

SKIPPED = {"Context"}  # generated sections
GAP = "  "  # between table columns

Line = tuple[str, bool]  # text, bold


def text(inline: Token) -> str:
    """Prose of an inline token: code spans without backticks."""
    out = []
    for _, child in children(inline):
        if child.type in ("text", "code_inline", "image"):
            out.append(child.content)
        elif child.type in ("softbreak", "hardbreak"):
            out.append(" ")
    return "".join(out).strip()


def wrap(words: str, first: str = "", rest: str = "") -> list[str]:
    """Words wrapped at COLUMNS, with prefixes for the first and later lines."""
    return textwrap.wrap(
        words, COLUMNS, initial_indent=first, subsequent_indent=rest
    ) or [first.rstrip()]


def column_widths(rows: list[list[str]]) -> list[int]:
    """Content widths, the widest shrunk one at a time to fit COLUMNS."""
    widths = [max(len(row[c]) for row in rows) for c in range(len(rows[0]))]
    room = COLUMNS - len(GAP) * (len(widths) - 1)
    while sum(widths) > room:
        widest = widths.index(max(widths))
        widths[widest] -= 1
    return widths


def render_table(rows: list[list[str]]) -> list[Line]:
    widths = column_widths(rows)
    out: list[Line] = []
    for n, row in enumerate(rows):
        cells = [textwrap.wrap(cell, w) or [""] for cell, w in zip(row, widths)]
        for i in range(max(map(len, cells))):
            parts = [
                (c[i] if i < len(c) else "").ljust(w) for c, w in zip(cells, widths)
            ]
            out.append((GAP.join(parts).rstrip(), n == 0))
        if n == 0:
            out.append((GAP.join("-" * w for w in widths), False))
    return out


def render_tokens(tokens: list[Token]) -> list[Line]:
    out: list[Line] = []
    depth = 0  # list nesting
    fresh = False  # the next paragraph starts a list item
    skip = False
    i = 0
    while i < len(tokens):
        token = tokens[i]
        kind = token.type
        if kind == "heading_open":
            title = text(tokens[i + 1])
            skip = token.tag == "h2" and title in SKIPPED
            if not skip:
                out += [("", False), (title, True), ("", False)]
            i += 3
            continue
        if skip or kind == "front_matter":
            i += 1
            continue
        if kind in ("bullet_list_open", "ordered_list_open"):
            depth += 1
        elif kind in ("bullet_list_close", "ordered_list_close"):
            depth -= 1
            if depth == 0:
                out.append(("", False))
        elif kind == "list_item_open":
            fresh = True
        elif kind == "inline" and tokens[i - 1].type == "paragraph_open":
            indent = "  " * max(depth - 1, 0)
            if depth and fresh:
                lines = wrap(text(token), indent + "- ", indent + "  ")
            elif depth:
                lines = wrap(text(token), indent + "  ", indent + "  ")
            else:
                lines = wrap(text(token)) + [""]
            out += [(line, False) for line in lines]
            fresh = False
        elif kind == "table_open":
            end = next(
                j for j in range(i, len(tokens)) if tokens[j].type == "table_close"
            )
            out += render_table(table_rows(tokens[i:end])) + [("", False)]
            i = end
        i += 1
    return tidy(out)


def table_rows(tokens: list[Token]) -> list[list[str]]:
    """A table's rows as text() cells. mdtools.table would turn code spans
    into its placeholder."""
    rows: list[list[str]] = []
    for j, token in enumerate(tokens):
        if token.type == "tr_open":
            rows.append([])
        elif token.type in ("th_open", "td_open"):
            rows[-1].append(text(tokens[j + 1]))
    return rows


def tidy(lines: list[Line]) -> list[Line]:
    """No blank line at either end, and never two in a row."""
    out: list[Line] = []
    for line in lines:
        if line[0] or (out and out[-1][0]):
            out.append(line)
    while out and not out[-1][0]:
        out.pop()
    return out


def render(path: Path) -> list[Line]:
    return render_tokens(read(path).tokens)


def pages(lines: list[Line]) -> int:
    return math.ceil(len(lines) / LINES)


def cards(args: list[str]) -> list[Path]:
    """Card paths: files as given, directories searched for cards."""
    paths = []
    for arg in map(Path, args):
        for path in sorted(arg.rglob("*.md")) if arg.is_dir() else [arg]:
            if read(path).meta.get("player"):
                paths.append(path)
    return paths


def count(n: int, noun: str) -> str:
    return f"{n} {noun}" + ("" if n == 1 else "s")


def write_pdf(paths: list[Path], out: Path) -> int:
    """Write the PDF; return its number of sides."""
    from fpdf import FPDF

    regular, bold = (
        FONTS / "JetBrainsMono-Regular.ttf",
        FONTS / "JetBrainsMono-Bold.ttf",
    )
    if not regular.is_file():
        sys.exit(f"{regular} is missing; run: source ./activate")
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(False)
    pdf.set_margins(0, 0, 0)
    pdf.set_title("Player cards")
    pdf.add_font("mono", "", str(regular))
    pdf.add_font("mono", "B", str(bold))
    for path in paths:
        lines = render(path)
        for side in range(0, len(lines), LINES * 2):
            pdf.add_page()
            for n, (line, strong) in enumerate(lines[side : side + LINES * 2]):
                page, row = divmod(n, LINES)
                pdf.set_font("mono", "B" if strong else "", FONT_SIZE)
                x = MARGIN + page * (PAGE_WIDTH + MARGIN)
                y = MARGIN + (row + 1) * LINE_HEIGHT - (LEADING - 1) * FONT_SIZE * PT
                pdf.text(x, y, line)
    out.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(out))
    return pdf.pages_count


def main(argv: list[str]) -> int:
    check = "--check" in argv
    argv = [a for a in argv if a != "--check"]
    pdf = None
    if "--pdf" in argv:
        k = argv.index("--pdf")
        if k + 1 >= len(argv):
            sys.exit(__doc__)
        pdf = Path(argv[k + 1])
        del argv[k : k + 2]
    paths = cards(argv)
    if pdf:
        sides = write_pdf(paths, pdf)
        print(f"wrote {pdf}: {count(len(paths), 'card')} on {count(sides, 'side')}")
        return 0
    if check:
        errors = [
            f"{path}:1: pages: {pages(lines)} > {PAGES} ({len(lines)} lines, {LINES} per page)"
            for path in paths
            if pages(lines := render(path)) > PAGES
        ]
        print("\n".join(errors), end="\n" if errors else "")
        return 1 if errors else 0
    for path in paths:
        print("\n".join(line for line, _ in render(path)))
        print("\f", end="")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
