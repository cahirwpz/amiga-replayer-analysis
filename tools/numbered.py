"""Find numbers that stand in for names in prose.

Other tools import this module; it has no command line:
  constants(spec)   {value: [names]} of a spec's module-level constants
  for_player(p)     the same for a player's spec in data/players.yaml
  find(text, consts)  (column, detail) for each number standing in a name
  layout(text)      the lines of a text that lay out a record

find() rejects:
  - a command, effect or opcode by number: "command 4", "effects 2 and 3"
  - a hex number, `$80` or `0x80`, equal to one of `consts`

It allows an offset: a hex number after `+`, or before "byte" or "bytes".
Callers allow the rest (see AGENTS.md#writing): a constant's definition
line, a comment that starts with a hex number, and the lines of layout().

A wrong name with the right value passes: only values are compared.
"""

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

KINDS = r"commands?|effects?|opcodes?|options?|events?|ops?"
NUMBER = r"(?:\$|0x)[0-9A-Fa-f]+|\d+"
BY_NUMBER = re.compile(rf"\b(?:{KINDS})\s+(?:{NUMBER})", re.IGNORECASE)
HEX = re.compile(r"(?<![\w$+])(?:\$|0x)([0-9A-Fa-f]+)\b(?!\s*`?\s*bytes?\b)")
LAYOUT = re.compile(rf"\s*(?:{NUMBER})\s")
FIELD = re.compile(rf"\s*(?:{NUMBER})\s+\w+(?:\s+\w+)?\s*")  # `$16 pos`
OPERATORS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.LShift: lambda a, b: a << b,
    ast.RShift: lambda a, b: a >> b,
    ast.BitOr: lambda a, b: a | b,
    ast.BitAnd: lambda a, b: a & b,
}


def value(node, known):
    """The int a constant expression stands for, or None."""
    if isinstance(node, ast.Constant) and type(node.value) is int:
        return node.value
    if isinstance(node, ast.Name):
        return known.get(node.id)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        v = value(node.operand, known)
        return None if v is None else -v
    if isinstance(node, ast.BinOp) and type(node.op) in OPERATORS:
        a, b = value(node.left, known), value(node.right, known)
        return None if a is None or b is None else OPERATORS[type(node.op)](a, b)
    return None


def values(node, count, known):
    """The ints an unpacked right-hand side stands for: a tuple or range()."""
    if isinstance(node, ast.Tuple):
        return [value(e, known) for e in node.elts]
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "range"
    ):
        args = [value(a, known) for a in node.args]
        if None not in args:
            return list(range(*args))
    return [None] * count


def definitions(tree):
    """(line, name, value) of each module-level constant; value may be None."""
    known: dict[str, int | None] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets, rhs = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, rhs = [node.target], node.value
        else:
            continue
        for target in targets:
            if isinstance(target, ast.Name):
                pairs = [(target.id, value(rhs, known))]
            elif isinstance(target, ast.Tuple):
                names = [getattr(e, "id", "") for e in target.elts]
                pairs = list(zip(names, values(rhs, len(names), known)))
            else:
                continue
            for name, v in pairs:
                if name.isupper():
                    known[name] = v
                    yield node, name, v


def constants(spec):
    """{value: [names]} of the int constants of a spec file."""
    tree = ast.parse(Path(spec).read_text(encoding="utf-8"))
    out: dict[int, list[str]] = {}
    for _, name, v in definitions(tree):
        if v is not None:
            out.setdefault(v, []).append(name)
    return out


def definition_lines(spec):
    """Lines of a spec that define a constant; their comments may use numbers."""
    tree = ast.parse(Path(spec).read_text(encoding="utf-8"))
    return {
        n
        for node, _, _ in definitions(tree)
        for n in range(node.lineno, node.end_lineno + 1)
    }


def for_player(player):
    """{value: [names]} of the player's spec; empty without one."""
    import players  # players imports annot, which imports this module

    spec = (players.load().get(player) or {}).get("spec")
    return constants(ROOT / spec) if spec else {}


def find(text, consts):
    """(column, detail) for each number that stands in for a name, in order."""
    found = [
        (m.start(), f"`{m.group(0)}`: name it by its constant or handler")
        for m in BY_NUMBER.finditer(text)
    ]
    for m in HEX.finditer(text):
        if names := consts.get(int(m.group(1), 16)):
            found.append((m.start(), f"`{m.group(0)}` is {' or '.join(names)}"))
    return sorted(found)


def layout(text):
    """The lines of a text that lay out a record. Either several lines
    start with an offset, or a line lists offsets and fields of one or
    two words: `4 list, $16 pos`. One line that starts with a number is
    prose."""
    lines = text.split("\n")
    starts = {line for line in lines if LAYOUT.match(line + " ")}
    lists = {
        line
        for line in lines
        if "," in line and all(FIELD.fullmatch(i) for i in line.split(","))
    }
    return (starts if len(starts) > 1 else set()) | lists
