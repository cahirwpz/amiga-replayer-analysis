"""Stream state that several player specs share.

The glossary's controller kinds (docs/glossary.md) are words for cards.
Only kinds with shared logic have a class here.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum, auto
from typing import ClassVar


@dataclass
class Countdown:
    """Counts ticks down and reloads from `speed`.

    With `BITS` set, the counter wraps like a register of that width,
    so a speed of 0 lasts 2**BITS ticks.
    """

    BITS: ClassVar[int | None] = None

    counter: int = 0  # ticks to the next step
    speed: int = 1  # counter reload

    def due(self) -> bool:
        """Count one tick; True when the counter reloads."""
        self.counter -= 1
        if self.BITS is not None:
            self.counter &= (1 << self.BITS) - 1
        if self.counter > 0:
            return False
        self.counter = self.speed
        return True


@dataclass
class CommandList(Countdown):
    """Opcodes with jumps and waits, but no conditions or calls.

    What a wait counts differs per player; the spec says.
    """

    pos: int = 0
    wait: int = 0

    def jump(self, pos: int) -> None:
        """Move to `pos` and drop the wait; the counter runs on."""
        self.pos, self.wait = pos, 0


class Mode(Enum):
    OFF = auto()
    ONCE = auto()
    LOOP = auto()


@dataclass
class TableWalker:
    """Steps through a table: off, once or looping."""

    table: Sequence[int] = ()
    pos: int = 0
    mode: Mode = Mode.OFF

    def step(self) -> int | None:
        """The next value; None when off. ONCE stops at the end."""
        if self.mode == Mode.OFF:
            return None
        value = self.table[self.pos]
        self.pos += 1
        if self.pos == len(self.table):
            if self.mode == Mode.ONCE:
                self.mode = Mode.OFF
            self.pos = 0
        return value
