#!/usr/bin/env python3
"""Render annotated copies of replayer sources.

Usage: annot.py [--check] [YAML...]

YAML defaults to every data/annot/*.yaml. Each file annotates one source
in ext/, which stays read-only:

  source: ext/uade/amigasrc/players/uade/soundmon/Soundmon2.2.s
  sha1: 0123...          # `sha1sum` of the source; a pin update must fix it
  labels:                # original label, or source line: new name
    bpmusic: PlayTick
    PlayNote: PlayNote   # a readable label keeps its name
    881: ModWrite        # a new label before line 881
  comments:              # source line: comment appended to that line
    185: vibrato step, shared by all voices
  banners:               # source line: block comment above that line
    622: Synth walkers, once per tick.
  refs:                  # more files that types: may name, e.g. format notes
    - ext/uade/amigasrc/players/uade/soundmon/format.txt
  types:                 # spec class: words in the source or refs
    Voice: [trk_prevper]
  layouts:               # a type's record: size, field: [offset, b|w|l]
    Voice: {size: 36, fields: {period: [0, w], volume: [2, b]}}

A key may be any identifier of the code, also one used but not defined,
e.g. an offset symbol. Specs name labels only by their new names; see
tools/specs.py.

`types` anchor the CamelCase classes of specs/<player>.py; see
tools/specs.py. Each word must occur as a whole word. Citations may name
types like labels.

`layouts` give the byte layout of a type's record, for tools that write
records into memory, e.g. tools/timing.py. Field names are the spec's
attribute names; a nested one is dotted: `eg.pos`. Only the fields a
tool needs are listed. A field lies inside the record; a word or long
starts at an even offset; fields do not overlap.

A player with only an IRA config has no source to annotate. Its file names
the config as `source` and holds only `types`, `layouts` and `refs`; the config's own
LABELs are the new names. It needs no sha1 and renders nothing.

Comments and banners name no command by number, and no hex number equal
to a constant of the player's spec; see tools/numbered.py. A banner line
that starts with an offset may, if the banner has several: a layout.

Line numbers are those of the pinned source. Renames change whole
identifiers outside `;` comments. New labels get a line of their own; the
listing is for reading, so they may split the scope of local labels. Added
comments start with `;;`, so they never pass for the author's.

The YAML is the committed artefact. Output goes to
build/annot/<player><suffix>, never committed. With --check, nothing is
written. Prints `file: problem` for each problem; exits 1 if any.
"""

# mypy: disallow-untyped-defs

import ast
import hashlib
import re
import sys
from collections import Counter
from collections.abc import Hashable, Iterator
from functools import cache
from pathlib import Path
from typing import Any

import numbered
import yaml

ROOT = Path(__file__).resolve().parent.parent
ANNOT = ROOT / "data" / "annot"
OUT = ROOT / "build" / "annot"

FIELDS = {"source", "sha1", "labels", "comments", "banners", "refs", "types", "layouts"}
SIZES = {"b": 1, "w": 2, "l": 4}
IDENT = r"[A-Za-z_][\w.]*"

Spec = dict[str, Any]  # an annotation file, as loaded


class UniqueKeyLoader(yaml.SafeLoader):
    """A duplicate key would silently drop an annotation."""

    def construct_mapping(
        self, node: yaml.MappingNode, deep: bool = False
    ) -> dict[Hashable, Any]:
        seen = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                raise yaml.constructor.ConstructorError(
                    None, None, f"duplicate key {key!r}", key_node.start_mark
                )
            seen.add(key)
        return super().construct_mapping(node, deep)


def load(path: Path) -> Spec:
    with open(path, encoding="utf-8") as f:
        return yaml.load(f, UniqueKeyLoader) or {}


def code_part(line: str) -> tuple[str, str]:
    """(code, comment) of an assembler line; `*` in column 1 is a comment."""
    if line.startswith("*"):
        return "", line
    code, sep, rest = line.partition(";")
    return code, sep + rest


def defined(lines: list[str]) -> set[str]:
    """Labels the source defines: identifiers in column 1."""
    return {m.group(0) for line in lines if (m := re.match(IDENT, line))}


def is_config(spec: Spec) -> bool:
    """True if the source is one of our IRA configs, data/disasm/*.cnf."""
    return str(spec.get("source", "")).endswith(".cnf")


