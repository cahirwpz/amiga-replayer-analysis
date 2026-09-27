"""Time for the hardware model: colour clocks and the Clock that parts use.
The event queue and its order live in hardware/amiga.py:Amiga.

Time counts CCK. Replay routines run as interrupt handlers at one instant;
a busy wait schedules its continuation.

Grain: one scanline. Out of scope: bus contention, 227/228-CCK lines.
"""

from collections.abc import Callable
from typing import Protocol

CCK_HZ = 3546895  # PAL colour clock
LINE_CCK = 227  # colour clocks per scanline
FRAME_LINES = 312  # scanlines per PAL frame
FRAME_CCK = LINE_CCK * FRAME_LINES


class Clock(Protocol):
    """The time, and the two ways a part acts. Amiga implements it."""

    @property
    def now(self) -> int: ...

    def at(self, time: int, action: Callable[[], None]) -> None:
        """A hardware event, e.g. a DMA fetch or a timer underflow."""

    def request_interrupt(self, handler: Callable[[], None]) -> None:
        """Run a CPU interrupt handler after this CCK's hardware events."""
