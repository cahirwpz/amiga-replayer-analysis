#!/usr/bin/env python3
"""Time replay code on an emulated Amiga 500 with vAmiga.

Usage: timing.py install
       timing.py run NAME
       timing.py check NAME

  install  fetch vAmiga's Core at a pinned commit into build/vamiga and
           build .venv/bin/amiga-timing from tools/timing/
  run      print the measured CCK of every span, case and load
  check    compare them with `expect` in the data file; exit 1 on a
           difference

NAME is a data file, data/timing/NAME.yaml. It says which code to take
from a replay's source, where to set breakpoints, and what memory to
write before the code runs:

  source   the replay's source, from the repo root
  take     label ranges [FROM, TO] of the source, TO excluded. TO becomes
           a label at the range's end. A third item gives lines to add
           after that label.
  drop     source lines to leave out; whitespace does not count
  entry    the label that the boot code calls
  points   breakpoints: LABEL or LABEL+OFFSET or LABEL-OFFSET
  spans    NAME: [FROM, TO], two points. The span is the CPU time
           between them, in CCK
  cases    NAME: {writes, expect}. `writes` are "ADDRESS SIZE VALUE",
           with SIZE b, w or l, done before the call. `expect` holds
           the spans per load

The excerpt is assembled with vasm at $10000 in chip RAM, as a replay
runs. A boot ROM copies it there, does the writes, waits for line $50
and calls the entry. Each case runs under each load in LOADS: without
display DMA, and with 6 low-resolution bitplanes, which take the most
bus slots from the CPU. Nothing generated is kept outside build/.
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hardware.clock import CPU_PER_CCK  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "timing"
BUILD = ROOT / "build"
SOURCE = BUILD / "vamiga"  # a sparse checkout of Core/ only
BIN = ROOT / ".venv" / "bin"
DRIVER = BIN / "amiga-timing"
VASM = BIN / "vasmm68k_mot"
VAMIGA_URL = "https://github.com/dirkwhoffmann/vAmiga.git"
VAMIGA_COMMIT = "090681fdd8c2e3475e49cb2fc6f5031750399b6b"  # tag v4.5
EXCERPT_AT = 0x10000
START_LINE = 0x50  # inside the display window of every load

# Register writes that set up each load before the call
LOADS = {
    "no display": [],
    "6 bitplanes": [
        "move.w #$6200,$dff100",  # BPLCON0: 6 bitplanes, low resolution
        "move.w #$0038,$dff092",  # DDFSTRT
        "move.w #$00d0,$dff094",  # DDFSTOP
        "move.w #$2c81,$dff08e",  # DIWSTRT
        "move.w #$2cc1,$dff090",  # DIWSTOP
        *(f"move.l #$70000,$dff0{0xE0 + 4 * n:x}" for n in range(6)),  # BPLxPT
        "move.w #$8300,$dff096",  # DMACON: DMA and bitplanes on
    ],
}

BOOT = """\
 org $fc0000
 dc.w $1111
 dc.w $4ef9 ; jmp: reset reads its address as the PC
 dc.l start
start:
 move.b #3,$bfe201 ; CIA-A: LED and overlay are outputs
 move.b #2,$bfe001 ; overlay off: chip RAM at 0
 move.w #$7fff,$dff096 ; all DMA off
 move.w #$7fff,$dff09a ; all interrupts off
frame: ; vAmiga sets up bitplane DMA at the first frame's last line
 move.l $dff004,d0
 and.l #$1ff00,d0
 cmp.l #$13800,d0
 bne.s frame
 lea excerpt(pc),a0
 lea ${at:x},a1
 move.l #(excerpt_end-excerpt)/2-1,d0
copy:
 move.w (a0)+,(a1)+
 dbra d0,copy
{setup}
wait:
 move.l $dff004,d0
 and.l #$1ff00,d0
 cmp.l #${line:x}00,d0
 bne.s wait
 jsr ${entry:x}
done:
 bra.s done
excerpt:
 incbin "excerpt.bin"
excerpt_end:
 cnop 0,$40000
"""


def install():
    """Fetch vAmiga's Core once, then build the driver."""
    if not (SOURCE / ".git").exists():
        SOURCE.mkdir(parents=True, exist_ok=True)
        for args in (
            ["init", "-q"],
            ["remote", "add", "origin", VAMIGA_URL],
            ["sparse-checkout", "set", "Core"],
            [
                "fetch",
                "-q",
                "--depth",
                "1",
                "--filter=blob:none",
                "origin",
                VAMIGA_COMMIT,
            ],
            ["checkout", "-q", VAMIGA_COMMIT],
        ):
            git(*args)
    build = BUILD / "amiga-timing"
    run_or_exit(
        "cmake", "-S", ROOT / "tools" / "timing", "-B", build, "-G", "Ninja",
        "-DCMAKE_BUILD_TYPE=Release", f"-DVAMIGA_CORE={SOURCE / 'Core'}",
    )  # fmt: skip
    run_or_exit("ninja", "-C", build, "amiga-timing")
    BIN.mkdir(parents=True, exist_ok=True)
    shutil.copy(build / "amiga-timing", DRIVER)
    print(f"installed vAmiga {VAMIGA_COMMIT[:7]} as {DRIVER.relative_to(ROOT)}")


