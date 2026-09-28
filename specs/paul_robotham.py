"""Paul Robotham's replay from Starlord (MicroProse, 1994). Paul
Robotham_v1.asm, Wanted Team's adaptation. It adds two commands and one
line from the replay of Dawn Patrol.

Card: players/PaulRobotham.md. Level 2: the control flow runs. Each
CamelCase function is a new name in data/annot/PaulRobotham.yaml; each
CamelCase class is in its `types:`.

Each voice reads its own byte stream from start to end. There are no
patterns and no positions. A note byte carries a length byte: a 5-bit
value, shifted left by a 3-bit count. The pulse length scales it to
ticks, and each voice keeps the remainder of that division. Loops nest
on a stack per voice.

Voice settings hold until a command changes them: instrument, volume,
envelope table, vibrato table and depth, portamento. Vibrato adds a
share of the period, so its interval is the same on every note. A mode
byte picks legato, and whether a note restarts the envelope and the
vibrato.

The game plays sound effects on music voices. While an effect plays,
the voice's stream runs on without channel writes. The routine that
starts an effect is commented out in this source. The rest of the
effect code runs.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from hardware import paula
from hardware.amiga import DEFAULT_LATCH, Amiga

PULSE_DIVISOR = 10800  # PulseDivisor
PULSE_LENGTH = 1000  # PulseLength at load; InitSong keeps the last value
FULL = 0x3F  # volumes, envelope values and the master volume: 0 to 63
START_TICKS = 10  # every voice waits this long before its first byte
ENVELOPE_START = 3  # the envelope index at a note
ENVELOPE_STEP = 4  # the envelope index moves this far per tick
VIBRATO_SCALE = 10000  # SetVibratoDepth divides it by the depth
EMPTY = paula.Sample(bytes(16))  # EmptyLoop: the adaptation's 8 zero words
EMPTY_PERIOD = 0x100  # SwapInstrument's period for an instrument without a loop

END_BYTE, TIE, COMMAND = 0x00, 0x7F, 0x80
END, STARTED, HELD = range(3)  # what ReadStream found

# SetMode's bits
LEGATO, KEEP_ENVELOPE, KEEP_VIBRATO = 1, 2, 4

# PeriodTable: indexed by the note byte. Note 0 is the end byte, so the
# first entry is never read. Notes above 59 read past the table.
PERIODS = (
    *(0x358, 0x328, 0x2FA, 0x2D0, 0x2A6, 0x280, 0x25C, 0x23A, 0x21A, 0x1FC),
    *(0x1E0, 0x1C4, 0x1AC, 0x194, 0x17D, 0x168, 0x153, 0x140, 0x12E, 0x11D),
    *(0x10D, 0xFE, 0xF0, 0xE2, 0xD6, 0xCA, 0xBE, 0xB4, 0xA9, 0xA0, 0x97),
    *(0x8E, 0x86, 0x7F, 0x78, 0x71, 0x6B, 0x65, 0x5F, 0x5A, 0x54, 0x50),
    *(0x4B, 0x47, 0x43, 0x3F, 0x3C, 0x38, 0x35, 0x32, 0x2F, 0x2D, 0x2A),
    *(0x28, 0x25, 0x23, 0x21, 0x1F, 0x1E, 0x1C),
)


# --- Player state ------------------------------------------------------


@dataclass
class Instrument:  # Instruments: 12 bytes each
    start: int  # 0: bytes into the sample file
    length: int  # 4: words
    loop_start: int  # 6
    loop_length: int  # 10: words; 0: the empty loop


@dataclass
class Voice:  # VoiceTable: 56 bytes each
    channel: paula.Channel
    number: int
    pos: int = 0  # 0: the stream, bytes into the module
    ticks: int = START_TICKS  # 4: until the next byte is read
    vibrato_phase: int = 0  # 6
    envelope_pos: int = ENVELOPE_START  # 7
    instrument: int = 0  # 9
    vibrato_table: int = 0  # 10: bytes into the module
    envelope_table: int = 0  # 14
    loops: list[tuple[int, int]] = field(default_factory=list)  # 22: count, pos
    volume: int = 0  # 26
    ended: bool = False  # 27, bit 7
    fading: bool = False  # 27, bit 6
    vibrato_on: bool = False  # 27, bit 4
    tie: bool = False  # 27, bit 3
    portamento_on: bool = False  # 27, bit 2
    vibrato_speed: int = 1  # 28
    vibrato_divisor: int = VIBRATO_SCALE  # 30
    period: int = 0  # 32: after portamento
    target: int = 0  # 34: the note's period
    portamento_step: int = 0  # 36
    loop: paula.Sample = EMPTY  # 38: the instrument's loop
    loop_period: int = 0  # 44
    mode: int = 0  # 46: SetMode's bits
    changed: bool = False  # 47: SetInstrument ran since the last note
    remainder: int = 0  # 50: of the last length division
    fade_level: int = 0  # 54
    fade_step: int = 0  # 55
    # One bit per voice in module bytes:
    dma_pending: bool = False  # DmaPending: DMA goes on next tick
    loop_pending: bool = False  # LoopPending: the loop is queued next tick
    volume_on: bool = False  # VolumeOn: the channel's volume is written


@dataclass
class Effect:  # EffectTable: 18 bytes per voice
    sample: paula.Sample = EMPTY  # 0 and 4
    loop: paula.Sample = EMPTY  # 6 and 10
    period: int = 0  # 12: never written; see EffectTick
    ticks: int = 0  # 14: a word; 0: no effect
    volume: int = 0  # 16
    start: bool = False  # EffectStart
    dma: bool = False  # EffectDma
    queue_loop: bool = False  # EffectLoop


@dataclass
class Module:
    amiga: Amiga
    data: bytes
    samples: bytes  # the sample file
    streams: list[int] = field(default_factory=list)
    vibrato_tables: list[int] = field(default_factory=list)  # VibratoTables
    envelope_tables: list[int] = field(default_factory=list)  # EnvelopeTables
    instruments: list[Instrument] = field(default_factory=list)
    voices: list[Voice] = field(default_factory=list)  # VoiceCount of them
    effects: list[Effect] = field(default_factory=list)
    ended_voices: int = 0  # EndedVoices; the replay never reads it
    pulse_length: int = PULSE_LENGTH  # PulseLength: in 1/10800 tick
    master: int = FULL  # MasterVolume
    master_target: int = FULL  # MasterTarget
    master_step: int = 0  # MasterStep: +1 or -1; 0: no fade
    master_counter: int = 0  # MasterCounter
    master_speed: int = 1  # MasterSpeed: ticks per step
    effect_voices: int = 3  # EffectVoiceCount: effects take voices 0 to this
    marker: int = 0  # Marker: the replay never reads it
    voice_mask: int = 0xFFFFFFFF  # VoiceMask: a clear bit mutes a voice
    stop_effects: bool = False  # StopEffects: the replay never sets it
    audio_filter: bool = False


# --- Start -------------------------------------------------------------


def new_module(data: bytes, samples: bytes, amiga: Amiga) -> Module:
    """DeliTracker calls Play by its own timer."""
    module = Module(amiga, data, samples)
    InitModule(module)
    InitSong(module)
    amiga.timer.on_underflow = lambda: Play(module)
    amiga.timer.set_latch(DEFAULT_LATCH)
    return module


def InitModule(module: Module) -> None:
    """Four words: voices (1 to 4), vibrato tables, envelope tables and
    instruments. Long offsets follow, one per stream and table.
    Instruments follow them. The first envelope table comes right after
    the instruments: 254 bytes of 63, a flat envelope."""
    data = module.data
    voices, vibratos, envelopes, count = (word(data, 2 * n) for n in range(4))
    offsets = [long(data, 8 + 4 * n) for n in range(voices + vibratos + envelopes)]
    module.streams = offsets[:voices]
    module.vibrato_tables = offsets[voices : voices + vibratos]
    module.envelope_tables = offsets[voices + vibratos :]
    at = 8 + 4 * len(offsets)
    module.instruments = [
        Instrument(
            long(data, a), word(data, a + 4), long(data, a + 6), word(data, a + 10)
        )
        for a in range(at, at + 12 * count, 12)
    ]
    channels = module.amiga.paula.channels
    module.voices = [Voice(channels[n], n) for n in range(voices)]
    module.effects = [Effect() for _ in channels]


def InitSong(module: Module) -> None:
    """Each voice starts at its stream, with the first instrument and
    the first tables, volume 0 and an empty loop stack. The pending
    bits, the fade level and PulseLength keep their values."""
    for voice, stream in zip(module.voices, module.streams):
        voice.pos, voice.ticks = stream, START_TICKS
        voice.vibrato_phase, voice.envelope_pos = 0, ENVELOPE_START
        voice.instrument = voice.volume = voice.mode = voice.remainder = 0
        voice.ended = voice.fading = voice.vibrato_on = voice.tie = False
        voice.portamento_on, voice.changed = False, False
        voice.portamento_step = 0
        voice.vibrato_speed, voice.vibrato_divisor = 1, VIBRATO_SCALE
        voice.vibrato_table = module.vibrato_tables[0]
        voice.envelope_table = module.envelope_tables[0]
        voice.loops = []
    module.ended_voices = 0
    module.effects = [Effect() for _ in module.effects]


# --- Tick --------------------------------------------------------------


def Play(module: Module) -> None:
    """Each voice plays its music, or an effect while its music runs
    muted. A voice that ended stays silent. Then the master fade."""
    for voice, effect in zip(module.voices, module.effects):
        if effect.ticks:
            MutedVoice(module, voice)
            EffectTick(module, voice, effect)
        elif not voice.ended:
            StepVoice(module, voice)
    MasterFade(module)


def StepVoice(module: Module, voice: Voice) -> None:
    """The phases move first. A new byte is read when the length runs
    out. A new note skips StartDma for this tick."""
    advance(voice)
    found = HELD
    if not voice.ticks:
        found = ReadStream(module, voice, muted=False)
        if found == END:
            return
    if found == HELD:
        StartDma(module, voice, muted=False)
    Portamento(voice)
    voice.channel.period = Vibrato(module, voice)
    voice.ticks = (voice.ticks - 1) & 0xFFFF
    if voice.volume_on:
        voice.channel.set_volume(EnvelopeTick(module, voice, muted=False))


def MutedVoice(module: Module, voice: Voice) -> None:
    """StepVoice without channel writes, while an effect plays. The
    fade level stays. It skips the ended check, so a voice that ended
    reads its end byte again each tick."""
    advance(voice)
    found = HELD
    if not voice.ticks:
        found = ReadStream(module, voice, muted=True)
        if found == END:
            return
    if found == HELD:
        StartDma(module, voice, muted=True)
    Portamento(voice)
    Vibrato(module, voice)
    voice.ticks = (voice.ticks - 1) & 0xFFFF
    EnvelopeTick(module, voice, muted=True)


def advance(voice: Voice) -> None:
    voice.vibrato_phase = (voice.vibrato_phase + voice.vibrato_speed) & 0xFF
    voice.envelope_pos = (voice.envelope_pos + ENVELOPE_STEP) & 0xFF


def ReadStream(module: Module, voice: Voice, muted: bool) -> int:
    """Commands run until a note, a tie or the end byte. A note byte is
    1 to 126; a length byte follows it. TIE holds the note on for its
    length: a tie. In legato mode, a note changes only the period,
    unless SetInstrument ran since the last note."""
    while True:
        byte = module.data[voice.pos]
        if byte == END_BYTE:
            VoiceEnd(module, voice, muted)
            return END
        voice.pos += 1
        if byte & COMMAND:
            RunCommand(module, voice, byte)
            continue
        voice.tie = byte == TIE
        if voice.tie:
            ReadLength(module, voice)
            return HELD
        if not voice.mode & LEGATO:
            NoteOn(module, voice, byte, muted)
            ReadLength(module, voice)
        elif voice.changed:
            SwapInstrument(module, voice, byte, muted)
            ReadLength(module, voice)
        else:
            LegatoNote(module, voice, byte, muted)
        return STARTED


def RunCommand(module: Module, voice: Voice, byte: int) -> None:
    """The low 5 bits pick a handler. Most take one argument byte."""
    COMMANDS[byte & 0x1F](module, voice)


def NoteOn(module: Module, voice: Voice, note: int, muted: bool) -> None:
    """DMA off, then the instrument's start, length and the note's
    period. The next tick turns DMA on. A new note ends a fade."""
    instrument = module.instruments[voice.instrument]
    period = PERIODS[note]
    voice.changed = False
    if not muted:
        voice.channel.disable()
        voice.volume_on = False
        voice.fade_level, voice.fading = 0, False
        voice.channel.queue(sample(module, instrument.start, instrument.length))
        voice.channel.period = period
    voice.target = voice.loop_period = period
    voice.loop = loop_sample(module, instrument)


def LegatoNote(module: Module, voice: Voice, note: int, muted: bool) -> None:
    """Only the period changes; the sample plays on. With portamento
    on, the pitch slides to the note. The replay reads the length in
    its own copy of ReadLength, which leaves DMA alone."""
    voice.target = PERIODS[note]
    if not muted:
        voice.channel.period = voice.target
    read_length(module, voice)
    restart(voice)


def SwapInstrument(module: Module, voice: Voice, note: int, muted: bool) -> None:
    """Legato mode, after SetInstrument: the note starts the new
    instrument at its loop, with no attack. Without a loop, it plays
    the empty loop at EMPTY_PERIOD. The muted copy also turns DMA off,
    so it stops the effect's sound."""
    instrument = module.instruments[voice.instrument]
    voice.channel.disable()
    voice.loop = loop_sample(module, instrument)
    period = PERIODS[note] if instrument.loop_length else EMPTY_PERIOD
    if not muted:
        voice.channel.set_volume(0)
        voice.volume_on = False
        voice.channel.queue(voice.loop)
        voice.channel.period = period
    voice.target = voice.loop_period = period
    voice.changed = False


