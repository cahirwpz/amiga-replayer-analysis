#!/usr/bin/env python3
"""Time replay code on an emulated Amiga 500 with vAmiga.

Usage: timing.py run NAME
       timing.py check NAME

  run      print the measured CCK of every span, case and load
  check    compare them with `expect` in the data file; exit 1 on a
           difference

NAME is a data file, data/timing/NAME.yaml. Its sections:

  code       what runs, cut from the replay's source
    source   the replay's annotation, data/annot/PLAYER.yaml; labels are
             its new names
    take     label ranges [FROM, TO] of the source, TO excluded. TO
             becomes a label at the range's end
    entry    the label that the boot code calls
  harness    what changes so the code runs alone
    drop     source lines to leave out; whitespace and comments do not
             count
    stop     labels that end a `take` range; `illegal` follows each, so
             code that reaches one stops the run
  measure    where the clock is read
    points   breakpoints: LABEL or LABEL+OFFSET or LABEL-OFFSET
    spans    NAME: [FROM, TO], two points. The span is the CPU time
             between them, in CCK
    spec     CONSTANT: [CASE, LOAD]; the spec specs/NAME.py holds the
             span CONSTANT as measured there. tests/ check it
  memory     NAME: {layout, at}: an array of records. `layout` is a type
             in the annotation's `layouts`; record N is at AT + N * size
  cases      NAME: {writes, expect}, done before the call. A write is
             "NAME[N].FIELD VALUE", a field of a `memory` record, or
             "ADDRESS SIZE VALUE" with SIZE b, w or l. A nested list,
             e.g. a YAML alias, adds its writes in place. `expect` holds
             the spans per load
  loads      optional; NAME: BITPLANES, the low-resolution bitplanes
             fetched during the call. Default: no display and 6
             bitplanes, which take the most bus slots from the CPU

The excerpt is assembled with vasm at $10000 in chip RAM, as a replay
runs. tools/timing/boot.asm is the boot ROM: it copies the excerpt, does
the writes, sets up the load, waits for line $50 and calls the entry.
Nothing generated is kept outside build/.
"""

# mypy: disallow-untyped-defs

import re
import struct
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import annot  # noqa: E402
import cli  # noqa: E402
from hardware.clock import CPU_PER_CCK  # noqa: E402

DATA = ROOT / "data" / "timing"
BUILD = ROOT / "build"
BIN = ROOT / ".venv" / "bin"
DRIVER = BIN / "amiga-timing"
VASM = BIN / "vasmm68k_mot"
EXCERPT_AT = 0x10000
START_LINE = 0x50  # inside the display window of every load

BOOT = ROOT / "tools" / "timing" / "boot.asm"
LOADS = {"no display": 0, "6 bitplanes": 6}  # without `loads` in the data file

Data = dict[str, Any]  # a data file, as loaded
Memory = dict[str, tuple[str, int, dict[str, tuple[int, int]]]]
Results = dict[str, dict[str, dict[str, float]]]  # {case: {load: {span: CCK}}}


def run_or_exit(*args: object) -> str:
    proc = subprocess.run([str(a) for a in args], capture_output=True, text=True)
    if proc.returncode:
        sys.exit(f"{' '.join(map(str, args[:2]))} failed:\n{proc.stdout}{proc.stderr}")
    return proc.stdout


def labels(lines: list[str]) -> dict[str, int]:
    """{label: index of its first line}: a label starts in column 1."""
    found = [
        (m[0], i) for i, line in enumerate(lines) if (m := re.match(annot.IDENT, line))
    ]
    return dict(reversed(found))


def source_lines(source: str) -> list[str]:
    """The lines of an annotation's rendered listing."""
    path = ROOT / source
    if problems := annot.process(path, write=False):
        sys.exit("\n".join(problems))
    spec = annot.load(path)
    return annot.render(spec, annot.source_lines(spec))


def code(line: str) -> str:
    """The code of an assembler line, whitespace normalised."""
    return " ".join(annot.code_part(line)[0].split())


def excerpt(data: Data) -> str:
    """The assembler text: the taken ranges of the source, at EXCERPT_AT."""
    lines = source_lines(data["code"]["source"])
    where = labels(lines)
    harness = data.get("harness", {})
    drop = {code(d) for d in harness.get("drop", [])}
    stop = set(harness.get("stop", []))
    out = [f" org ${EXCERPT_AT:x}"]
    for first, end in data["code"]["take"]:
        out += [
            line for line in lines[where[first] : where[end]] if code(line) not in drop
        ]
        out.append(f"{end}:")
        if end in stop:
            out.append(" illegal")
    return "\n".join(out) + "\n"


def assemble(work: Path, name: str, source: Path, **defines: int) -> dict[str, int]:
    """Assemble source with work in the include path, into work/NAME.bin.
    Return the symbols of its listing."""
    run_or_exit(
        VASM, "-quiet", "-Fbin", "-I", work,
        *(f"-D{key}={value}" for key, value in defines.items()),
        "-L", work / f"{name}.lst", "-o", work / f"{name}.bin", source,
    )  # fmt: skip
    listing = (work / f"{name}.lst").read_text("latin-1")
    return {
        m[1]: int(m[2], 16)
        for m in re.finditer(r"^(\w+)\s+A:([0-9A-F]{8})$", listing, re.M)
    }