def renames(spec: Spec) -> tuple[dict[str, str], dict[int, str]]:
    """({old label: new name}, {source line: new label}) of `labels`."""
    labels = spec.get("labels") or {}
    return (
        {k: v for k, v in labels.items() if isinstance(k, str)},
        {k: v for k, v in labels.items() if isinstance(k, int)},
    )


def check(spec: Spec, lines: list[str], sha1: str) -> Iterator[str]:
    """Yield problems with the spec against the source lines."""
    for key in sorted(set(spec) - FIELDS):
        yield f"unknown field `{key}`"
    if is_config(spec):
        for key in sorted(set(spec) - {"source", "refs", "types", "layouts"}):
            yield f"`{key}` needs a source; a config takes only types, layouts and refs"
        new_names = cited_labels(ROOT / spec["source"]) or set()
    else:
        yield from check_source(spec, lines, sha1)
        new_names = set((spec.get("labels") or {}).values())
    yield from check_types(spec, lines, new_names)
    yield from check_layouts(spec)


def check_source(spec: Spec, lines: list[str], sha1: str) -> Iterator[str]:
    """Yield problems with `sha1`, `labels`, `comments` and `banners`."""
    if spec.get("sha1") != sha1:
        yield f"sha1 is {spec.get('sha1')}, source has {sha1}"

    labels = spec.get("labels") or {}
    known = defined(lines)
    used = {w for line in lines for w in re.findall(IDENT, code_part(line)[0])}
    for old, new in labels.items():
        if isinstance(old, int):
            if not 1 <= old <= len(lines):
                yield f"labels: line {old} is not in the source"
        elif old not in known and old not in used:
            yield f"label {old} is not in the source"
        if not re.fullmatch(IDENT, str(new)):
            yield f"{new} is not an identifier"
        elif new in used and new != old:
            yield f"{new} already occurs in the source"
    for new, count in Counter(labels.values()).items():
        if count > 1:
            yield f"{new} is the new name of several labels"

    for field in ("comments", "banners"):
        for num, text in (spec.get(field) or {}).items():
            if not isinstance(num, int) or not 1 <= num <= len(lines):
                yield f"{field}: line {num} is not in the source"
            if field == "comments" and "\n" in text.strip():
                yield f"comments: line {num} spans several lines; use a banner"
            try:
                text.encode("latin-1")
            except UnicodeEncodeError:
                yield f"{field}: line {num} is not Latin-1"


def check_types(spec: Spec, lines: list[str], labels: set[str]) -> Iterator[str]:
    """Yield problems with `refs` and `types`."""
    texts = ["\n".join(lines)]
    for ref in spec.get("refs") or []:
        path = ROOT / str(ref)
        if not path.is_file():
            yield f"refs: {ref} does not exist"
        else:
            texts.append(path.read_bytes().decode("latin-1"))
    for name, words in (spec.get("types") or {}).items():
        if not re.fullmatch(r"[A-Z]\w*", str(name)):
            yield f"types: {name} is not a CamelCase name"
        if name in labels:
            yield f"types: {name} is also a label"
        for word in words:
            pattern = re.compile(rf"(?<![\w.]){re.escape(str(word))}(?!\w)")
            if not any(pattern.search(t) for t in texts):
                yield f"types: {name}: {word} is in neither the source nor refs"


def layout(spec: Spec, name: str) -> tuple[int, dict[str, tuple[int, int]]]:
    """(record size, {field: (offset, size in bytes)}) of a type's layout."""
    found = spec["layouts"][name]
    fields = {f: (at, SIZES[size]) for f, (at, size) in found["fields"].items()}
    return found["size"], fields


def check_layouts(spec: Spec) -> Iterator[str]:
    """Yield problems with `layouts`."""
    types = spec.get("types") or {}
    for name, found in (spec.get("layouts") or {}).items():
        if name not in types:
            yield f"layouts: {name} is not in types"
        size = found["size"]
        taken: dict[int, str] = {}
        for field, (at, kind) in found["fields"].items():
            if not re.fullmatch(r"[a-z_]\w*(\.[a-z_]\w*)*", str(field)):
                yield f"layouts: {name}: {field} is not an attribute name"
            width = SIZES[kind]
            if at < 0 or at + width > size:
                yield f"layouts: {name}: {field} lies outside {size} bytes"
            if width > 1 and at % 2:
                yield f"layouts: {name}: {field} is a {kind} at an odd offset"
            for byte in range(at, at + width):
                if byte in taken:
                    yield f"layouts: {name}: {field} overlaps {taken[byte]}"
                    break
                taken[byte] = field


