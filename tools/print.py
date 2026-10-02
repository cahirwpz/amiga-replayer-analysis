#!/usr/bin/env python3
"""Print player cards as text, and check that each fits its pages.

Usage: print.py [--check | --pdf OUT.pdf] FILE.md|DIR...

  (no option)  print each card as the text that goes on paper
  --check      exit 1 if a card needs more than PAGES pages
  --pdf        write the cards as one PDF: A4 portrait, each card from a
               new page

The paper: A4 portrait, JetBrains Mono at FONT_SIZE. The columns and the
lines per page follow from the page, the margins and the font's advance
width. A card may fill PAGES pages: one sheet, printed on both sides.

Text leaves out the front matter. Headings print in bold, code spans without their
backticks, labels without their leading colon, links as their text and
an arrow (↗). The PDF sets code spans in italics and underlines link text;
neither breaks across lines. The PDF prints the title at twice the size
and headings at 1.4 (`##`) and 1.2 times (`###`); each still counts as
one line. Tables get columns wide enough for
their cells, then the widest columns shrink until the table fits; cells
wrap inside their column.

The PDF embeds the font from .venv/share/fonts/; `source ./activate`
fetches it (setup/Makefile). The check needs no font.
"""

# mypy: disallow-untyped-defs

import math
import re
import sys
from typing import TYPE_CHECKING
from pathlib import Path

import cli
from markdown_it.token import Token

if TYPE_CHECKING:
    from fpdf import FPDF
from mdtools import children, read

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / ".venv" / "share" / "fonts"

FONT_SIZE = 10.0  # points
PAGES = 2  # pages per card: both sides of one sheet
SHEET = (210.0, 297.0)  # A4 portrait, mm
MARGIN = 10.0  # mm, around the page
ADVANCE = 0.6  # JetBrains Mono's advance width, in em
LEADING = 1.2  # line height, in font sizes
PT = 25.4 / 72  # mm per point

PAGE_WIDTH = SHEET[0] - 2 * MARGIN
COLUMNS = int(PAGE_WIDTH / (FONT_SIZE * ADVANCE * PT))
LINE_HEIGHT = FONT_SIZE * LEADING * PT  # mm
LINES = int((SHEET[1] - 2 * MARGIN) / LINE_HEIGHT)  # per page

GAP = "  "  # between table columns

Line = tuple[str, int]  # text with marks, weight

# Weights. The PDF prints a heading larger; text counts it as one line.
PLAIN, BOLD, SUBSECTION, SECTION, TITLE = 0, 1, 2, 3, 4
SCALE = {SUBSECTION: 1.2, SECTION: 1.4, TITLE: 2.0}  # font size, in FONT_SIZE
# Baseline shift, in lines: the title also fills the blank line below it.
SHIFT = {SUBSECTION: 0.1, SECTION: 0.25, TITLE: 0.6}

# Link text and code spans sit between these marks; a link's arrow follows
# it. Their spaces become no-break spaces, so wrapping keeps them whole.
OPEN, CLOSE, CODE, END_CODE = "\x01", "\x02", "\x03", "\x04"
MARKS = (OPEN, CLOSE, CODE, END_CODE)
ARROW, NBSP = "\u2197", "\u00a0"


def visible(line: str) -> int:
    """Printed width: marks take no column."""
    return len(line) - sum(line.count(mark) for mark in MARKS)


def plain(line: str) -> str:
    """A line as printed text, without marks."""
    for mark in MARKS:
        line = line.replace(mark, "")
    return line.replace(NBSP, " ")


def text(inline: Token) -> str:
    """Prose of an inline token, with marks: code spans without backticks,
    a label without its leading colon."""
    out = []
    link = False
    for _, child in children(inline):
        if child.type == "code_inline":
            code = child.content.removeprefix(":").replace(" ", NBSP)
            out.append(CODE + code + END_CODE)
        elif child.type in ("text", "image"):
            content = child.content
            out.append(content.replace(" ", NBSP) if link else content)
        elif child.type in ("softbreak", "hardbreak"):
            out.append(NBSP if link else " ")
        elif child.type == "link_open":
            out.append(OPEN)
            link = True
        elif child.type == "link_close":
            out.append(CLOSE + ARROW)
            link = False
    return "".join(out).strip()


def fill(words: str, width: int, first: str = "", rest: str = "") -> list[str]:
    """Greedy wrap by printed width; a word longer than a line stays whole.
    Splits at plain spaces only, so links stay whole."""
    lines: list[str] = []
    line, empty = first, True
    for word in filter(None, words.split(" ")):
        if not empty and visible(line) + 1 + visible(word) > width:
            lines.append(line)
            line, empty = rest, True
        line += word if empty else " " + word
        empty = False
    lines.append(line.rstrip())
    return lines


def wrap(words: str, first: str = "", rest: str = "") -> list[str]:
    """Words wrapped at COLUMNS, with prefixes for the first and later lines."""
    return fill(words, COLUMNS, first, rest)


