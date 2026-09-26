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

ROOT = Path(__file__).resolve().parent.parent
DEFAULT = ROOT / "ext" / "uade" / "amigasrc" / "players"
TEXT_EXT = {".s", ".asm", ".a", ".i", ".c", ".h", ".txt", ".readme", ".doc"}


def main(argv):
    flags = 0
    code_only = False
    while argv and argv[0].startswith("-") and len(argv[0]) == 2:
        opt = argv.pop(0)
        if opt == "-i":
            flags |= re.IGNORECASE
        elif opt == "-c":
            code_only = True
        else:
            sys.exit(__doc__)
    if not argv:
        sys.exit(__doc__)
    pattern = re.compile(argv[0], flags)
    paths = [Path(p) for p in argv[1:]] or [DEFAULT]
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