def check_numbers(spec: Spec, consts: dict[int, list[str]]) -> Iterator[str]:
    """Yield numbers that stand in for names in comments and banners."""
    for field in ("comments", "banners"):
        for num, text in (spec.get(field) or {}).items():
            skip = numbered.layout(str(text)) if field == "banners" else set()
            for line in str(text).split("\n"):
                if line in skip:
                    continue
                for _, detail in numbered.find(line, consts):
                    yield f"{field}: line {num}: {detail}"


def player_of(path: Path) -> str:
    """The player an annotation file belongs to: <player>[-<part>].yaml."""
    import players  # players imports this module

    known = players.load()
    stem = path.stem
    return stem if stem in known else stem.rpartition("-")[0]


def render(spec: Spec, lines: list[str]) -> list[str]:
    """The annotated source, as a list of lines."""
    labels, new = renames(spec)
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
        if num in new:
            out.append(f"{new[num]}:")
        if rename:
            code, rest = code_part(line)
            line = rename.sub(lambda m: labels[m.group(0)], code) + rest
        if num in comments:
            line = f"{line.rstrip()}\t;; {comments[num].strip()}"
        out.append(line)
    return out


def source_lines(spec: Spec) -> list[str]:
    """The lines of the annotated source."""
    return (ROOT / str(spec["source"])).read_bytes().decode("latin-1").split("\n")


def listing_labels(path: Path) -> set[str]:
    """Every label in the rendered listing, and every type; for citations."""
    spec = load(path)
    types = set(spec.get("types") or {})
    if is_config(spec):
        return (cited_labels(ROOT / spec["source"]) or set()) | types
    labels, new = renames(spec)
    listing = defined(source_lines(spec)) - set(labels)
    return listing | set(labels.values()) | set(new.values()) | types


@cache
def cited_labels(path: Path) -> set[str] | None:
    """Labels a citation `path:Label` may name; None if the file has none.

    Assembler: identifiers in column 1. C: function names. IRA config: LABEL
    and SYMBOL. data/annot/*.yaml: the labels of the rendered listing.
    Python, e.g. specs/: top-level functions and classes. .NET resources
    (.resx), e.g. a port's notes: string names.
    """
    text = path.read_bytes().decode("latin-1")
    suffix = path.suffix.lower()
    if suffix == ".yaml":
        return listing_labels(path) if path.parent.name == "annot" else None
    if suffix == ".py":
        return {getattr(n, "name", "") for n in ast.parse(text).body} - {""}
    if suffix == ".cnf":
        pattern = r"^(?:LABEL|SYMBOL)\s+(\S+)\s"
    elif suffix == ".resx":
        pattern = r'<data name="([^"]+)"'
    elif suffix in (".c", ".h"):
        pattern = r"^[A-Za-z_][^;()=\n]*?\b(\w+)\s*\("
    else:
        return defined(text.split("\n"))
    return {m.group(1) for m in re.finditer(pattern, text, re.M)}


def process(path: Path, write: bool) -> list[str]:
    """Check one YAML file and render it; return a list of problems."""
    rel = path.resolve().relative_to(ROOT).as_posix()
    try:
        spec = load(path)
    except yaml.YAMLError as e:
        return [f"{rel}: {e}".replace("\n", " ")]
    source = ROOT / str(spec.get("source", ""))
    if not spec.get("source") or not source.is_file():
        return [f"{rel}: source {spec.get('source')} does not exist"]
    lines = source_lines(spec)
    sha1 = hashlib.sha1(source.read_bytes()).hexdigest()
    problems = [f"{rel}: {p}" for p in check(spec, lines, sha1)]
    consts = numbered.for_player(player_of(path))
    problems += [f"{rel}: {p}" for p in check_numbers(spec, consts)]
    if write and not problems and not is_config(spec):
        OUT.mkdir(parents=True, exist_ok=True)
        dest = OUT / (path.stem + source.suffix)
        dest.write_bytes("\n".join(render(spec, lines)).encode("latin-1"))
        print(dest.relative_to(ROOT))
    return problems


def main(argv: list[str]) -> int:
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