def ReadLength(module: Module, voice: Voice) -> None:
    """A note restarts the vibrato and the envelope, unless SetMode
    keeps them, and asks for DMA. A tie does neither."""
    read_length(module, voice)
    if voice.tie:
        return
    restart(voice)
    voice.dma_pending = True


def read_length(module: Module, voice: Voice) -> None:
    """Bits 0-4: value; bits 5-7: shift. Pulses × PulseLength / 10800,
    plus the voice's last remainder. The new remainder stays with the
    voice. A result of 0 ticks lasts 65 536 ticks."""
    byte = arg(module, voice)
    pulses = (byte & 0x1F) << (byte >> 5)
    total = pulses * module.pulse_length + voice.remainder
    voice.ticks, voice.remainder = divmod(total, PULSE_DIVISOR)


def restart(voice: Voice) -> None:
    if not voice.mode & KEEP_VIBRATO:
        voice.vibrato_phase = 0
    if not voice.mode & KEEP_ENVELOPE:
        voice.envelope_pos = ENVELOPE_START


def StartDma(module: Module, voice: Voice, muted: bool) -> None:
    """The tick after a note: DMA on, unless VoiceMask mutes the voice.
    The tick after that: the loop and its period."""
    if voice.dma_pending:
        voice.dma_pending, voice.loop_pending = False, True
        if not muted and module.voice_mask >> voice.number & 1:
            voice.channel.enable()
            voice.volume_on = True
    elif voice.loop_pending:
        voice.loop_pending = False
        if not muted:
            voice.channel.queue(voice.loop)
            voice.channel.period = voice.loop_period