def address(expr: str, symbols: dict[str, int]) -> int:
    """A number, LABEL, LABEL+OFFSET or LABEL-OFFSET; numbers in Python
    syntax."""
    m = re.fullmatch(r"(\w+)\s*(?:([+-])\s*(\w+))?", expr.strip())
    if not m:
        raise ValueError(f"bad address: {expr}")
    value = int(m[1], 0) if m[1][0].isdigit() else symbols[m[1]]
    if m[2]:
        value += int(m[3], 0) * (1 if m[2] == "+" else -1)
    return value


def records(data: Data) -> Memory:
    """{NAME: (base expression, record size, {field: (offset, size)})} of
    the `memory` section, with layouts from the annotation."""
    memory = data.get("memory", {})
    if not memory:
        return {}
    spec = annot.load(ROOT / data["code"]["source"])
    return {
        name: (str(place["at"]), *annot.layout(spec, place["layout"]))
        for name, place in memory.items()
    }


def write(item: str, symbols: dict[str, int], memory: Memory) -> tuple[int, int, int]:
    """(address, size, value) of one write."""
    m = re.fullmatch(r"(\w+)\[(\w+)\]\.([\w.]+)\s+(\S+)", item.strip())
    if not m:
        target, kind, value = item.split()
        return address(target, symbols), annot.SIZES[kind], int(value, 0)
    name, index, field, value = m.groups()
    base, record, fields = memory[name]
    offset, size = fields[field]
    return address(base, symbols) + int(index, 0) * record + offset, size, int(value, 0)


def writes(case: dict[str, Any], symbols: dict[str, int], memory: Memory) -> bytes:
    """The writes.bin table of boot.asm. A nested list, e.g. a YAML alias,
    adds its writes in place."""
    items = [
        j for i in case.get("writes", []) for j in (i if isinstance(i, list) else [i])
    ]
    table = struct.pack(">H", len(items))
    for item in items:
        target, size, value = write(item, symbols, memory)
        table += struct.pack(">LHL", target, size, value & 0xFFFFFFFF)
    return table


def measure(name: str) -> tuple[Data, Results]:
    """The data file and its results. Files go to build/timing/NAME."""
    if not DRIVER.exists():
        sys.exit("amiga-timing missing; run: source ./activate")
    data = yaml.safe_load((DATA / f"{name}.yaml").read_text())
    section = data["measure"]
    work = BUILD / "timing" / name
    work.mkdir(parents=True, exist_ok=True)
    (work / "excerpt.asm").write_text(excerpt(data), "latin-1")
    symbols = assemble(work, "excerpt", work / "excerpt.asm")
    memory = records(data)
    points = {p: address(expr, symbols) for p, expr in section["points"].items()}
    results: Results = {}
    for case_name, case in data["cases"].items():
        (work / "writes.bin").write_bytes(writes(case, symbols, memory))
        for load, bitplanes in data.get("loads", LOADS).items():
            assemble(
                work, "boot", BOOT, EXCERPT_AT=EXCERPT_AT, ENTRY=symbols[data["code"]["entry"]],
                START_LINE=START_LINE, BITPLANES=bitplanes,
            )  # fmt: skip
            out = run_or_exit(
                DRIVER, work / "boot.bin", *(f"{a:x}" for a in points.values())
            )
            clock = {
                int(a, 16): int(c)
                for a, c in (line.split() for line in out.splitlines())
            }
            spans = {
                span: (clock[points[b]] - clock[points[a]]) / CPU_PER_CCK
                for span, (a, b) in section["spans"].items()
            }
            results.setdefault(case_name, {})[load] = spans
    return data, results


def cck(value: float) -> int | float:
    """A span as written in the data file: whole CCK as an int."""
    return int(value) if value == int(value) else value


def run(name: str) -> int:
    _, results = measure(name)
    for case, loads in results.items():
        for load, spans in loads.items():
            cells = ", ".join(f"{s} {cck(v)}" for s, v in spans.items())
            print(f"{case} | {load} | {cells}")
    return 0


def check(name: str) -> int:
    data, results = measure(name)
    bad = 0
    for case, loads in results.items():
        expect = data["cases"][case].get("expect", {})
        for load, spans in loads.items():
            for span, value in spans.items():
                want = expect.get(load, {}).get(span)
                if want != cck(value):
                    print(
                        f"{name}: {case}, {load}, {span}: {cck(value)}, expected {want}"
                    )
                    bad = 1
    return bad


def main(argv: list[str]) -> int:
    parser = cli.parser(__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("run", "check"):
        commands.add_parser(name, description=__doc__).add_argument("name")
    args = parser.parse_args(argv)
    return {"run": run, "check": check}[args.command](args.name)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
