"""What a replayer runs on: the time, Paula and the tick sources.

Amiga is the Clock that every part uses. A replayer spec takes an Amiga
and sets the handler of the tick source it uses: the CIA timer or the
vertical blank.
"""

import sched
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import IntEnum

from hardware.cia import CiaTimer
from hardware.paula import Paula
from hardware.vblank import VerticalBlank


class Priority(IntEnum):
    """Order of events at the same CCK: hardware events such as DMA fetches
    and timer underflows, then interrupts, then other CPU work."""

    HARDWARE = 0
    INTERRUPT = 1
    CPU = 2


@dataclass
class Amiga:
    _now: int = field(default=0, init=False)  # CCK since start
    queue: sched.scheduler = field(init=False)
    paula: Paula = field(init=False)
    timer: CiaTimer = field(init=False)  # e.g. CIA-B timer A
    vblank: VerticalBlank = field(init=False)

    def __post_init__(self) -> None:
        self.queue = sched.scheduler(lambda: self._now, no_waiting)
        self.paula = Paula(self)
        self.timer = CiaTimer(self)
        self.vblank = VerticalBlank(self)

    @property
    def now(self) -> int:
        """Read-only: only step() and run() move time."""
        return self._now

    def schedule(
        self, time: int, priority: Priority, action: Callable[[], None]
    ) -> None:
        if time < self.now:
            raise ValueError(f"event at {time} is before now, {self.now}")
        self.queue.enterabs(time, priority, action)

    def after(self, delay: int, priority: Priority, action: Callable[[], None]) -> None:
        self.schedule(self.now + delay, priority, action)

    def at(self, time: int, action: Callable[[], None]) -> None:
        """Clock: a hardware event."""
        self.schedule(time, Priority.HARDWARE, action)

    def request_interrupt(self, handler: Callable[[], None]) -> None:
        """Clock: an interrupt handler, after this CCK's hardware events."""
        self.schedule(self.now, Priority.INTERRUPT, handler)

    def step(self) -> int | None:
        """Advance to the next scheduled event and run every event due at
        that CCK, including those it schedules there. Returns the new time,
        or None if nothing is scheduled."""
        if self.queue.empty():
            return None
        self._now = int(self.queue.queue[0].time)
        self.queue.run(blocking=False)
        return self.now

    def run(self, until: int) -> None:
        """Run every event up to `until`, then stop the clock there."""
        while (delay := self.queue.run(blocking=False)) is not None:
            if self.now + delay > until:
                break
            self._now += int(delay)  # the next event; none is skipped
        self._now = until


def no_waiting(delay: float) -> None:
    """Time moves only by step() and run(), which never skip an event.

    sched calls this with 0 after each event; any real wait is a bug.
    """
    if delay:
        raise RuntimeError("the event queue runs only without blocking")
