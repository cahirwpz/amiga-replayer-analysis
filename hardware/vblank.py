"""The vertical blank interrupt, as replayers use it for a fixed tick."""

from collections.abc import Callable
from dataclasses import dataclass

from hardware.clock import FRAME_CCK, Clock


@dataclass
class VerticalBlank:
    """The vertical blank interrupt: once per frame, 50 Hz on PAL."""

    clock: Clock
    handler: Callable[[], None] | None = None

    def start(self) -> None:
        self.clock.at(self.clock.now + FRAME_CCK, self.frame)

    def frame(self) -> None:
        """The beam reaches the end of the frame."""
        if self.handler is not None:
            self.clock.request_interrupt(self.handler)
        self.start()
