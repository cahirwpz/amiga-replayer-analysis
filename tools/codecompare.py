#!/usr/bin/env python3
"""Find instruction runs that two or more disassembled replays share.

Usage: codecompare.py [-n N] NAME:START-END NAME:START-END...

NAME is a listing, build/disasm/NAME.asm; write it first with
`tools/disasm.py listing NAME`. START-END is the replay's code range, in
hex, end excluded. N (default 4) is the shortest run that counts.

Each instruction is reduced to its shape: branch sizes, registers,
offsets, immediates and labels are masked. So `bne.s` and `bne.w`
match, and so do the same steps on fields at other offsets. A run is N
or more shapes in a row that also occur in a row in the other listing.

For each pair, prints how many instructions of the first listing lie
in shared runs, then each run as START-END with the label it starts
in and any labels inside it. Shared runs point to shared code; reading both
routines decides it.
"""

import re
from pathlib import Path

import cli

ROOT = Path(__file__).resolve().parent.parent
LINE = re.compile(r"\t([A-Z.]+)\t([^;]*);([0-9a-f]+):")
LABEL = re.compile(r"^(\w+):")
KEEP_SIZE = ("BSET", "BCLR", "BCHG", "BTST")


def shape(mnemonic: str, operands: str) -> str:
    """The instruction with sizes of branches and all numbers masked."""
    if mnemonic.startswith("DB"):
        mnemonic = "DBcc"
    elif mnemonic.startswith("B") and not mnemonic.startswith(KEEP_SIZE):
        mnemonic = mnemonic.split(".")[0]
    operands = re.sub(r"-?\$?\w+(?=\()", "n", operands.strip())
    operands = re.sub(r"#\$?-?[0-9a-fA-F]+", "#", operands)
    operands = re.sub(r"\b[DA][0-7]\b", "r", operands)
    operands = re.sub(r"\b(LAB_\w+|[A-Z]\w+)\b", "L", operands)
    return f"{mnemonic} {operands}"


def read(
    name: str, start: int, end: int
) -> tuple[list[tuple[str, int]], dict[int, str]]:
    """Shapes with their addresses, and the labels, of one code range."""
    code: list[tuple[str, int]] = []
    labels: dict[int, str] = {}
    pending: list[str] = []
    for line in (
        (ROOT / "build/disasm" / f"{name}.asm").read_text("latin-1").splitlines()
    ):
        if m := LABEL.match(line):
            pending.append(m.group(1))
            continue
        if not (m := LINE.match(line)):
            continue
        at = int(m.group(3), 16)
        for label in pending:
            if not label.startswith(("LAB_", "SECSTRT")):
                labels[at] = label
        pending = []
        if start <= at < end and not m.group(1).startswith(("DC", "DS")):
            code.append((shape(m.group(1), m.group(2)), at))
    return code, labels


def shared(a: list[tuple[str, int]], b: list[tuple[str, int]], n: int) -> set[int]:
    """Indexes into `a` that lie in a run of n shapes also found in `b`."""
    runs = {tuple(s for s, _ in b[i : i + n]) for i in range(len(b) - n + 1)}
    found: set[int] = set()
    for i in range(len(a) - n + 1):
        if tuple(s for s, _ in a[i : i + n]) in runs:
            found.update(range(i, i + n))
    return found


def report(
    first: str,
    second: str,
    a: list[tuple[str, int]],
    labels: dict[int, str],
    found: set[int],
) -> None:
    print(f"{first} / {second}: {len(found)} of {len(a)} instructions of {first}")
    run: list[int] = []
    for i in sorted(found) + [-2]:
        if run and i != run[-1] + 1:
            lo, hi = a[run[0]][1], a[run[-1]][1]
            before = [x for x in sorted(labels) if x <= lo][-1:]
            names = [labels[x] for x in sorted(labels) if x in before or lo < x <= hi]
            print(f"  {lo:x}-{hi:x}", " ".join(names))
            run = []
        run.append(i)


def main() -> None:
    parser = cli.parser(__doc__)
    parser.add_argument("-n", type=int, default=4)
    parser.add_argument("ranges", nargs="+", metavar="NAME:START-END")
    args = parser.parse_args()
    listings = []
    for item in args.ranges:
        name, span = item.split(":")
        start, end = (int(x, 16) for x in span.split("-"))
        listings.append((name, *read(name, start, end)))
    for i, (first, a, labels) in enumerate(listings):
        for second, b, _ in listings[i + 1 :]:
            report(first, second, a, labels, shared(a, b, args.n))


if __name__ == "__main__":
    main()
