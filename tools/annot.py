#!/usr/bin/env python3
"""Render annotated copies of replayer sources.

Usage: annot.py [--check] [YAML...]

YAML defaults to every data/annot/*.yaml. Each file annotates one source
in ext/, which stays read-only:

  source: ext/uade/amigasrc/players/uade/soundmon/Soundmon2.2.s
  sha1: 0123...          # `sha1sum` of the source; a pin update must fix it
  labels:                # original label, or source line: new name
    bpmusic: PlayTick
    881: ModWrite        # a new label before line 881
  comments:              # source line: comment appended to that line
    185: vibrato step, shared by all voices
  banners:               # source line: block comment above that line
    622: Synth walkers, once per tick.
  refs:                  # more files that types: may name, e.g. format notes
    - ext/uade/amigasrc/players/uade/soundmon/format.txt
  types:                 # spec class: words in the source or refs
    Voice: [trk_prevper]

`types` anchor the CamelCase classes of specs/<player>.py; see
tools/specs.py. Each word must occur as a whole word. Citations may name
types like labels.

Line numbers are those of the pinned source. Renames change whole
identifiers outside `;` comments. New labels get a line of their own; the
listing is for reading, so they may split the scope of local labels. Added
comments start with `;;`, so they never pass for the author's.

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

FIELDS = {"source", "sha1", "labels", "comments", "banners", "refs", "types"}
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


def defined(lines):
    """Labels the source defines: identifiers in column 1."""
    return {m.group(0) for line in lines if (m := re.match(IDENT, line))}


def check(spec, lines, sha1):
    """Yield problems with the spec against the source lines."""
    for key in sorted(set(spec) - FIELDS):
        yield f"unknown field `{key}`"
    if spec.get("sha1") != sha1:
        yield f"sha1 is {spec.get('sha1')}, source has {sha1}"

    labels = spec.get("labels") or {}
    known = defined(lines)
    used = {w for line in lines for w in re.findall(IDENT, code_part(line)[0])}
    for old, new in labels.items():
        if isinstance(old, int):
            if not 1 <= old <= len(lines):
                yield f"labels: line {old} is not in the source"
        elif not isinstance(old, str) or not isinstance(new, str):
            yield f"labels: {old}: {new} is not a pair of strings; quote it"
        elif old not in known:
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

    yield from check_types(spec, lines, set(labels.values()))


def check_types(spec, lines, labels):
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
        if not isinstance(words, list) or not words:
            yield f"types: {name} needs a list of words"
            continue
        for word in words:
            pattern = re.compile(rf"(?<![\w.]){re.escape(str(word))}(?!\w)")
            if not any(pattern.search(t) for t in texts):
                yield f"types: {name}: {word} is in neither the source nor refs"


def render(spec, lines):
    """The annotated source, as a list of lines."""
    labels = {k: v for k, v in (spec.get("labels") or {}).items() if isinstance(k, str)}
    new = {k: v for k, v in (spec.get("labels") or {}).items() if isinstance(k, int)}
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


def source_lines(spec):
    """(raw bytes, lines) of the annotated source."""
    data = (ROOT / str(spec["source"])).read_bytes()
    return data, data.decode("latin-1").split("\n")


def listing_labels(path):
    """Every label in the rendered listing, and every type; for citations."""
    spec = load(path)
    labels = spec.get("labels") or {}
    renamed = {k for k in labels if isinstance(k, str)}
    listing = defined(source_lines(spec)[1]) - renamed
    return listing | set(labels.values()) | set(spec.get("types") or {})


def cited_labels(path, cache={}):
    """Labels a citation `path:Label` may name; None if the file has none.

    Assembler: identifiers in column 1. C: function names. IRA config: LABEL
    and SYMBOL. data/annot/*.yaml: the labels of the rendered listing.
    """
    if path not in cache:
        text = path.read_bytes().decode("latin-1")
        suffix = path.suffix.lower()
        if suffix == ".yaml":
            cache[path] = listing_labels(path) if path.parent.name == "annot" else None
        elif suffix == ".cnf":
            found = re.finditer(r"^(?:LABEL|SYMBOL)\s+(\S+)\s", text, re.M)
            cache[path] = {m.group(1) for m in found}
        elif suffix in (".c", ".h"):
            found = re.finditer(r"^[A-Za-z_][^;()=\n]*?\b(\w+)\s*\(", text, re.M)
            cache[path] = {m.group(1) for m in found}
        else:
            cache[path] = defined(text.split("\n"))
    return cache[path]


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
    data, lines = source_lines(spec)
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
