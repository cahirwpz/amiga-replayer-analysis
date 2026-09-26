#!/usr/bin/env python3
"""Cognitive load checker for Markdown prose.

Usage: cogload.py FILE.md|DIR...

Prints `file:line: rule: detail` for each violation; exits 1 if any.
Limits depend on the file's directory (see PROFILES). Code is exempt.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GLOSSARY = ROOT / "docs" / "glossary.md"

DEFAULT = {
    "sentence_words": 16,  # words per sentence
    "block_sentences": 3,  # sentences per paragraph or list item
    "list_items": 7,  # items per list (per nesting level)
    "list_depth": 2,  # nested list levels
    "file_words": 450,  # words per file, tables included
    "cell_words": 15,  # words per table cell
    "fk_grade": 12.0,  # Flesch-Kincaid grade of the file's prose
}

# First matching path prefix (relative to ROOT) wins.
PROFILES = [
    # A lookup table, not read top to bottom.
    ("docs/glossary.md", {"file_words": 3000}),
    ("players/", {"file_words": 200}),
    ("ideas/", {"file_words": 300}),
    (
        "details/",
        {
            "sentence_words": 20,
            "block_sentences": 5,
            "list_items": 10,
            "list_depth": 3,
            "file_words": 1000,
            "cell_words": 25,
            "fk_grade": 14.0,
        },
    ),
]

# Files exempt from the acronym check.
ACRONYM_EXEMPT = {"AGENTS.md", "docs/glossary.md"}

# FK grade is noisy on tiny samples.
FK_MIN_WORDS = 50

ABBREVIATIONS = ["e.g.", "i.e.", "vs.", "etc.", "cf.", "approx.", "no."]

LIST_RE = re.compile(r"^(\s*)(?:[-*+]|\d+[.)])\s+(.*)$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
ACRONYM_RE = re.compile(r"\b([A-Z][A-Z0-9]+)s?\b")
WORD_RE = re.compile(r"[^\W_]", re.UNICODE)
ROMAN_RE = re.compile(r"[IVX]+")  # "Mugician II" is not an acronym


def profile_for(path):
    try:
        rel = path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        rel = path.as_posix()
    limits = dict(DEFAULT)
    for prefix, overrides in PROFILES:
        if rel.startswith(prefix):
            limits.update(overrides)
            break
    return rel, limits


def clean(text):
    """Reduce inline Markdown to plain prose. Inline code becomes one word."""
    text = re.sub(r"`[^`]*`", "CODE", text)
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\[[^\]]*\]", r"\1", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[*_]{1,3}", "", text)
    return text


def words(text):
    return [w for w in text.split() if WORD_RE.search(w)]


def sentences(text):
    for abbr in ABBREVIATIONS:
        text = text.replace(abbr, abbr.replace(".", "\0"))
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p for p in (s.replace("\0", ".") for s in parts) if words(p)]


def syllables(word):
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w or not re.search(r"[a-z]", word):
        return 1
    if word.isupper():
        return 1
    groups = re.findall(r"[aeiouy]+", w)
    n = len(groups)
    if w.endswith("e") and not w.endswith("le") and n > 1:
        n -= 1
    return max(n, 1)


def load_glossary():
    terms = set()
    if not GLOSSARY.exists():
        return None
    for line in GLOSSARY.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*(?:[-*+]\s+|\|\s*)?\*\*(.+?)\*\*", line)
        if m:
            for term in re.split(r"[/,]", m.group(1)):
                terms.add(term.strip())
    return terms


def parse(lines):
    """Yield (kind, lineno, payload) blocks.

    kind: 'para' (text), 'item' (text, indent), 'cell' (text), 'heading' (text).
    """
    in_code = False
    start = 0
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                start = i + 1
                break

    para, para_line = [], 0
    item, item_line, item_indent = None, 0, 0

    def flush():
        nonlocal para, item
        out = []
        if para:
            out.append(("para", para_line, " ".join(para)))
            para = []
        if item is not None:
            out.append(("item", item_line, (" ".join(item), item_indent)))
            item = None
        return out

    for i in range(start, len(lines)):
        n = i + 1
        line = lines[i]
        if FENCE_RE.match(line):
            yield from flush()
            in_code = not in_code
            continue
        if in_code:
            continue
        stripped = line.strip()
        if not stripped:
            yield from flush()
            yield ("blank", n, None)
            continue
        if stripped.startswith("<!--"):
            continue
        if stripped.startswith("#"):
            yield from flush()
            yield ("heading", n, stripped.lstrip("#").strip())
            continue
        if stripped.startswith("|"):
            yield from flush()
            if re.fullmatch(r"[|:\-\s]+", stripped):
                continue
            for cell in stripped.strip("|").split("|"):
                yield ("cell", n, cell.strip())
            continue
        m = LIST_RE.match(line)
        if m:
            yield from flush()
            item, item_line, item_indent = [m.group(2)], n, len(m.group(1))
            continue
        if item is not None and line.startswith(" "):
            item.append(stripped)
            continue
        if stripped.startswith(">"):
            stripped = stripped.lstrip("> ").strip()
        if item is not None:
            yield from flush()
        if not para:
            para_line = n
        para.append(stripped)
    yield from flush()


def check(path, glossary):
    rel, lim = profile_for(path)
    lines = path.read_text(encoding="utf-8").splitlines()
    errors = []

    def err(line, rule, detail):
        errors.append(f"{rel}:{line}: {rule}: {detail}")

    total_words = 0
    prose_words = prose_sentences = prose_syllables = 0
    unknown = {}

    # List tracking: stack of [indent, item_count, first_line].
    stack = []
    pending_blank = False

    def close_lists(indent=-1):
        while stack and stack[-1][0] > indent:
            ind, count, first = stack.pop()
            if count > lim["list_items"]:
                err(first, "list-items", f"{count} > {lim['list_items']}")

    for kind, n, payload in parse(lines):
        if kind == "blank":
            pending_blank = True
            continue
        if kind == "item":
            text, indent = payload
            close_lists(indent)
            if stack and stack[-1][0] == indent:
                stack[-1][1] += 1
            else:
                stack.append([indent, 1, n])
            if len(stack) > lim["list_depth"]:
                err(n, "list-depth", f"{len(stack)} > {lim['list_depth']}")
        elif kind == "para" and pending_blank:
            close_lists()
        elif kind in ("heading", "cell"):
            close_lists()
        pending_blank = False

        if kind == "item":
            text = payload[0]
        else:
            text = payload
        text = clean(text)
        w = words(text)
        total_words += len(w)

        if glossary is not None:
            for m in ACRONYM_RE.finditer(text):
                term = m.group(1)
                if term == "CODE" or ROMAN_RE.fullmatch(term):
                    continue
                if term not in glossary:
                    unknown.setdefault(m.group(1), n)
        if kind == "cell":
            if len(w) > lim["cell_words"]:
                err(n, "cell-words", f"{len(w)} > {lim['cell_words']}")
            continue
        if kind == "heading":
            continue

        sents = sentences(text)
        if len(sents) > lim["block_sentences"]:
            err(n, "block-sentences", f"{len(sents)} > {lim['block_sentences']}")
        for s in sents:
            sw = words(s)
            if len(sw) > lim["sentence_words"]:
                err(
                    n,
                    "sentence-words",
                    f"{len(sw)} > {lim['sentence_words']}: {s[:50]}…",
                )
            prose_words += len(sw)
            prose_syllables += sum(syllables(x) for x in sw)
        prose_sentences += len(sents)
    close_lists()

    if total_words > lim["file_words"]:
        err(1, "file-words", f"{total_words} > {lim['file_words']}")
    if prose_words >= FK_MIN_WORDS and prose_sentences:
        grade = (
            0.39 * prose_words / prose_sentences
            + 11.8 * prose_syllables / prose_words
            - 15.59
        )
        if grade > lim["fk_grade"]:
            err(1, "fk-grade", f"{grade:.1f} > {lim['fk_grade']}")
    if rel not in ACRONYM_EXEMPT:
        for term, n in unknown.items():
            err(n, "acronym", f"{term} not in docs/glossary.md")
    return errors


def main(argv):
    glossary = load_glossary()
    errors = []
    for arg in map(Path, argv):
        for path in sorted(arg.rglob("*.md")) if arg.is_dir() else [arg]:
            errors += check(path, glossary)
    for e in errors:
        print(e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