def Portamento(voice: Voice) -> None:
    """Moves the period by the step towards the target. Within one step,
    it lands on the target. Off, the period is the target."""
    if not voice.portamento_on:
        voice.period = voice.target
        return
    distance = signed_word(voice.target - voice.period)
    step = voice.portamento_step
    if step < abs(distance):
        voice.period += step if distance >= 0 else -step
    else:
        voice.period = voice.target


def Vibrato(module: Module, voice: Voice) -> int:
    """Period + period × value / divisor. The value is a signed byte of
    the vibrato table, at the phase. The divisor is 10000 / depth. So
    the swing is a share of the period: the same interval on every
    note."""
    if not voice.vibrato_on:
        return voice.period
    value = signed_byte(module.data[voice.vibrato_table + voice.vibrato_phase])
    offset = truncate(voice.period * value, voice.vibrato_divisor)
    return (voice.period + offset) & 0xFFFF


def EnvelopeTick(module: Module, voice: Voice, muted: bool) -> int:
    """The envelope byte at the index, times the volume, / 63. A negative
    byte jumps back by its size, rounded up to 4 bytes. The index steps
    4 bytes per tick and wraps at 256, so an envelope with no jump
    repeats every 64 ticks. A fade replaces the volume with a level that
    falls by its step each tick. Then VoiceMask and the master volume."""
    if not voice.volume:
        return 0
    while (value := module.data[voice.envelope_table + voice.envelope_pos]) & 0x80:
        back = (0x100 - value + 3) & 0xFC
        voice.envelope_pos = (voice.envelope_pos - back) & 0xFF
    level = voice.volume
    if voice.fading and not muted:
        if voice.fade_level:
            level = (voice.fade_level - voice.fade_step) & 0xFF
            voice.fade_level = level = 0 if level & 0x80 else level
        else:
            level = 0
    volume = (value & FULL) * (level & FULL) // FULL
    if not module.voice_mask >> voice.number & 1:
        return 0
    if module.master != FULL:
        volume = volume * module.master // FULL & FULL
    return volume


