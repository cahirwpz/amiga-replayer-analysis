#!/usr/bin/env python3
"""Cognitive load checker for Markdown prose.

Usage: cogload.py FILE.md|DIR...

Prints `file:line: rule: detail` for each violation; exits 1 if any.
Limits depend on the file's directory (see PROFILES). Code is exempt.
Also flags acronyms missing from data/glossary.yaml, and its avoided terms.
A "Seen in:" paragraph is a list of links, a lookup like a table: it has
no sentence limits and does not count toward the file's words.
A card, players/<player>.md, names no command by number and no hex number
equal to a constant of the player's spec; see tools/numbered.py.
Markdown is parsed by tools/mdtools.py; regexes only see the extracted prose.
"""

import re
import sys
from pathlib import Path

import cli
import glossary
import numbered
from mdtools import CODE, line_of, literal, plain, read

ROOT = Path(__file__).resolve().parent.parent

DEFAULT = {
    "sentence_words": 16,  # words per sentence
    "block_sentences": 3,  # sentences per paragraph or list item
    "list_items": 7,  # items per list (per nesting level)
    "list_depth": 2,  # nested list levels
    "file_words": 450,  # words per file; 0: no limit
    "count_tables": True,  # table cells count toward file_words
    "cell_words": 15,  # words per table cell
    "fk_grade": 12.0,  # Flesch-Kincaid grade of the file's prose
}

# First matching path prefix (relative to ROOT) wins.
PROFILES = [
    # A lookup table, not read top to bottom.
    ("docs/glossary.md", {"file_words": 3000}),
    # A checklist; its tables are lookups, like the glossary.
    ("docs/control-dimensions.md", {"file_words": 450, "count_tables": False}),
    # Working rules; read at the start of every session.
    ("AGENTS.md", {"file_words": 600}),
    # Working notes; sections go away as tasks are done.
    ("TODO.md", {"file_words": 1000}),
    # Cards: tools/print.py limits them by printed pages instead.
    ("players/", {"file_words": 0}),
    ("ideas/", {"file_words": 600}),
    # A lookup of techniques that cards link, like the family pages.
    ("docs/paula-techniques.md", {"file_words": 600}),
]

# Files exempt from the acronym check.
ACRONYM_EXEMPT = {"AGENTS.md", "docs/glossary.md"}
# Files exempt from the avoided-terms check.
AVOID_EXEMPT = {"docs/glossary.md"}

SEEN_IN = "Seen in:"  # starts a list of links, e.g. in docs/paula-techniques.md

# FK grade is noisy on tiny samples.
FK_MIN_WORDS = 50

ABBREVIATIONS = ["e.g.", "i.e.", "vs.", "etc.", "cf.", "approx.", "no."]

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


def load_avoided():
    """(pattern, avoided, preferred) for each glossary avoided term."""
    return [
        (re.compile(rf"\b{re.escape(term)}s?\b", re.IGNORECASE), term, use)
        for term, use in glossary.avoided().items()
    ]


def blocks(doc):
    """Yield (kind, line, text, code) for each block of prose.

    kind: 'heading', 'para', 'links' (a "Seen in:" list) or 'cell'; code is
    the text with code spans.
    Lists come as separate events: ('list-open', line), ('item', line) and
    ('list-close', line).
    """
    tokens = doc.tokens
    for i, token in enumerate(tokens):
        kind = token.type
        if kind in ("bullet_list_open", "ordered_list_open"):
            yield "list-open", line_of(token), None, None
        elif kind in ("bullet_list_close", "ordered_list_close"):
            yield "list-close", 0, None, None
        elif kind == "list_item_open":
            yield "item", line_of(token), None, None
        elif kind == "inline":
            parent = tokens[i - 1].type
            block = {
                "heading_open": "heading",
                "paragraph_open": "para",
                "th_open": "cell",
                "td_open": "cell",
            }.get(parent)
            text = plain(token)
            if block == "para" and text.startswith(SEEN_IN):
                block = "links"
            if block:
                yield block, line_of(token), text, literal(token)


def card_constants(rel):
    """{value: [names]} of the spec of the player whose card this is."""
    parts = Path(rel).parts
    if len(parts) == 2 and parts[0] == "players" and rel.endswith(".md"):
        return numbered.for_player(Path(rel).stem)
    return None


def check(path, known_terms, avoided=()):
    rel, lim = profile_for(path)
    consts = card_constants(rel)
    errors = []

    def err(line, rule, detail):
        errors.append(f"{rel}:{line}: {rule}: {detail}")

    total_words = 0
    prose_words = prose_sentences = prose_syllables = 0
    unknown: dict[str, int] = {}
    lists = []  # one [item count, first line] per open list

    for kind, n, text, code in blocks(read(path)):
        if kind == "list-open":
            lists.append([0, n])
            if len(lists) > lim["list_depth"]:
                err(n, "list-depth", f"{len(lists)} > {lim['list_depth']}")
            continue
        if kind == "list-close":
            count, first = lists.pop()
            if count > lim["list_items"]:
                err(first, "list-items", f"{count} > {lim['list_items']}")
            continue
        if kind == "item":
            lists[-1][0] += 1
            continue

        if consts is not None:
            for _, detail in numbered.find(code, consts):
                err(n, "number", detail)
        w = words(text)
        if kind in ("para", "heading") or (kind == "cell" and lim["count_tables"]):
            total_words += len(w)
        if rel not in AVOID_EXEMPT:
            for pattern, term, use in avoided:
                if pattern.search(text):
                    err(n, "avoid", f"`{term}`: use `{use}`")
        for m in ACRONYM_RE.finditer(text):
            term = m.group(1)
            if term == CODE or ROMAN_RE.fullmatch(term):
                continue
            if term not in known_terms:
                unknown.setdefault(term, n)
        if kind == "cell":
            if len(w) > lim["cell_words"]:
                err(n, "cell-words", f"{len(w)} > {lim['cell_words']}")
            continue
        if kind in ("heading", "links"):
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

    if lim["file_words"] and total_words > lim["file_words"]:
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
            err(n, "acronym", f"{term} not in data/glossary.yaml")
    return errors


def main(argv):
    parser = cli.parser(__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args(argv)
    known_terms = glossary.terms()
    avoided = load_avoided()
    errors = []
    for arg in args.paths:
        for path in sorted(arg.rglob("*.md")) if arg.is_dir() else [arg]:
            errors += check(path, known_terms, avoided)
    for e in errors:
        print(e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
