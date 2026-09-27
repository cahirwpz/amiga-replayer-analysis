"""Paula, the Amiga sound chip, as replayers see it.

Prose companion: docs/paula.md. Only facts that shape replayer design are
modelled. A body of `...` is leaf math or hardware timing.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum, auto

CLOCK = 3546895  # PAL audio clock in Hz: sample rate = CLOCK / period
MIN_PERIOD = 124  # below this, DMA cannot fetch in time
MAX_VOLUME = 64  # volume runs 0..MAX_VOLUME, linear
CHANNELS = 4
LEFT = (0, 3)  # fixed stereo: channels 0 and 3 left, 1 and 2 right
RIGHT = (1, 2)
PAL_FRAME_HZ = 50


@dataclass
class Sample:
    """8-bit signed bytes, word-aligned, even length."""

    data: bytes


@dataclass
class Channel:
    """One of the four DMA channels: AUDxLC, AUDxLEN, AUDxPER, AUDxVOL."""

    number: int
    location: Sample | None = None  # AUDxLC: copied to the pointer at each wrap
    length: int = 0  # AUDxLEN, in words
    period: int = 0  # AUDxPER: clock divider
    volume: int = 0  # AUDxVOL
    dma: bool = False  # DMACON bit for this channel
    on_wrap: Callable[["Channel"], None] | None = None  # audio interrupt

    def play(self, sample: Sample) -> None:
        """Start DMA from the sample. The first word after start is dropped."""
        self.location = sample
        self.length = len(sample.data) // 2
        self.dma = True

    def repeat(self, sample: Sample) -> None:
        """Set the loop. It applies at the next wrap, never at once."""
        self.location = sample
        self.length = len(sample.data) // 2

    def stop(self) -> None:
        self.dma = False

    def wrap(self) -> None:
        """DMA reached the end: reload the pointer and raise the interrupt.

        The channel always loops. A one-shot sound needs a short silent loop.
        """
        if self.on_wrap is not None:
            self.on_wrap(self)

    def rate(self) -> int:
        return CLOCK // max(self.period, MIN_PERIOD)


class Attach(Enum):
    """ADKCON: a channel modulates the next one and falls silent itself."""

    NONE = auto()
    VOLUME = auto()  # its words feed the next channel's AUDxVOL
    PERIOD = auto()  # its words feed the next channel's AUDxPER
    BOTH = auto()  # words alternate: volume, period


@dataclass
class Paula:
    channels: list[Channel] = field(
        default_factory=lambda: [Channel(n) for n in range(CHANNELS)]
    )
    attach: list[Attach] = field(default_factory=lambda: [Attach.NONE] * 3)

    def attach_modulation(self, modulator: int, mode: Attach) -> None:
        """Channel n modulates channel n+1. It costs a whole voice."""
        self.attach[modulator] = mode

    def start_dma(self, mask: int) -> None:
        """DMACON set. The pointer is fetched up to a scanline later, so
        replayers wait before they write the loop pointer."""
        for channel in self.channels:
            if mask & (1 << channel.number):
                channel.dma = True


class Clock(Enum):
    """What calls the replayer's tick routine."""

    VBLANK = auto()  # once per frame, PAL_FRAME_HZ
    CIA_TIMER = auto()  # CIA timer: any rate, set by the score's tempo


@dataclass
class Timer:
    source: Clock
    ticks_per_second: int = PAL_FRAME_HZ
    tick: Callable[[], None] | None = None  # the replayer's play routine

    def set_rate(self, bpm: int) -> None:
        """CIA timers only: derive the tick rate from a tempo."""
        self.ticks_per_second = cia_rate(bpm)


def cia_rate(bpm: int) -> int: ...  # 709379 Hz CIA clock over the latch value


@dataclass
class LoopCounter:
    """Counts sample passes with the audio interrupt.

    Enables sample chaining and waits measured in sample loops instead of
    ticks. Without it, a replayer only knows the tick.
    """

    passes: int = 0
    target: int = 0
    then: Callable[[Channel], None] | None = None

    def on_wrap(self, channel: Channel) -> None:
        self.passes += 1
        if self.passes == self.target and self.then is not None:
            self.then(channel)


@dataclass
class MixBuffer:
    """Software mixing: several voices summed into one channel's buffer.

    More voices than CHANNELS need CPU mixing. The channel then plays the
    buffer as a plain sample, double-buffered at each wrap.
    """

    channel: Channel
    mix_rate: int  # bytes per second the mixer writes
    buffers: tuple[Sample, Sample]
    current: int = 0

    def on_wrap(self, channel: Channel) -> None:
        """Hand the finished half to the mixer; queue the other one."""
        self.current ^= 1
        channel.repeat(self.buffers[self.current])

    def fill(self, voices: list["MixVoice"]) -> None:
        """Sum and scale the voices into the free half."""
        free = self.buffers[self.current ^ 1]
        for voice in voices:
            resample_add(free, voice, self.mix_rate)


@dataclass
class MixVoice:
    """A voice that plays through a mixer, not its own channel."""

    sample: Sample
    position: int  # fixed-point read position
    step: int  # fixed-point: voice rate / mix rate
    volume: int


def resample_add(out: Sample, voice: MixVoice, mix_rate: int) -> None: ...
