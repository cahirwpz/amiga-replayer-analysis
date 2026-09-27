"""A CIA timer, as replayers use it for tempo.

One timer in continuous mode; that is all MED needs. The chip's second
timer, one-shot mode and interrupt control register are left out.
Source: Minimig-AGA_MiSTer 3ab91cd, rtl/cia_timera.v and minimig.v.
"""

from collections.abc import Callable
from dataclasses import dataclass

from hardware.clock import Clock

E_DIVIDER = 5  # CCK per timer count: the E clock, 709379 Hz on PAL


@dataclass
class CiaTimer:
    """Counts down once per E-clock count and interrupts at underflow.

    The underflow comes on the count after zero, so the period is
    latch + 1 counts. At underflow the counter reloads from the latch, so
    a new latch takes effect at the next underflow. CIA-B interrupts at
    CPU level 6, CIA-A at level 2.
    """

    clock: Clock
    on_underflow: Callable[[], None] | None = None  # the replayer's play routine
    latch: int = 0xFFFF
    running: bool = False

    def set_latch(self, value: int) -> None:
        self.latch = value & 0xFFFF

    def start(self) -> None:
        """Load the counter from the latch and count."""
        if not self.running:
            self.running = True
            self.schedule()

    def schedule(self) -> None:
        delay = (self.latch + 1) * E_DIVIDER
        self.clock.at(self.clock.now + delay, self.underflow)

    def underflow(self) -> None:
        self.schedule()  # reload from the latch and count on
        if self.on_underflow is not None:
            self.clock.request_interrupt(self.on_underflow)
