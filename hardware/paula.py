"""Paula, the Amiga sound chip, as replayers see it.

Prose companion: docs/paula.md. Facts from ghostown-spookytown-2's
docs/paula.md, a digest of Minimig-AGA 20260220, WinUAE and the Amiga
Hardware Reference Manual. Only facts that shape replayer design are
modelled; sample bytes are not played. Time: hardware/clock.py:Clock.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Flag, auto

from hardware.clock import CCK_HZ, LINE_CCK, Clock

MIN_PERIOD = 124  # CCK: one word per line limits a channel to about 28.6 kHz
MAX_VOLUME = 64
CHANNELS = 4
LEFT = (0, 3)  # fixed stereo: channels 0 and 3 left, 1 and 2 right
RIGHT = (1, 2)
SLOT_CCK = (0x0E, 0x10, 0x12, 0x14)  # each channel's DMA slot in a line
VOLUME_WORD_BITS = 7  # an attach volume word: V6-V0
PERIOD_WORD_BITS = 16


@dataclass
class Sample:
    """8-bit signed bytes, word-aligned, even length."""

    data: bytes


class Attach(Flag):
    """A channel's ADKCON attach bits: ATVOL `0x01 << n`, ATPER `0x10 << n`.
    Channel n modulates channel n+1.

    Unresolved: the manual says either bit silences the modulator; WinUAE
    plays an ATPER modulator's words as audio. The manual says with both
    bits, words alternate between volume and period; WinUAE fetches for one
    mode only. This model follows the manual.
    """

    NONE = 0
    VOLUME = auto()
    PERIOD = auto()


def next_slot(number: int, earliest: int) -> int:
    """The first DMA slot of channel `number` at or after `earliest`.

    Agnus gives each channel a fixed slot per line, so channels never
    compete: one word per channel per line.
    """
    slot = earliest - earliest % LINE_CCK + SLOT_CCK[number]
    return slot if slot >= earliest else slot + LINE_CCK


@dataclass
class Channel:
    """One audio channel: registers, counters, DMA state machine, interrupt.

    Source for the state machine: Minimig-AGA_MiSTer 3ab91cd,
    rtl/paula_audio_channel.v. Grain: one word, not one byte.

    `location` and `length` are the queued registers AUDxLC and AUDxLEN.
    `playing`, `pointer` and `count` are the live pointer and counter. The
    channel always wraps: there is no loop register and no one-shot mode.

    A channel is independent. It owns its DMACON, INTENA and INTREQ bits
    and meets the other channels only through its attach link. In
    hardware, the four channels share one CPU interrupt, level 4, whose
    handler tests the INTREQ bits. The per-channel handler here is our
    convenience.
    """

    number: int
    clock: Clock
    location: Sample | None = None  # AUDxLC
    length: int = 0  # AUDxLEN, in words
    playing: Sample | None = None
    pointer: int = 0  # words into `playing`
    count: int = 0  # words left
    period: int = 0  # AUDxPER: CCK per byte
    volume: int = 0  # AUDxVOL, after set_volume
    dma: bool = False  # this channel's DMACON bit
    armed: bool = False  # DMA enabled; the start reload is pending
    idle: bool = True  # no word is playing; only now can DMA on restart
    irq_enabled: bool = False  # this channel's INTENA bit
    irq_requested: bool = False  # this channel's INTREQ bit; the CPU clears it
    on_interrupt: "Callable[[Channel], None] | None" = None  # see on_irq
    mode: Attach = Attach.NONE  # set by ADKCON; on channel 3 it only mutes
    modulates: "Channel | None" = None  # the next channel, while attached
    volume_next: bool = True  # with both attach bits: the next word's use

    def queue(self, sample: Sample) -> None:
        """Write AUDxLC and AUDxLEN. The live pointer takes them at the next
        reload, never at once."""
        self.location = sample
        self.length = len(sample.data) // 2

    def enable(self) -> None:
        """Set this channel's DMACON bit.

        From idle, it arms the start reload; the next slot takes AUDxLC.
        Before the channel is idle, it plays on with no restart, so
        replayers wait after DMA off. Setting a set bit does nothing.
        """
        if self.dma:
            return
        self.dma = True
        if self.idle:
            self.idle, self.armed = False, True
            self.fetch_at(self.clock.now)

    def play(self, sample: Sample) -> None:
        self.queue(sample)
        self.enable()

    def disable(self) -> None:
        """Clear this channel's DMACON bit. The channel finishes its word,
        up to 2 × period CCK, then goes idle.

        Left out: with its INTREQ bit clear, the channel plays one more
        word and requests an interrupt first.
        """
        self.dma = self.armed = False

    def set_volume(self, value: int) -> None:
        """Volume gates the output by PWM; it does not multiply. Of the
        register's 7 bits, bit 6 forces the maximum."""
        self.volume = MAX_VOLUME if value & 0x40 else value & 0x3F

    def rate(self) -> int:
        """Bytes per second. Below MIN_PERIOD, DMA cannot keep up."""
        return CCK_HZ // self.period if self.period else 0

    def fetch_at(self, earliest: int) -> None:
        """Request a word; Agnus serves it at the channel's next slot."""
        slot = next_slot(self.number, earliest)
        self.clock.at(slot, self.fetch)

    def fetch(self) -> None:
        """One DMA slot: the start reload, or one word."""
        if not self.dma:
            self.idle = True  # the word is done and DMA is off
            return
        if self.armed:
            # The start reload: this first word only reloads the pointer and
            # is dropped; sound starts on the second word. A queue() before
            # this slot is taken here, so the note plays from the loop point.
            self.armed = False
            self.reload()
            self.pointer, self.count = 1, self.length - 1
            self.fetch_at(self.clock.now + 1)
            return
        word = self.read_word()
        if self.count == 1:
            self.reload()  # rides on the last word's fetch, not the next one
        else:
            self.pointer += 1
            self.count -= 1
        if self.modulates is not None:
            self.modulate(word)
        self.fetch_at(self.clock.now + 2 * self.period)

    def reload(self) -> None:
        """Copy AUDxLC and AUDxLEN to the live pointer and counter, and
        request an interrupt."""
        self.playing = self.location
        self.pointer, self.count = 0, self.length
        self.irq_requested = True
        if self.irq_enabled:
            self.clock.request_interrupt(self.interrupt)

    def interrupt(self) -> None:
        """Run the handler once per request. Clearing INTREQ here stands in
        for the handler's acknowledge."""
        if not self.irq_requested or self.on_interrupt is None:
            return
        self.irq_requested = False
        self.on_interrupt(self)

    def on_irq(self, handler: "Callable[[Channel], None]") -> None:
        """Enable this channel's interrupt with its handler."""
        self.on_interrupt = handler
        self.irq_enabled = True

    def read_word(self) -> int:
        if self.playing is None:
            return 0
        at = self.pointer * 2
        return int.from_bytes(self.playing.data[at : at + 2], "big")

    def modulate(self, word: int) -> None:
        """One word per fetch goes to the next channel's volume or period."""
        target = self.modulates
        assert target is not None
        both = Attach.VOLUME in self.mode and Attach.PERIOD in self.mode
        use_volume = Attach.VOLUME in self.mode and (not both or self.volume_next)
        if both:
            self.volume_next = not self.volume_next
        if use_volume:
            target.set_volume(word & ((1 << VOLUME_WORD_BITS) - 1))
        else:
            target.period = word


@dataclass
class Paula:
    """The four channels and ADKCON, the one register they share here."""

    clock: Clock
    channels: list[Channel] = field(init=False)

    def __post_init__(self) -> None:
        self.channels = [Channel(n, self.clock) for n in range(CHANNELS)]

    def adkcon(self, modes: list[Attach]) -> None:
        """Link channel n to n+1: 0→1, 1→2 and 2→3 only.

        A modulator costs a whole voice on its side: 0→1 and 2→3 span both
        sides, 1→2 stays on the right.
        """
        for channel, mode in zip(self.channels, modes):
            channel.mode = mode
            last = channel.number == CHANNELS - 1
            attached = mode != Attach.NONE and not last
            channel.modulates = self.channels[channel.number + 1] if attached else None
