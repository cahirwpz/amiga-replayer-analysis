"""Controller kinds, as docs/glossary.md defines them.

A player's spec subclasses these. The class it picks is the controller's
Kind. Where a field lives (voice, instrument, score) is its owner.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum, auto


@dataclass
class CommandList:
    """Opcodes with jumps and waits, but no conditions or calls.

    It runs every `speed` ticks. A wait counts visits, not ticks. A jump
    from elsewhere moves `pos` and clears `wait`; the counter runs on, so
    the target acts at its next visit.
    """

    pos: int = 0
    wait: int = 0  # visits left
    counter: int = 0  # ticks to the next visit
    speed: int = 1  # counter reload

    def due(self) -> bool:
        """Count one tick; True when the list visits."""
        self.counter -= 1
        if self.counter > 0:
            return False
        self.counter = self.speed
        return True

    def waiting(self) -> bool:
        """Count one visit off a wait; True while the wait lasts."""
        if self.wait == 0:
            return False
        self.wait -= 1
        return self.wait > 0

    def jump(self, pos: int) -> None:
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


class StateMachine:
    """Changes its state by rules, e.g. an envelope or a vibrato."""


# A lookup maps an input to a value and has no state: a plain function.


class Program(CommandList):
    """Opcodes with conditions or calls."""
