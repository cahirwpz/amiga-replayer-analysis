#!/usr/bin/env python3
"""Search replayer sources. Use this instead of grep.

Usage: srcgrep.py [-i] [-c] PATTERN [PATH...]

Replayer sources are Latin-1, and grep in a UTF-8 locale silently finds
nothing in them. This tool decodes every file as Latin-1.

  -i  ignore case
  -c  skip matches inside ';' comments
PATH defaults to ext/uade/amigasrc/players. Prints `path:line: text`.
"""

import re
import sys
from pathlib import Path

import cli

ROOT = Path(__file__).resolve().parent.parent
DEFAULT = ROOT / "ext" / "uade" / "amigasrc" / "players"
TEXT_EXT = {".s", ".asm", ".a", ".i", ".c", ".h", ".txt", ".readme", ".doc"}


def main(argv):
    parser = cli.parser(__doc__)
    parser.add_argument("-i", action="store_true")
    parser.add_argument("-c", action="store_true")
    parser.add_argument("pattern")
    parser.add_argument("paths", nargs="*", type=Path)
    args = parser.parse_args(argv)
    pattern = re.compile(args.pattern, re.IGNORECASE if args.i else 0)
    code_only = args.c
    paths = args.paths or [DEFAULT]
    found = False
    for base in paths:
        files = sorted(base.rglob("*")) if base.is_dir() else [base]
        for f in files:
            if not f.is_file() or ".git" in f.parts:
                continue
            if f.suffix.lower() not in TEXT_EXT and f.suffix:
                continue
            text = f.read_bytes().decode("latin-1")
            for n, line in enumerate(text.splitlines(), start=1):
                hay = line.split(";")[0] if code_only else line
                if pattern.search(hay):
                    found = True
                    print(f"{f}:{n}: {line.rstrip()}")
    return 0 if found else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