def VoiceEnd(module: Module, voice: Voice, muted: bool) -> None:
    """The voice stops for good. Its stream stays at the end byte."""
    module.ended_voices += 1
    voice.ended = True
    if not muted:
        voice.channel.disable()
        voice.volume_on = False


def MasterFade(module: Module) -> None:
    """One step of 1 every MasterSpeed ticks, until the target."""
    module.master_counter += 1
    if module.master_counter < module.master_speed:
        return
    module.master_counter = 0
    if not module.master_step:
        return
    if module.master == module.master_target:
        module.master_step = 0
        return
    module.master += module.master_step


# --- Sound effects -----------------------------------------------------


def StartEffect(module: Module, sound: Instrument, period: int, volume: int) -> None:
    """Commented out in this source. Its length in ticks is words ×
    period × 28 / 10^6: about the sample's play time at 50 Hz. It takes,
    of voices 0 to EffectVoiceCount, the one whose effect has the fewest
    ticks left. A later voice wins a tie. A looping effect counts from
    -1 down, so a new effect replaces it before it takes a free voice."""
    if not sound.start:
        return
    best, chosen = 0x7FFF, 0
    for n in range(module.effect_voices + 1):
        left = signed_word(module.effects[n].ticks)
        if left <= best:
            best, chosen = left, n
    effect = module.effects[chosen]
    effect.sample = sample(module, sound.start, sound.length)
    effect.volume, effect.period = volume, period
    effect.ticks = sound.length * period // 1000 * 28 // 1000
    effect.loop = loop_sample(module, sound)
    if sound.loop_length:
        effect.ticks = 0xFFFF
    effect.start = True


