"""TFMX 7V: TFMX Pro with voices 4-7 mixed into channel 3. TFMX 7V_v4.asm.

Card: players/TFMX-7V.md, a delta card on TFMX Pro. Level 2: the control
flow runs. Only the mixer is modelled; the rest is specs/tfmx_pro.py.
Each CamelCase function is a new name in data/annot/TFMX-7V.yaml; each
CamelCase class is in its `types:`.
"""

from dataclasses import dataclass, field

from hardware import paula
from hardware.clock import Clock
from specs import tfmx_pro

MIXED = range(4, 8)  # voices 4-7 write FakeChannel registers
MIX_CHANNEL = 3  # Paula channel 3 plays the mixed buffer
SHORT_LOOP = 32  # words: shorter loops play the silent buffer
MIN_SLOW = -32  # SlowDown: percent, at least -32
MAX_VOLUME = 63  # a mixed voice's volume is clamped here
MAX_BYTES = 480 + 792  # BufferBytes: one buffer
SILENT_WORDS = MAX_BYTES // 2 - 32  # the silent buffer's loop
CLIP_EDGE = 384  # ClipTable: 384 × -128, a 256-byte ramp, 384 × +127
MIX_PERIODS = (  # MixPeriodTable: channel 3's period for 0..28 kHz
    *(3580, 3580, 1790, 1193, 895, 716, 597, 511, 447, 398, 358, 325, 298),
    *(275, 256, 239, 224, 211, 199, 188, 179, 170, 163, 156, 149, 143, 138),
    *(133, 128),
)


@dataclass
class FakeChannel(paula.Channel):  # Voice1Registers: registers in RAM
    """What voices 4-7 write instead of Paula. The instrument program code
    does not see a difference. The mixer reads these fields once per tick."""

    restart: bool = True  # v7wset: DMA was off; the next on restarts
    loop: bytes = b""  # v7loopv, v7loopd: taken at the next wrap
    source: bytes = b""  # the bytes being read
    position: int = 0  # MixPosition: 16.16, negative, counts up to the end
    step: int = 0  # v7freq: 16.16 bytes per mixed byte

    def enable(self) -> None:
        self.dma = True  # DmaFlags, not DMACON

    def disable(self) -> None:
        self.dma = False


@dataclass
class Mixer:  # MixerState, MixerOn, MixRateIndex, SlowDown
    on: bool = False
    rate: int = 16  # MixRateIndex: kHz, an index into MIX_PERIODS
    slow: int = 0  # SlowDown: percent added to the tick's length
    bytes_per_tick: int = 0
    period: int = 0  # channel 3's period for the mix rate
    buffers: list[bytearray] = field(
        default_factory=lambda: [bytearray(MAX_BYTES), bytearray(MAX_BYTES)]
    )  # NewBuffer, OldBuffer
    silence: bytes = bytes(MAX_BYTES)  # SilentBuffer, cleared by MixOff
    volume: list[bytes] = field(default_factory=list)  # VolumeTables
    clip: bytes = b""  # ClipTable


@dataclass
class Module7V(tfmx_pro.Module):  # SongState with the v7 fields
    mixer: Mixer = field(default_factory=Mixer)


def new_voices(clock: Clock, paula_: paula.Paula) -> list[tfmx_pro.Voice]:
    """FakeRegisters: voices 0-3 play Paula; voices 4-7 write RAM."""
    voices = [tfmx_pro.Voice(channel) for channel in paula_.channels]
    voices += [tfmx_pro.Voice(FakeChannel(number, clock)) for number in MIXED]
    return voices


def fakes(module: Module7V) -> list[FakeChannel]:
    channels = [voice.channel for voice in module.voices[MIXED.start :]]
    assert all(isinstance(c, FakeChannel) for c in channels)
    return channels  # type: ignore[return-value]


def HookChannel3(module: Module7V) -> None:
    """The whole replay runs from channel 3's audio interrupt, not a timer."""
    mix = module.amiga.paula.channels[MIX_CHANNEL]
    mix.on_irq(lambda channel: MixTick(module))