def column_widths(rows: list[list[str]]) -> list[int]:
    """Content widths, the widest shrunk one at a time to fit COLUMNS."""
    widths = [max(visible(row[c]) for row in rows) for c in range(len(rows[0]))]
    room = COLUMNS - len(GAP) * (len(widths) - 1)
    while sum(widths) > room:
        widest = widths.index(max(widths))
        widths[widest] -= 1
    return widths


def render_table(rows: list[list[str]]) -> list[Line]:
    widths = column_widths(rows)
    out: list[Line] = []
    for n, row in enumerate(rows):
        cells = [fill(cell, w) for cell, w in zip(row, widths)]
        for i in range(max(map(len, cells))):
            parts = [pad(c[i] if i < len(c) else "", w) for c, w in zip(cells, widths)]
            out.append((GAP.join(parts).rstrip(), n == 0))
        if n == 0:
            out.append((GAP.join("-" * w for w in widths), False))
    return out


def pad(cell: str, width: int) -> str:
    return cell + " " * (width - visible(cell))


def render_tokens(tokens: list[Token]) -> list[Line]:
    out: list[Line] = []
    lists: list[int | None] = []  # per open list: its item number, None if bulleted
    markers: list[str] = []  # per open list: its current item's marker
    fresh = False  # the next paragraph starts a list item
    i = 0
    while i < len(tokens):
        token = tokens[i]
        kind = token.type
        if kind == "heading_open":
            title = text(tokens[i + 1])
            weight = {"h1": TITLE, "h2": SECTION, "h3": SUBSECTION}.get(token.tag, BOLD)
            out += [("", PLAIN), (title, weight), ("", PLAIN)]
            i += 3
            continue
        if kind == "front_matter":
            i += 1
            continue
        if kind in ("bullet_list_open", "ordered_list_open"):
            lists.append(0 if kind == "ordered_list_open" else None)
            markers.append("- ")
        elif kind in ("bullet_list_close", "ordered_list_close"):
            lists.pop()
            markers.pop()
            if not lists:
                out.append(("", False))
        elif kind == "list_item_open":
            number = lists[-1]
            if number is not None:
                lists[-1] = number = number + 1
                markers[-1] = f"{number}. "
            fresh = True
        elif kind == "inline" and tokens[i - 1].type == "paragraph_open":
            indent = "".join(" " * len(m) for m in markers[:-1])
            hang = indent + " " * len(markers[-1]) if markers else ""
            if markers and fresh:
                lines = wrap(text(token), indent + markers[-1], hang)
            elif markers:
                lines = wrap(text(token), hang, hang)
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
    """Write the PDF; return its number of pages."""
    from fpdf import FPDF

    styles = {"": "Regular", "B": "Bold", "I": "Italic", "BI": "BoldItalic"}
    files = {
        style: FONTS / f"JetBrainsMono-{name}.ttf" for style, name in styles.items()
    }
    for file in files.values():
        if not file.is_file():
            sys.exit(f"{file} is missing; run: source ./activate")
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(False)
    pdf.set_margins(0, 0, 0)
    pdf.set_title("Player cards")
    for style, file in files.items():
        pdf.add_font("mono", style, str(file))
    for path in paths:
        lines = render(path)
        for row, (line, weight) in enumerate(lines):
            if row % LINES == 0:
                pdf.add_page()
            x = MARGIN
            y = (
                MARGIN
                + (row % LINES + 1) * LINE_HEIGHT
                - (LEADING - 1) * FONT_SIZE * PT
            )
            y += SHIFT.get(weight, 0) * LINE_HEIGHT
            draw(pdf, x, y, line, weight > PLAIN, FONT_SIZE * SCALE.get(weight, 1))
    out.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(out))
    return pdf.pages_count


def draw(
    pdf: "FPDF", x: float, y: float, line: str, strong: bool, size: float = FONT_SIZE
) -> None:
    """One line: code in italics, link text underlined. Monospace: each
    column is one advance."""
    link = code = False
    column = 0
    for part in re.split(f"([{''.join(MARKS)}])", line):
        if part in MARKS:
            link = {OPEN: True, CLOSE: False}.get(part, link)
            code = {CODE: True, END_CODE: False}.get(part, code)
            continue
        if part:
            style = (
                ("B" if strong else "") + ("I" if code else "") + ("U" if link else "")
            )
            pdf.set_font("mono", style, size)
            pdf.text(x + column * ADVANCE * size * PT, y, part.replace(NBSP, " "))
            column += len(part)


def main(argv: list[str]) -> int:
    parser = cli.parser(__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--pdf", type=Path)
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args(argv)
    paths, pdf = cards(args.paths), args.pdf
    if pdf:
        written = write_pdf(paths, pdf)
        print(f"wrote {pdf}: {count(len(paths), 'card')} on {count(written, 'page')}")
        return 0
    if args.check:
        errors = [
            f"{path}:1: pages: {pages(lines)} > {PAGES} ({len(lines)} lines, {LINES} per page)"
            for path in paths
            if pages(lines := render(path)) > PAGES
        ]
        print("\n".join(errors), end="\n" if errors else "")
        return 1 if errors else 0
    for path in paths:
        print("\n".join(plain(line) for line, _ in render(path)))
        print("\f", end="")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