def EffectTick(module: Module, voice: Voice, effect: Effect) -> None:
    """Three ticks to start: DMA off and the sample, then DMA on, then
    the loop and the volume. The adaptation writes only the lengths.
    The original also wrote AUDxPER: first a loop address word, then
    the effect's period. At 0 ticks left: DMA off and volume 0.
    StopEffects ends only the first effect that sees it."""
    if effect.start:
        voice.channel.disable()
        voice.channel.queue(effect.sample)
        effect.start, effect.dma = False, True
    elif effect.dma:
        voice.channel.set_volume(0)
        voice.channel.enable()
        effect.dma, effect.queue_loop = False, True
    elif effect.queue_loop:
        voice.channel.queue(effect.loop)
        effect.queue_loop = False
        voice.channel.set_volume(effect.volume)
    effect.ticks = (effect.ticks - 1) & 0xFFFF
    if not effect.ticks:
        voice.channel.disable()
        voice.channel.set_volume(0)
    if module.stop_effects:
        module.stop_effects = False
        effect.ticks = 2


# --- Commands ----------------------------------------------------------

Command = Callable[[Module, Voice], None]


def BadCommand(module: Module, voice: Voice) -> None:
    """Unused numbers: flashes the screen white; no argument."""


def LoopStart(module: Module, voice: Voice) -> None:
    """1: a count. Pushes the count and the next byte's place."""
    count = arg(module, voice)
    voice.loops.append((count, voice.pos))


def LoopEnd(module: Module, voice: Voice) -> None:
    """2: counts down. At 0 it pops; else it jumps back. A count of 0
    plays 65 536 times."""
    count, pos = voice.loops[-1]
    count = (count - 1) & 0xFFFF
    if not count:
        voice.loops.pop()
        return
    voice.loops[-1] = (count, pos)
    voice.pos = pos


def SetVibratoDepth(module: Module, voice: Voice) -> None:
    """7: a depth; 0 turns vibrato off."""
    depth = arg(module, voice)
    voice.vibrato_on = bool(depth)
    if depth:
        voice.vibrato_divisor = VIBRATO_SCALE // depth


