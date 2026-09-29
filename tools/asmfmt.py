#!/usr/bin/env python3
"""Lay out our 68k assembler files, Motorola syntax for vasm.

Usage: asmfmt.py [--check] FILE.asm...

Rewrites each file in place; with --check, only lists the files that it
would change, and exits 1 if there are any.

Each field starts at a multiple of 8 columns, with spaces, never tabs:

  label      column 0
  mnemonic   column 8, or the next multiple of 8 after a long label
  operands   the next multiple of 8 after the mnemonic, usually 16
  comment    column 32, or the next multiple of 8 after the code

A comment on a line of its own stays at column 0, or else goes to
column 8. A `;` inside quotes is not a comment. Empty lines stay empty.
Replayer sources in ext/ keep their own layout; this is for our files.
"""

import sys
from pathlib import Path

TAB = 8
COMMENT = 32


def split_comment(line):
    """(code, comment): the comment starts at the first ; outside quotes."""
    quote = None
    for i, char in enumerate(line):
        if quote:
            if char == quote:
                quote = None
        elif char in "'\"":
            quote = char
        elif char == ";":
            return line[:i].rstrip(), line[i:].rstrip()
    return line.rstrip(), ""


def column(text, at):
    """Pad text to the next multiple of TAB that is at least `at`, with at
    least one space after it."""
    width = max(at, (len(text) // TAB + 1) * TAB) if text else at
    return text.ljust(width)


def layout(line):
    code, comment = split_comment(line.expandtabs(TAB))
    if not code.strip():
        if not comment:
            return ""
        return comment if line[:1] == ";" else " " * TAB + comment
    label = "" if code[0].isspace() else code.split()[0]
    rest = code[len(label) :].strip()
    mnemonic, _, operands = rest.partition(" ")
    out = label
    if mnemonic:
        out = column(out, TAB) + mnemonic
    if operands.strip():
        out = column(out, 2 * TAB) + operands.strip()
    if comment:
        out = column(out, COMMENT) + comment
    return out.rstrip()


def format_text(text):
    return "".join(layout(line) + "\n" for line in text.splitlines())


def main(argv):
    check = argv[:1] == ["--check"]
    files = argv[1:] if check else argv
    if not files:
        sys.exit(__doc__)
    changed = []
    for name in files:
        path = Path(name)
        text = path.read_text("latin-1")
        new = format_text(text)
        if new != text:
            changed.append(name)
            if not check:
                path.write_text(new, "latin-1")
    for name in changed:
        print(f"{name}: {'would be ' if check else ''}reformatted")
    return 1 if changed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
