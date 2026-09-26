#!/usr/bin/env python3
"""Render annotated copies of replayer sources.

Usage: annot.py [--check] [YAML...]

YAML defaults to every data/annot/*.yaml. Each file annotates one source
in ext/, which stays read-only:

  source: ext/uade/amigasrc/players/uade/soundmon/Soundmon2.2.s
  sha1: 0123...          # `sha1sum` of the source; a pin update must fix it
  labels:                # original label: new name
    bpmusic: PlayTick
  comments:              # source line: comment appended to that line
    185: vibrato step, shared by all voices
  banners:               # source line: block comment above that line
    622: Synth walkers, once per tick.

Line numbers are those of the pinned source. Renames change whole
identifiers outside `;` comments. Added comments start with `;;`, so they
never pass for the author's.

The YAML is the committed artefact. Output goes to
build/annot/<player><suffix>, never committed. With --check, nothing is
written. Prints `file: problem` for each problem; exits 1 if any.
"""

import hashlib
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
ANNOT = ROOT / "data" / "annot"
OUT = ROOT / "build" / "annot"

FIELDS = {"source", "sha1", "labels", "comments", "banners"}
IDENT = r"[A-Za-z_][\w.]*"


class UniqueKeyLoader(yaml.SafeLoader):
    """A duplicate key would silently drop an annotation."""

    def construct_mapping(self, node, deep=False):
        seen = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                raise yaml.constructor.ConstructorError(
                    None, None, f"duplicate key {key!r}", key_node.start_mark
                )
            seen.add(key)
        return super().construct_mapping(node, deep)


def load(path):
    with open(path, encoding="utf-8") as f:
        return yaml.load(f, UniqueKeyLoader) or {}


def code_part(line):
    """(code, comment) of an assembler line; `*` in column 1 is a comment."""
    if line.startswith("*"):
        return "", line
    code, sep, rest = line.partition(";")
    return code, sep + rest


def check(spec, lines, sha1):
    """Yield problems with the spec against the source lines."""
    for key in sorted(set(spec) - FIELDS):
        yield f"unknown field `{key}`"
    if spec.get("sha1") != sha1:
        yield f"sha1 is {spec.get('sha1')}, source has {sha1}"

    labels = spec.get("labels") or {}
    defined = {m.group(0) for line in lines if (m := re.match(IDENT, line))}
    used = {w for line in lines for w in re.findall(IDENT, code_part(line)[0])}
    for old, new in labels.items():
        if not isinstance(old, str) or not isinstance(new, str):
            yield f"labels: {old}: {new} is not a pair of strings; quote it"
        elif old not in defined:
            yield f"label {old} is not defined in the source"
        if not re.fullmatch(IDENT, str(new)):
            yield f"{new} is not an identifier"
        elif new in used:
            yield f"{new} already occurs in the source"
    for new in {n for n in labels.values() if list(labels.values()).count(n) > 1}:
        yield f"{new} is the new name of several labels"

    for field in ("comments", "banners"):
        for num, text in (spec.get(field) or {}).items():
            if not isinstance(num, int) or not 1 <= num <= len(lines):
                yield f"{field}: line {num} is not in the source"
            if not isinstance(text, str):
                yield f"{field}: line {num} has no text"
            elif field == "comments" and "\n" in text.strip():
                yield f"comments: line {num} spans several lines; use a banner"
            else:
                try:
                    text.encode("latin-1")
                except UnicodeEncodeError:
                    yield f"{field}: line {num} is not Latin-1"


def render(spec, lines):
    """The annotated source, as a list of lines."""
    labels = spec.get("labels") or {}
    comments = spec.get("comments") or {}
    banners = spec.get("banners") or {}
    rename = None
    if labels:
        names = "|".join(map(re.escape, sorted(labels, key=len, reverse=True)))
        rename = re.compile(rf"(?<![\w.$])(?:{names})(?![\w.])")
    out = []
    for num, line in enumerate(lines, start=1):
        if num in banners:
            out.append(";; " + "-" * 60)
            out += [f";; {t}".rstrip() for t in banners[num].strip().split("\n")]
        if rename:
            code, rest = code_part(line)
            line = rename.sub(lambda m: labels[m.group(0)], code) + rest
        if num in comments:
            line = f"{line.rstrip()}\t;; {comments[num].strip()}"
        out.append(line)
    return out


def process(path, write):
    """Check one YAML file and render it; return a list of problems."""
    rel = path.resolve().relative_to(ROOT).as_posix()
    try:
        spec = load(path)
    except yaml.YAMLError as e:
        return [f"{rel}: {e}".replace("\n", " ")]
    source = ROOT / str(spec.get("source", ""))
    if not spec.get("source") or not source.is_file():
        return [f"{rel}: source {spec.get('source')} does not exist"]
    data = source.read_bytes()
    lines = data.decode("latin-1").split("\n")
    problems = [
        f"{rel}: {p}" for p in check(spec, lines, hashlib.sha1(data).hexdigest())
    ]
    if write and not problems:
        OUT.mkdir(parents=True, exist_ok=True)
        dest = OUT / (path.stem + source.suffix)
        dest.write_bytes("\n".join(render(spec, lines)).encode("latin-1"))
        print(dest.relative_to(ROOT))
    return problems


def main(argv):
    write = "--check" not in argv
    args = [a for a in argv if a != "--check"]
    if any(a.startswith("-") for a in args):
        sys.exit(__doc__)
    paths = [Path(a) for a in args] or sorted(ANNOT.glob("*.yaml"))
    problems = [p for path in paths for p in process(path, write)]
    for p in problems:
        print(p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