def SetVibratoSpeed(module: Module, voice: Voice) -> None:
    """8: added to the phase each tick."""
    voice.vibrato_speed = arg(module, voice)


def SetPortamento(module: Module, voice: Voice) -> None:
    """9: step / 4; 0 turns portamento off."""
    step = arg(module, voice)
    voice.portamento_on = bool(step)
    if step:
        voice.portamento_step = 4 * step


def SetVibratoTable(module: Module, voice: Voice) -> None:
    """11: 256 signed bytes."""
    voice.vibrato_table = module.vibrato_tables[arg(module, voice)]


def SetEnvelope(module: Module, voice: Voice) -> None:
    """12."""
    voice.envelope_table = module.envelope_tables[arg(module, voice)]


def VoiceVolume(module: Module, voice: Voice) -> None:
    """13: 0 to 63."""
    voice.volume = arg(module, voice)


def SetPulseLength(module: Module, voice: Voice) -> None:
    """14: × 16. It serves all voices. A larger value plays slower."""
    module.pulse_length = arg(module, voice) << 4


def SetInstrument(module: Module, voice: Voice) -> None:
    """15: also turns legato mode off, and marks the change for
    SwapInstrument."""
    voice.instrument = arg(module, voice)
    voice.mode &= ~LEGATO
    voice.changed = True


def SetMode(module: Module, voice: Voice) -> None:
    """19: bit 0 legato, bit 1 keeps the envelope, bit 2 keeps the
    vibrato phase."""
    voice.mode = arg(module, voice)


def EffectVoices(module: Module, voice: Voice) -> None:
    """20: effects may take voices 0 to this number."""
    module.effect_voices = arg(module, voice) & 3


def SetMarker(module: Module, voice: Voice) -> None:
    """21: a byte for the game (guess)."""
    module.marker = arg(module, voice)


def FadeMaster(module: Module, voice: Voice) -> None:
    """22: target, then ticks per step. 0 ticks sets it at once."""
    module.master_target = arg(module, voice)
    module.master_step = 1 if module.master_target > module.master else -1
    module.master_speed = arg(module, voice)
    if not module.master_speed:
        module.master_step = 0
        module.master = module.master_target


def FadeOut(module: Module, voice: Voice) -> None:
    """23: the fade starts from the volume. A new note ends it."""
    voice.fade_level, voice.fading = voice.volume, True


def FadeStep(module: Module, voice: Voice) -> None:
    """24."""
    voice.fade_step = arg(module, voice)


def FilterOn(module: Module, voice: Voice) -> None:
    """25."""
    module.audio_filter = True


def FilterOff(module: Module, voice: Voice) -> None:
    """26."""
    module.audio_filter = False


COMMANDS: tuple[Command, ...] = (  # CommandTable
    BadCommand, LoopStart, LoopEnd, BadCommand, BadCommand, BadCommand,
    BadCommand, SetVibratoDepth, SetVibratoSpeed, SetPortamento,
    BadCommand, SetVibratoTable, SetEnvelope, VoiceVolume, SetPulseLength,
    SetInstrument, BadCommand, BadCommand, BadCommand, SetMode,
    EffectVoices, SetMarker, FadeMaster, FadeOut, FadeStep, FilterOn,
    FilterOff, *(BadCommand,) * 5,
)  # fmt: skip


# --- Helpers -----------------------------------------------------------


def arg(module: Module, voice: Voice) -> int:
    voice.pos += 1
    return module.data[voice.pos - 1]


def sample(module: Module, start: int, words: int) -> paula.Sample:
    return paula.Sample(module.samples[start : start + 2 * words])


def loop_sample(module: Module, instrument: Instrument) -> paula.Sample:
    if not instrument.loop_length:
        return EMPTY
    return sample(module, instrument.loop_start, instrument.loop_length)


def word(data: bytes, at: int) -> int:
    return data[at] << 8 | data[at + 1]


def long(data: bytes, at: int) -> int:
    return word(data, at) << 16 | word(data, at + 2)


def signed_byte(value: int) -> int:
    return value - 0x100 if value & 0x80 else value


def signed_word(value: int) -> int:
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


def truncate(dividend: int, divisor: int) -> int:
    """DIVS: the quotient rounds towards 0."""
    quotient = abs(dividend) // divisor
    return -quotient if dividend < 0 else quotient