def git(*args):
    run_or_exit("git", "-C", SOURCE, *args)


def run_or_exit(*args):
    proc = subprocess.run([str(a) for a in args], capture_output=True, text=True)
    if proc.returncode:
        sys.exit(f"{' '.join(map(str, args[:2]))} failed:\n{proc.stdout}{proc.stderr}")
    return proc.stdout


def labels(lines):
    """{label: line index}: a label starts in the first column."""
    found = {}
    for i, line in enumerate(lines):
        if line and not line[0].isspace() and not line.startswith(";"):
            found.setdefault(re.split(r"[:\s]", line, maxsplit=1)[0], i)
    return found


def excerpt(data):
    """The assembler text: the taken ranges of the source, at EXCERPT_AT."""
    lines = (ROOT / data["source"]).read_text("latin-1").splitlines()
    where = labels(lines)
    drop = {" ".join(d.split()) for d in data.get("drop", [])}
    out = [f" org ${EXCERPT_AT:x}"]
    for first, end, *extra in data["take"]:
        for line in lines[where[first] : where[end]]:
            if " ".join(line.split()) not in drop:
                out.append(line)
        out.append(f"{end}:")
        out.extend(extra)
    return "\n".join(out) + "\n"


def assemble(work, name, text):
    """Assemble text in work; return the symbols of its listing."""
    (work / f"{name}.s").write_text(text, "latin-1")
    run_or_exit(
        VASM,
        "-quiet",
        "-Fbin",
        "-L",
        work / f"{name}.lst",
        "-o",
        work / f"{name}.bin",
        work / f"{name}.s",
    )
    listing = (work / f"{name}.lst").read_text("latin-1")
    return {
        m[1]: int(m[2], 16)
        for m in re.finditer(r"^(\w+)\s+A:([0-9A-F]{8})$", listing, re.M)
    }


def address(expr, symbols):
    """A number, LABEL, LABEL+OFFSET or LABEL-OFFSET; numbers in Python
    syntax."""
    m = re.fullmatch(r"(\w+)\s*(?:([+-])\s*(\w+))?", expr.strip())
    if not m:
        raise ValueError(f"bad address: {expr}")
    value = int(m[1], 0) if m[1][0].isdigit() else symbols[m[1]]
    if m[2]:
        value += int(m[3], 0) * (1 if m[2] == "+" else -1)
    return value


def writes(case, symbols):
    """move instructions for "ADDRESS SIZE VALUE" writes. A nested list,
    e.g. a YAML alias, adds its writes in place."""
    items = case.get("writes", [])
    while any(isinstance(i, list) for i in items):
        items = [j for i in items for j in (i if isinstance(i, list) else [i])]
    out = []
    for item in items:
        target, size, value = item.split()
        out.append(f" move.{size} #{int(value, 0)},${address(target, symbols):x}")
    return out


def measure(name):
    """{case: {load: {span: CCK}}}. Files go to build/timing/NAME."""
    if not DRIVER.exists():
        sys.exit("amiga-timing missing; run: tools/timing.py install")
    data = yaml.safe_load((DATA / f"{name}.yaml").read_text())
    work = BUILD / "timing" / name
    work.mkdir(parents=True, exist_ok=True)
    symbols = assemble(work, "excerpt", excerpt(data))
    points = {p: address(expr, symbols) for p, expr in data["points"].items()}
    results = {}
    for case_name, case in data["cases"].items():
        for load, setup in LOADS.items():
            text = BOOT.format(
                at=EXCERPT_AT,
                setup="\n".join(writes(case, symbols) + [f" {s}" for s in setup]),
                line=START_LINE,
                entry=symbols[data["entry"]],
            )
            assemble(work, "boot", text)
            out = run_or_exit(
                DRIVER, work / "boot.bin", *(f"{a:x}" for a in points.values())
            )
            clock = {
                int(a, 16): int(c)
                for a, c in (line.split() for line in out.splitlines())
            }
            spans = {
                span: (clock[points[b]] - clock[points[a]]) / CPU_PER_CCK
                for span, (a, b) in data["spans"].items()
            }
            results.setdefault(case_name, {})[load] = spans
    return data, results


def number(value):
    return int(value) if value == int(value) else value


def run(name):
    _, results = measure(name)
    for case, loads in results.items():
        for load, spans in loads.items():
            cells = ", ".join(f"{s} {number(v)}" for s, v in spans.items())
            print(f"{case} | {load} | {cells}")


def check(name):
    data, results = measure(name)
    bad = 0
    for case, loads in results.items():
        expect = data["cases"][case].get("expect", {})
        for load, spans in loads.items():
            for span, value in spans.items():
                want = expect.get(load, {}).get(span)
                if want != number(value):
                    print(
                        f"{name}: {case}, {load}, {span}: {number(value)}, expected {want}"
                    )
                    bad = 1
    return bad


def main(argv):
    if argv == ["install"]:
        return install()
    if len(argv) == 2 and argv[0] in ("run", "check"):
        return {"run": run, "check": check}[argv[0]](argv[1])
    sys.exit(__doc__)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
