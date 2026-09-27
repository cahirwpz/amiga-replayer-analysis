"""TFMX 7V: TFMX Pro with voices 4-7 mixed into channel 3. TFMX 7V_v4.asm.

Card: players/TFMX-7V.md, a delta card on TFMX Pro. Level 2: the control
flow runs; leaf math is a stub. Only the mixer is modelled; the rest is
specs/tfmx_pro.py. Each CamelCase function is a label in
data/annot/TFMX-7V.yaml; each CamelCase class is in its `types:`.
"""

from dataclasses import dataclass, field

from hardware import paula
from hardware.clock import Clock
from specs import tfmx_pro

MIXED = range(4, 8)  # voices 4-7 write FakeChannel registers
MIX_CHANNEL = 3  # Paula channel 3 plays the mixed buffer
SHORT_LOOP = 32  # words: shorter loops play the silent buffer
MIN_SLOW = -32  # v7slodo: percent, at least -32
MAX_VOLUME = 63  # a mixed voice's volume is clamped here


@dataclass
class FakeChannel(paula.Channel):  # voice1dat: registers in RAM
    """What voices 4-7 write instead of Paula. The macro engine does not
    see a difference. The mixer reads these fields once per tick."""

    restart: bool = True  # v7wset: DMA was off; the next on restarts
    offset: int = 0  # v7regstore: the position, negative up to the end
    step: int = 0  # v7freq: 16.16 bytes per mixed byte

    def enable(self) -> None:
        self.dma = True  # flagtab, not DMACON

    def disable(self) -> None:
        self.dma = False


@dataclass
class Mixer:  # v7field, v7flag, v7mixrate, v7slodo
    on: bool = False
    rate: int = 0  # v7mixrate: an index into v7KHztable
    slow: int = 0  # v7slodo: percent added to the tick's length
    bytes_per_tick: int = 0
    period: int = 0  # channel 3's period for the mix rate
    buffers: list[bytearray] = field(default_factory=lambda: [bytearray(), bytearray()])
    silence: bytearray = field(default_factory=bytearray)  # v7buffer3


@dataclass
class Module7V(tfmx_pro.Module):  # CHfield0 with the v7 fields
    mixer: Mixer = field(default_factory=Mixer)


def new_voices(clock: Clock, paula_: paula.Paula) -> list[tfmx_pro.Voice]:
    """FakeRegisters: voices 0-3 play Paula; voices 4-7 write RAM."""
    voices = [tfmx_pro.Voice(channel) for channel in paula_.channels]
    voices += [tfmx_pro.Voice(FakeChannel(number, clock)) for number in MIXED]
    return voices


def HookChannel3(module: Module7V) -> None:
    """The whole replay runs from channel 3's audio interrupt, not a timer."""
    mix = module.amiga.paula.channels[MIX_CHANNEL]
    mix.on_irq(lambda channel: MixTick(module))


def MixOn(module: Module7V) -> None:
    """Bytes per tick = rate × 20 × (100 + slow) / 100, rounded to even:
    one 50 Hz tick of sound. `slow` stretches it, so the tick slows."""
    mixer = module.mixer
    mixer.slow = max(mixer.slow, MIN_SLOW)
    mixer.bytes_per_tick = mix_bytes(mixer.rate, mixer.slow)
    mixer.period = mix_period(mixer.rate)
    channel = module.amiga.paula.channels[MIX_CHANNEL]
    channel.period = mixer.period
    channel.set_volume(0)
    channel.queue(paula.Sample(bytes(mixer.buffers[0])))
    for voice in module.voices[MIXED.start :]:
        assert isinstance(voice.channel, FakeChannel)
        FakeDma(mixer, voice.channel)
    mixer.on = True


def MixOff(module: Module7V) -> None:
    """Channel 3 becomes a plain voice again. The mixed voices stop."""
    module.mixer.on = False
    tfmx_pro.StopVoice(module, MIX_CHANNEL)
    for voice in module.voices[MIXED.start :]:
        assert isinstance(voice.channel, FakeChannel)
        voice.channel.dma, voice.channel.step = False, 0


def SwitchMixing(module: Module7V, voice: int) -> None:
    """Runs first in NoteToVoice. A note to voice 3 stops mixing; a note
    to voices 4-7 starts it."""
    if voice == MIX_CHANNEL and module.mixer.on:
        MixOff(module)
    elif voice in MIXED and not module.mixer.on:
        MixOn(module)


def CmdMixSlow(module: Module7V, position: bytes) -> bool:
    """Position command 3: word 3 sets `slow`, then mixing restarts."""
    slow = int.from_bytes(position[6:8], "big", signed=True)
    if slow >= 0:
        module.mixer.slow = slow
    MixOn(module)
    module.position += 1
    return True


def FadeToChannel3(module: Module7V, voice: tfmx_pro.Voice) -> None:
    """While mixing, the fade level goes to channel 3's Paula volume. A
    mixed voice keeps its own volume, unfaded."""
    channel = module.amiga.paula.channels[MIX_CHANNEL]
    channel.set_volume(module.fade.level)
    voice.channel.set_volume(voice.volume)


def MixTick(module: Module7V) -> None:
    """Channel 3 plays the buffer filled last tick. The mixer fills the
    other one, then runs the replay's tick."""
    mixer = module.mixer
    channel = module.amiga.paula.channels[MIX_CHANNEL]
    channel.queue(paula.Sample(bytes(mixer.buffers[1])))
    fakes = [v.channel for v in module.voices[MIXED.start :]]
    for fake in fakes:
        assert isinstance(fake, FakeChannel)
        VolumeAndStep(mixer, fake)
    for fake in fakes:
        assert isinstance(fake, FakeChannel)
        FakeDma(mixer, fake)
    mixer.buffers.reverse()
    MixLoop(mixer, fakes)
    TickFromMixer(module)


def TickFromMixer(module: Module7V) -> None:
    tfmx_pro.PlayTick(module)


def VolumeAndStep(mixer: Mixer, fake: FakeChannel) -> None:
    """Step = mix period / voice period. A period of 0 leaves both."""
    if not fake.period:
        return
    fake.volume = min(fake.volume & 0xFF, MAX_VOLUME)
    fake.step = (mixer.period << 16) // fake.period


def FakeDma(mixer: Mixer, fake: FakeChannel) -> None:
    """DMA off: step 0, and the next on restarts. DMA on: the registers
    become the loop, taken at the next wrap. After a restart, at once."""
    if not fake.dma:
        fake.step, fake.restart = 0, True
        return
    ShortLoopSilent(mixer, fake)
    if fake.restart:
        fake.restart = False
        fake.offset = -2 * fake.length


def ShortLoopSilent(mixer: Mixer, fake: FakeChannel) -> None:
    """Loops under 32 words play the silent buffer, so short synth waves
    are mute on voices 4-7."""
    if fake.length < SHORT_LOOP:
        fake.location = paula.Sample(bytes(mixer.silence))


def MixLoop(mixer: Mixer, fakes: list[paula.Channel]) -> None:
    """Per mixed byte: each voice's byte through its volume table, the
    four summed, the sum clipped. No division. 254 cycles per byte."""
    # see BuildMixTables


def BuildMixTables() -> None:
    """64 volume tables of 256 bytes: sample × volume / 64. A clip table
    of 1024 bytes: -128 × 384, a ramp, +127 × 384."""


def mix_bytes(rate: int, slow: int) -> int: ...  # v7KHztable


def mix_period(rate: int) -> int: ...  # v7KHztable