def MixOn(module: Module7V) -> None:
    """Bytes per tick = rate × 20 × (100 + slow) / 100, rounded to even:
    one 50 Hz tick of sound. `slow` stretches it, so the tick slows."""
    mixer = module.mixer
    mixer.slow = max(mixer.slow, MIN_SLOW)
    mixer.bytes_per_tick = (mixer.rate * 20 * (100 + mixer.slow) // 100 + 1) & ~1
    mixer.period = MIX_PERIODS[mixer.rate]
    channel = module.amiga.paula.channels[MIX_CHANNEL]
    channel.period = mixer.period
    channel.set_volume(0)
    # two words, so the first interrupt, and the first mix, come at once
    channel.queue(paula.Sample(bytes(mixer.buffers[0][:4])))
    for fake in fakes(module):
        FakeDma(mixer, fake)
    mixer.on = True


def MixOff(module: Module7V) -> None:
    """Channel 3 becomes a plain voice again. The mixed voices stop and
    point at the silent buffer."""
    module.mixer.on = False
    tfmx_pro.StopVoice(module, MIX_CHANNEL)
    for fake in fakes(module):
        fake.dma, fake.step, fake.restart = False, 0, False
        fake.source = fake.loop = module.mixer.silence
        fake.position = -len(fake.source) << 16


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
    """Channel 3 has just started the buffer mixed last tick. The mixer
    fills the other one, queues it for the next pass, then runs the
    replay's tick. The real code writes AUDxLC first; Paula takes it only
    at the next reload, after the mix. The model's Paula copies, so it
    queues after the mix."""
    mixer = module.mixer
    for fake in fakes(module):
        VolumeAndStep(mixer, fake)
    for fake in fakes(module):
        FakeDma(mixer, fake)
    mixer.buffers.reverse()
    buffer = mixer.buffers[0]
    MixLoop(mixer, fakes(module), buffer)
    channel = module.amiga.paula.channels[MIX_CHANNEL]
    channel.queue(paula.Sample(bytes(buffer[: mixer.bytes_per_tick])))
    TickFromMixer(module)


def TickFromMixer(module: Module7V) -> None:
    tfmx_pro.PlayTick(module)


def VolumeAndStep(mixer: Mixer, fake: FakeChannel) -> None:
    """Step = mix period / voice period, in 16.16. A period of 0 leaves
    both volume and step as they are."""
    if not fake.period:
        return
    fake.volume = min(fake.volume & 0xFF, MAX_VOLUME)
    quotient = ((mixer.period << 11) // fake.period) & 0xFFFF  # divu
    fake.step = quotient << 5


def FakeDma(mixer: Mixer, fake: FakeChannel) -> None:
    """DMA off: step 0, and the next on restarts. DMA on: the registers
    become the loop, taken at the next wrap. After a restart, at once."""
    if not fake.dma:
        fake.step, fake.restart = 0, True
        return
    fake.loop = ShortLoopSilent(mixer, fake)
    if fake.restart:
        fake.restart = False
        fake.source = fake.loop
        fake.position = -len(fake.source) << 16


def ShortLoopSilent(mixer: Mixer, fake: FakeChannel) -> bytes:
    """Loops under 32 words play the silent buffer, so short synth waves
    are mute on voices 4-7."""
    if fake.length < SHORT_LOOP or fake.location is None:
        return mixer.silence[: 2 * SILENT_WORDS]
    return fake.location.data[: 2 * (fake.length & 0x3FFF)]


def MixLoop(mixer: Mixer, channels: list[FakeChannel], buffer: bytearray) -> None:
    """Per mixed byte, each voice: read a byte, look it up in the table
    of its volume, step on. At the loop's end, the latched loop takes
    over. The four table bytes are summed and clipped, not divided: one
    voice alone plays at full level. Wanted Team's loop takes 254 cycles
    per byte; the original, 268."""
    for i in range(mixer.bytes_per_tick):
        total = 0
        for fake in channels:
            byte = fake.source[(fake.position >> 16) + len(fake.source)]
            total += mixer.volume[fake.volume][byte]
            fake.position += fake.step
            if fake.position >= 0:  # past the end: the loop takes over
                fake.position -= len(fake.loop) << 16
                fake.source = fake.loop
        buffer[i] = mixer.clip[total]


def BuildMixTables(mixer: Mixer) -> None:
    """64 volume tables: a byte times volume / 64, offset by $80, so four
    of them sum to 0..1020 around 512. The clip table maps that sum to a
    signed byte: 384 × -128, a ramp, 384 × +127."""
    mixer.volume = [
        bytes(((signed(b) * volume) >> 6 ^ 0x80) & 0xFF for b in range(256))
        for volume in range(64)
    ]
    ramp = bytes(range(0x80, 0x100)) + bytes(range(0x80))
    mixer.clip = bytes([0x80] * CLIP_EDGE) + ramp + bytes([0x7F] * CLIP_EDGE)


def signed(byte: int) -> int:
    return byte - 256 if byte >= 0x80 else byte


def WaitLoopsOff(module: tfmx_pro.Module, voice: tfmx_pro.Voice, s: bytes) -> bool:
    """$1a reads on, on every voice: a program cannot wait for sample
    passes. The handler and its interrupt are commented out. Guess: the
    mixed voices raise no audio interrupt, and the mixer takes channel
    3's."""
    return tfmx_pro.MacroNext(module, voice, s)


MACRO_OPCODES = list(tfmx_pro.MACRO_OPCODES)
MACRO_OPCODES[0x1A] = WaitLoopsOff
