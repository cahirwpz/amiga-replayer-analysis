"""Read and write Markdown for the tools in this directory.

Reading goes through markdown-it-py, never through regular expressions:
  read(path)       front matter (YAML) and the token stream
  plain(inline)    the prose of an inline token; code spans become CODE
  children(inline) (line, child) for each child of an inline token
  sections(doc)    body tokens grouped under their `##` headings
  table(tokens)    the first table in a token list, as (line, cells) rows

Writing produces text that prettier leaves unchanged, so generated files can
be compared byte for byte:
  format_table(header, rows)   a table padded like prettier pads it
  wrap(text)                   a paragraph wrapped at 80 columns
  block(name, lines)           a generated block between two HTML comments
  find_block(text, name)       that block inside a page, markers included
  replace_block(text, name, b) the page with that block replaced
"""

from dataclasses import dataclass, field
from pathlib import Path

import yaml
from markdown_it import MarkdownIt
from mdit_py_plugins.front_matter import front_matter_plugin

CODE = "CODE"  # stands in for a code span in plain()
WIDTH = 80  # prettier --print-width in .pre-commit-config.yaml

_PARSER = MarkdownIt("commonmark").enable("table").use(front_matter_plugin)


@dataclass
class Doc:
    path: Path
    tokens: list
    meta: dict = field(default_factory=dict)  # YAML front matter
    meta_error: str = ""  # set when the front matter is not valid YAML


def read(path):
    tokens = _PARSER.parse(Path(path).read_text(encoding="utf-8"))
    doc = Doc(Path(path), tokens)
    if tokens and tokens[0].type == "front_matter":
        try:
            meta = yaml.safe_load(tokens[0].content)
        except yaml.YAMLError as e:
            doc.meta_error = str(e).splitlines()[0]
        else:
            if isinstance(meta, dict):
                doc.meta = meta
            else:
                doc.meta_error = "front matter is not a mapping"
    return doc


def line_of(token):
    """1-based first line of a block token, or 0 if it has none."""
    return token.map[0] + 1 if token.map else 0


def children(inline):
    """Yield (line, child) for an inline token; breaks advance the line."""
    line = line_of(inline)
    for child in inline.children or []:
        yield line, child
        if child.type in ("softbreak", "hardbreak"):
            line += 1


def plain(inline):
    """Prose of an inline token: text and link text, code spans as CODE."""
    out = []
    for _, child in children(inline):
        if child.type == "text":
            out.append(child.content)
        elif child.type == "code_inline":
            out.append(CODE)
        elif child.type == "image":
            out.append(child.content)
        elif child.type in ("softbreak", "hardbreak", "html_inline"):
            out.append(" ")
    return "".join(out).strip()


def sections(doc):
    """{title: tokens} for each `##` heading; tokens run to the next one."""
    out, current = {}, None
    tokens = doc.tokens
    for i, token in enumerate(tokens):
        if token.type == "heading_open" and token.tag == "h2":
            current = plain(tokens[i + 1])
            out[current] = []
        elif current is not None:
            out[current].append(token)
    return out


def heading_lines(doc, level="h2"):
    """[(line, title)] of the headings at one level, in order."""
    tokens = doc.tokens
    return [
        (line_of(t), plain(tokens[i + 1]))
        for i, t in enumerate(tokens)
        if t.type == "heading_open" and t.tag == level
    ]


def table(tokens):
    """Rows of the first table in tokens, as (line, [plain cell text])."""
    rows, row, inside = [], None, False
    for i, token in enumerate(tokens):
        if token.type == "table_open":
            inside = True
        elif token.type == "table_close":
            break
        elif inside and token.type == "tr_open":
            row = (line_of(token), [])
            rows.append(row)
        elif inside and token.type in ("th_open", "td_open"):
            row[1].append(plain(tokens[i + 1]))
    return rows


def format_table(header, rows):
    """Lines of a Markdown table, padded the way prettier pads it."""
    widths = [
        max(3, len(header[c]), *(len(r[c]) for r in rows)) for c in range(len(header))
    ]

    def line(cells):
        return "| " + " | ".join(s.ljust(w) for s, w in zip(cells, widths)) + " |"

    return [line(header), line(["-" * w for w in widths])] + [line(r) for r in rows]


def wrap(text):
    """A paragraph wrapped at WIDTH. Like prettier, it breaks only at spaces
    and never inside a code span."""
    atoms = []
    for word in text.split():
        if atoms and atoms[-1].count("`") % 2:
            atoms[-1] += " " + word  # still inside a code span
        else:
            atoms.append(word)
    lines = []
    for atom in atoms:
        if lines and len(lines[-1]) + 1 + len(atom) <= WIDTH:
            lines[-1] += " " + atom
        else:
            lines.append(atom)
    return "\n".join(lines)


def _markers(name):
    return f"<!-- {name}:begin -->", f"<!-- {name}:end -->"


def block(name, lines):
    """A generated block. Hand-written text may surround it on the page."""
    begin, end = _markers(name)
    return "\n".join([begin, "", *lines, "", end])


def find_block(text, name):
    begin, end = _markers(name)
    a = text.index(begin)
    return text[a : text.index(end, a) + len(end)]


def replace_block(text, name, new):
    return text.replace(find_block(text, name), new)
